"""Verification pipeline: orchestrates the agentic steps for each claim and records an evidence trace.

    extract -> (quran match | hadith retrieval -> classify) -> Dorar (if weak / ungraded) -> grade -> score
            -> alternatives (if not green)

Every text, number and grading in the result is quoted from the DB or Dorar with provenance. The LLM (if used)
only extracted the claim spans; summaries are deterministic templates.
"""

import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.config import get_settings
from app.core import alternatives as alts
from app.core import classify as cls
from app.core.extract import extract_claims, ocr_image
from app.core.matn import find_excerpt
from app.core.normalize import detect_lang, normalize_ar, normalize_en
from app.core.quran_match import exact_matches, match_quran
from app.core.retrieve import retrieve
from app.core.score import aggregate_grade, sanad_score
from app.db import repo
from app.llm.provider import LLMError
from app.models import (
    Alternative,
    AyahRef,
    ClaimResult,
    ExtractedClaim,
    Grading,
    SourceRef,
    TraceStep,
    VerifyResponse,
)
from app.sources.dorar import DorarHadith, DorarUnavailable
from app.sources.dorar import client as dorar_client

log = logging.getLogger(__name__)

STEP_LABELS = {
    "ocr": ("قراءة الصورة", "Read image"),
    "extract": ("استخراج الادعاءات", "Extract claims"),
    "quran_match": ("مطابقة القرآن", "Match Quran"),
    "retrieve": ("البحث في المصادر", "Search sources"),
    "classify": ("مقارنة النص", "Compare wording"),
    "dorar": ("الدرر السنية", "Dorar.net"),
    "grade": ("أحكام المحدثين", "Scholars' gradings"),
    "score": ("درجة السند", "Sanad score"),
    "alternatives": ("البديل الصحيح", "Authentic alternative"),
}

# Original posts are kept in memory only (never persisted) so /api/prepare can rebuild them. No PII on disk.
_POSTS: "OrderedDict[str, str]" = OrderedDict()
_POSTS_MAX = 500


def remember_post(check_id: str, text: str) -> None:
    _POSTS[check_id] = text
    while len(_POSTS) > _POSTS_MAX:
        _POSTS.popitem(last=False)


def recall_post(check_id: str) -> str | None:
    return _POSTS.get(check_id)


@dataclass
class Tracer:
    steps: list[TraceStep] = field(default_factory=list)

    @contextmanager
    def step(self, name: str, **detail):
        t0 = time.perf_counter()
        rec = TraceStep(step=name, label_ar=STEP_LABELS[name][0], label_en=STEP_LABELS[name][1], detail=dict(detail))
        try:
            yield rec
        except Exception as e:
            rec.status = "error"
            rec.detail["error"] = str(e)[:200]
            raise
        finally:
            rec.ms = round((time.perf_counter() - t0) * 1000, 1)
            self.steps.append(rec)


# ---------------- hadith matching ----------------

@dataclass
class HadithMatch:
    hadith_id: int
    c: cls.Classification
    confidence: float


def _hadith_refs(h: dict, lang: str) -> dict[str, str]:
    if lang == "en":
        return {"en": normalize_en(h["text_en"] or "")}
    return {"matn": h["matn_norm"] or "", "text": h["text_norm"]}


def _key(m: HadithMatch) -> tuple:
    return (cls.RANK[m.c.match_type], round(m.c.coverage, 2), round(m.c.span_similarity, 3), m.confidence)


def match_hadith(claim: str, lang: str, tr: Tracer) -> HadithMatch | None:
    norm = normalize_ar(claim) if lang == "ar" else normalize_en(claim)
    best: HadithMatch | None = None

    def consider(res, rerank_known: bool):
        nonlocal best
        rows = repo.get_hadiths([c.id for c in res.candidates])
        for cand in res.candidates:
            h = rows.get(cand.id)
            if not h:
                continue
            c = cls.classify(norm, _hadith_refs(h, lang), cand.rerank, cross_lang=False)
            lexical = c.span_similarity if c.match_type in ("identical", "partial", "altered") else 0.0
            conf = max(cand.rerank or 0.0, lexical) if rerank_known else lexical
            m = HadithMatch(cand.id, c, conf)
            if best is None or _key(m) > _key(best):
                best = m

    # Pass 1: lexical only (fast). An exact / excerpt match needs no meaning model.
    with tr.step("retrieve", mode="lexical") as st:
        res = retrieve(claim, kind="hadith", lang=lang, top_k=8, use_rerank=False, use_dense=False)
        st.detail["candidates"] = len(res.candidates)
    with tr.step("classify", pass_="lexical") as st:
        consider(res, rerank_known=False)
        st.detail["best"] = best.c.match_type if best else None
    if best and best.c.match_type in ("identical", "partial"):
        return best

    # Pass 2: hybrid + reranker (meaning / paraphrase / cross-language).
    with tr.step("retrieve", mode="hybrid") as st:
        res = retrieve(claim, kind="hadith", lang=lang, top_k=5)
        st.detail.update(candidates=len(res.candidates), dense=res.used_dense, rerank=res.used_rerank,
                         timings_ms={k: round(v) for k, v in res.timings_ms.items()})
        if not res.used_rerank:
            st.status = "degraded"
    with tr.step("classify", pass_="hybrid") as st:
        consider(res, rerank_known=res.used_rerank)
        st.detail["best"] = best.c.match_type if best else None
    return best


# ---------------- dorar ----------------

@dataclass
class DorarMatch:
    hits: list[DorarHadith]            # all hits returned by Dorar
    matching: list[DorarHadith]        # hits whose text matches the claim
    best: DorarHadith | None
    c: cls.Classification | None


def match_dorar(claim_ar: str, tr: Tracer) -> DorarMatch | None:
    with tr.step("dorar") as st:
        try:
            hits = dorar_client().search(claim_ar)
        except DorarUnavailable as e:
            st.status = "degraded"
            st.detail["reason"] = str(e)
            return None
        norm = normalize_ar(claim_ar)
        scored = []
        for h in hits:
            c = cls.compare(norm, normalize_ar(h.text))
            scored.append((cls.RANK[c.match_type], round(c.coverage, 2), c.span_similarity, h, c))
        scored.sort(key=lambda x: x[:3], reverse=True)
        matching = [h for r, _cov, _s, h, _c in scored if r >= cls.RANK["altered"]]
        best = scored[0] if scored and scored[0][0] >= cls.RANK["altered"] else None
        st.detail.update(results=len(hits), matching=len(matching),
                         best_match=best[4].match_type if best else "not_found")
        return DorarMatch(hits, matching, best[3] if best else None, best[4] if best else None)


def _dorar_gradings(hits: list[DorarHadith]) -> list[dict]:
    out, seen = [], set()
    for h in hits:
        key = (h.mohdith, h.grade, h.book)
        if key in seen or not h.grade:
            continue
        seen.add(key)
        out.append({"grade_ar": h.grade, "grade_en": None, "grade_class": h.grade_class, "grader": h.mohdith or "-",
                    "reference": f"{h.book} {h.number_or_page}".strip(), "source": "dorar.net"})
    return out


# ---------------- per-claim ----------------

def _summary(status: str, match_type: str, claim_type: str, where: str | None) -> tuple[str, str]:
    """Neutral, deterministic one-liners (no LLM)."""
    if match_type == "not_found":
        return "لم يُعثر عليه في المصادر المعتمدة.", "Not found in the approved sources."
    mt_ar = {"identical": "مطابق", "partial": "جزء من النص", "altered": "مع تغيير في الألفاظ",
             "paraphrase": "بالمعنى"}[match_type]
    mt_en = {"identical": "identical", "partial": "an excerpt", "altered": "with altered wording",
             "paraphrase": "by meaning"}[match_type]
    st_ar = {"green": "موثّق", "amber": "يحتاج مراجعة", "red": "منسوب خطأً أو لا أصل له"}[status]
    st_en = {"green": "verified", "amber": "needs review", "red": "misattributed / no basis"}[status]
    w = f" — {where}" if where else ""
    return f"{st_ar}: وُجد {mt_ar}{w}.", f"{st_en}: found {mt_en}{w}."


def verify_claim(idx: int, claim: ExtractedClaim) -> ClaimResult:
    s = get_settings()
    tr = Tracer()
    lang = claim.lang
    notes: list[str] = []
    ctype = claim.claim_type
    ayah_ref = source = None
    gradings: list[dict] = []
    c: cls.Classification | None = None
    confidence = 0.0
    local_hid: int | None = None
    dm: DorarMatch | None = None

    # 1) Quran: always try an exact match (cheap); fuzzy/meaning only when the post says it is a verse.
    qm = None
    with tr.step("quran_match") as st:
        norm_q = normalize_ar(claim.text, honorifics=False) if lang == "ar" else ""
        if lang == "ar" and len(norm_q.split()) >= 3 and exact_matches(norm_q, limit=1):
            qm = match_quran(claim.text, lang, use_rerank=False)
        elif ctype == "quran":
            qm = match_quran(claim.text, lang)
        else:
            st.status = "skipped"
        if qm:
            st.detail.update(match=qm.match_type, ref=qm.ref()["ref"] if qm.match_type != "not_found" else None)
    if qm and qm.match_type != "not_found" and (ctype == "quran" or qm.match_type in ("identical", "partial")):
        if ctype != "quran":
            notes.append("retyped_as_quran")
        ctype = "quran"
        c, confidence = qm.classification, qm.confidence
        ref = qm.ref()
        ayah_ref = AyahRef(**{k: ref[k] for k in AyahRef.model_fields if k in ref},
                           other_occurrences=[f"{repo.get_ayah_by_id(a0)['surah']}:{repo.get_ayah_by_id(a0)['ayah']}"
                                              for a0, _ in qm.occurrences[:5]])
        if qm.match_type == "paraphrase" and lang == "en":
            notes.append("matched_translation_meaning")
    elif ctype == "quran":
        c = cls.Classification("not_found", 0, 0, 0, (0, 0))

    # 2) Hadith / saying
    if ctype != "quran":
        hm = match_hadith(claim.text, lang, tr)
        good_local = hm is not None and hm.c.match_type != "not_found" and (
            hm.c.match_type in ("identical", "partial") or hm.confidence >= s.th_low_confidence)
        if good_local:
            local_hid, c, confidence = hm.hadith_id, hm.c, hm.confidence
            h = repo.get_hadith(local_hid)
            gradings = h["gradings"]
            source = SourceRef(kind="hadith", hadith_id=local_hid, collection=h["collection_name_ar"],
                               collection_en=h["collection_name_en"], number=h["number"], book=h["book"],
                               narrator=h["narrator"], text_ar=h["matn_ar"] or h["text_ar"], text_ar_full=h["text_ar"],
                               text_en=h["text_en"], url=h["source_url"], provider=h["source_dataset"])
            if c.match_type == "partial":
                ref_tokens = _hadith_refs(h, lang).get(c.reference, "").split()[c.span[0]:c.span[1]]
                source.excerpt_ar = find_excerpt(source.text_ar, ref_tokens) or find_excerpt(h["text_ar"], ref_tokens)
            if ctype == "saying" and c.match_type in ("identical", "partial", "altered", "paraphrase"):
                ctype = "hadith"
                notes.append("retyped_as_hadith")

        # 3) Dorar when the local match is weak or the hadith has no grading (spec 6.3)
        #    ... or when the local match is only "altered": the circulating text may be a DIFFERENT (weak) hadith
        #    that Dorar has verbatim, e.g. a short weak saying that resembles part of an authentic hadith.
        local_exact = good_local and c.match_type in ("identical", "partial")
        need_dorar = (not local_exact) or not gradings or aggregate_grade(gradings) == "unknown"
        claim_ar = claim.text if lang == "ar" else (source.text_ar if source else None)
        if need_dorar and claim_ar:
            dm = match_dorar(claim_ar, tr)
            if dm and dm.best is not None:
                d_grades = _dorar_gradings(dm.matching)
                dorar_better = lang == "ar" and good_local and cls.RANK[dm.c.match_type] > cls.RANK[c.match_type]
                if dorar_better:
                    notes.append("dorar_match_preferred")
                    good_local, local_hid = False, None
                if good_local:
                    if cls.RANK[dm.c.match_type] >= cls.RANK[c.match_type]:
                        gradings = gradings + d_grades
                        notes.append("gradings_from_dorar")
                else:
                    c = dm.c if lang == "ar" else cls.Classification("paraphrase", 0, 0, 0, (0, 0))
                    confidence = c.span_similarity if c.match_type != "paraphrase" else (hm.confidence if hm else 0.5)
                    b = dm.best
                    source = SourceRef(kind="dorar", collection=b.book, number=b.number_or_page, narrator=b.rawi,
                                       text_ar=b.text, url=b.url, provider="dorar.net")
                    gradings = d_grades
                    if ctype == "saying":
                        ctype = "hadith"
                        notes.append("retyped_as_hadith")
        elif need_dorar:
            notes.append("dorar_skipped_no_arabic_text")
        if c is None:
            c = hm.c if hm else cls.Classification("not_found", 0, 0, 0, (0, 0))
            confidence = 0.0

    # 4) grade + score
    with tr.step("grade") as st:
        grade = aggregate_grade(gradings) if ctype != "quran" else "quran"
        st.detail.update(n=len(gradings), aggregate=grade)
    with tr.step("score") as st:
        sc = sanad_score(ctype, c.match_type, confidence, grade if grade != "quran" else "unknown",
                         attributed_to_prophet=(ctype == "hadith"))
        st.detail.update(score=sc.score, status=sc.status, reasons=sc.reasons)

    # 5) alternatives for anything that is not verified
    alternatives: list[dict] = []
    if sc.status != "green" and ctype != "quran":
        with tr.step("alternatives") as st:
            try:
                alternatives = alts.suggest(claim.text, dm.matching if dm else [],
                                            exclude_ids={local_hid} if local_hid else set(), lang=lang)
            except Exception as e:  # noqa: BLE001 - alternatives are best effort
                st.status = "degraded"
                st.detail["error"] = str(e)[:120]
            st.detail["n"] = len(alternatives)

    where = None
    if ayah_ref:
        where = f"{ayah_ref.surah_name_ar} {ayah_ref.ref}"
    elif source:
        where = f"{source.collection} {source.number or ''}".strip()
    s_ar, s_en = _summary(sc.status, c.match_type, ctype, where)
    show_diff = c.match_type in ("altered", "partial")
    return ClaimResult(
        index=idx, claim_text=claim.text, claim_type=ctype, attributed_to=claim.attributed_to, lang=lang,
        status=sc.status, sanad_score=sc.score, match_type=c.match_type, match_confidence=round(confidence, 3),
        reasons=sc.reasons, grade_class=sc.grade_class, diff=c.diff if show_diff else [],
        source=source if c.match_type != "not_found" else None, ayah=ayah_ref,
        gradings=[Grading(**g) for g in gradings] if c.match_type != "not_found" else [],
        alternatives=[Alternative(**{k: a.get(k) for k in Alternative.model_fields if k in a}) for a in alternatives],
        evidence_trace=tr.steps, notes=notes, summary_ar=s_ar, summary_en=s_en,
    )


# ---------------- entry point ----------------

def verify(text: str | None = None, image_base64: str | None = None, lang_hint: str | None = None) -> VerifyResponse:
    s = get_settings()
    tr = Tracer()
    notes: list[str] = []
    post = (text or "").strip()
    if image_base64:
        with tr.step("ocr") as st:
            try:
                ocr_text = ocr_image(image_base64)
                post = (post + "\n" + ocr_text).strip() if post else ocr_text.strip()
                st.detail["chars"] = len(ocr_text)
            except (LLMError, ValueError) as e:
                st.status = "degraded"
                st.detail["reason"] = str(e)
                notes.append("ocr_unavailable")
    post = post[: s.max_input_chars]
    check_id = uuid.uuid4().hex[:12]
    lang = lang_hint or detect_lang(post)
    if not post:
        return VerifyResponse(check_id=check_id, input_text="", input_lang=lang, extraction_method="rules",
                              claims=[], evidence_trace=tr.steps, notes=notes + ["empty_input"])
    with tr.step("extract") as st:
        ex = extract_claims(post)
        st.detail.update(method=ex.method, n=len(ex.claims), notes=ex.notes)
    notes += ex.notes
    claims = [verify_claim(i, c) for i, c in enumerate(ex.claims)]
    resp = VerifyResponse(check_id=check_id, input_text=post, input_lang=lang, extraction_method=ex.method,
                          claims=claims, evidence_trace=tr.steps, notes=notes)
    remember_post(check_id, post)
    try:
        stored = resp.model_dump()
        stored["input_text"] = ""  # the post itself is not persisted (P5); only its hash
        repo.save_check(check_id, hashlib.sha256(post.encode()).hexdigest(), stored)
    except Exception as e:  # noqa: BLE001 - persistence is best effort
        log.warning("could not save check: %s", e)
    return resp
