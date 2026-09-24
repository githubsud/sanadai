"""«جهّز للنشر» — Prepare for publishing (spec 6.8). Fully deterministic (no LLM).

The user's post is kept as written; each circulating religious text is replaced by the verified original
VERBATIM from the source, with a citation marker and a Sources block:
  keep     verified / weak-but-found: the original text (Quran: Tanzil Uthmani; hadith: dataset / Dorar text)
  replace  fabricated or not found, with an authentic alternative: the alternative, introduced by fixed wording
  remove   fabricated or not found, no alternative: the claim (and its attribution cue) is removed
A validator then checks that every sacred text inserted exists verbatim in the DB or the Dorar cache.
"""

import json
import re
from dataclasses import dataclass, field

from app.db import repo

QUOTES = {"«": "»", '"': '"', "“": "”", "﴿": "﴾", "❝": "❞"}
CUE_BEFORE = re.compile(
    r"(?:(?:و|ف)?(?:قال|يقول|قالت)\s+(?:رسول\s*الله|النبي|النبى|الله\s+تعالى|تعالى)[^:\n«\"﴿]{0,40}\s*[:：]?\s*"
    r"|the\s+(?:prophet|messenger)[^:\n]{0,40}?\s+said\s*[:：]?\s*)$",
    re.IGNORECASE,
)

L = {
    "ar": {"sources": "المصادر:", "alt_intro": "وقد صحّ في معناه:",
           "removed": "(حُذف نصٌّ منسوب لم يُعثر عليه في المصادر المعتمدة)", "grade": "الحكم", "translation": "الترجمة",
           "quran_src": "القرآن الكريم", "tanzil": "نص المصحف: مشروع تنزيل tanzil.net",
           "note": "✔ جُهّز بواسطة سند AI — النصوص منقولة حرفيًا من مصادرها."},
    "en": {"sources": "Sources:", "alt_intro": "An authentic text with this meaning:",
           "removed": "(removed: an attributed text not found in the approved sources)", "grade": "Grading",
           "translation": "Translation", "quran_src": "The Holy Quran",
           "tanzil": "Quran text: Tanzil Project tanzil.net",
           "note": "✔ Prepared with SanadAI — texts quoted verbatim from their sources."},
}


@dataclass
class Segment:
    """An inserted sacred text that must exist verbatim in a source."""
    text: str
    kind: str        # ayah | hadith | dorar | translation


@dataclass
class Prepared:
    text: str
    sources: list[str]
    replacements: list[dict]
    segments: list[Segment] = field(default_factory=list)
    validated: bool = False
    validation_errors: list[str] = field(default_factory=list)


def decide(c: dict) -> str:
    """Same rule as web/graph.js finalWording."""
    if c["match_type"] != "not_found" and c["grade_class"] != "mawdu" and (c.get("ayah") or c.get("source")):
        return "keep"
    return "replace" if c.get("alternatives") else "remove"


def _grade_line(gradings: list[dict]) -> str:
    parts = []
    for g in gradings[:3]:
        label = g.get("grade_ar") or g.get("grade_en") or ""
        parts.append(f"{g.get('grader')}: {label}".strip())
    return "؛ ".join(parts)


def _render_original(c: dict, out: str, segs: list[Segment]) -> tuple[str, str]:
    """(inline text, source line) for a kept claim."""
    L_ = L[out]
    if c.get("ayah"):
        a = c["ayah"]
        start = repo.get_ayah(a["surah"], a["ayah_start"])
        ayahs = repo.get_ayah_range(start["id"], start["id"] + _n_ayahs(a) - 1)
        for x in ayahs:
            segs.append(Segment(x["text_uthmani"], "ayah"))
        inline = "﴿" + " ".join(f"{x['text_uthmani']} ({x['ayah']})" for x in ayahs) + "﴾"
        if out == "en" and all(x["text_en"] for x in ayahs):
            for x in ayahs:
                segs.append(Segment(x["text_en"], "translation"))
            inline += f"\n({L_['translation']}: " + " ".join(x["text_en"] for x in ayahs) + ")"
        src = f"{L_['quran_src']} — {a['surah_name_ar'] if out == 'ar' else a['surah_name_en']} {a['ref']} — {a['url']}"
        return inline, src
    s = c["source"]
    kind = "dorar" if s.get("kind") == "dorar" else "hadith"
    # a partial quote is replaced by the matching verbatim excerpt of the source (not the whole hadith)
    arabic = s.get("excerpt_ar") if c["match_type"] == "partial" and s.get("excerpt_ar") else s["text_ar"]
    segs.append(Segment(arabic, kind))
    inline = f"«{arabic}»"
    if out == "en" and s.get("text_en"):
        segs.append(Segment(s["text_en"], "translation"))
        inline += f"\n({L_['translation']}: {s['text_en']})"
    name = s.get("collection_en") if out == "en" and s.get("collection_en") else s.get("collection")
    grade = _grade_line(c.get("gradings") or [])
    src = f"{name} {s.get('number') or ''}".strip()
    if grade:
        src += f" — {L_['grade']}: {grade}"
    if s.get("url"):
        src += f" — {s['url']}"
    return inline, src


def _n_ayahs(a: dict) -> int:
    if a["surah_end"] == a["surah"]:
        return a["ayah_end"] - a["ayah_start"] + 1
    first = repo.get_ayah(a["surah"], a["ayah_start"])["id"]
    last = repo.get_ayah(a["surah_end"], a["ayah_end"])["id"]
    return last - first + 1


def _render_alternative(alt: dict, out: str, segs: list[Segment]) -> tuple[str, str]:
    L_ = L[out]
    kind = "dorar" if alt["origin"].startswith("dorar") else "hadith"
    segs.append(Segment(alt["text_ar"], kind))
    inline = f"{L_['alt_intro']} «{alt['text_ar']}»"
    if out == "en" and alt.get("text_en"):
        segs.append(Segment(alt["text_en"], "translation"))
        inline += f"\n({L_['translation']}: {alt['text_en']})"
    src_d = alt.get("source") or {}
    name = src_d.get("collection_en") if out == "en" and src_d.get("collection_en") else src_d.get("collection")
    src = f"{name or ''} {src_d.get('number') or ''}".strip()
    grade = _grade_line(alt.get("gradings") or [])
    if grade:
        src += f" — {L_['grade']}: {grade}"
    if src_d.get("url"):
        src += f" — {src_d['url']}"
    return inline, src


def _span(post: str, claim_text: str, start_at: int) -> tuple[int, int] | None:
    i = post.find(claim_text, start_at)
    if i < 0:
        i = post.find(claim_text)
    return (i, i + len(claim_text)) if i >= 0 else None


def build(post: str, claims: list[dict], out: str = "ar") -> Prepared:
    out = "en" if out == "en" else "ar"
    pieces: list[str] = []
    sources: list[str] = []
    replacements: list[dict] = []
    segs: list[Segment] = []
    cursor = 0
    for c in claims:
        sp = _span(post, c["claim_text"], cursor)
        if sp is None or sp[0] < cursor:
            replacements.append({"claim": c["claim_text"], "action": "skipped", "reason": "span_not_found"})
            continue
        s0, e0 = sp
        # widen to surrounding quotes, e.g. «claim» or ﴿claim﴾
        if s0 > 0 and post[s0 - 1] in QUOTES and e0 < len(post) and post[e0] == QUOTES[post[s0 - 1]]:
            s0, e0 = s0 - 1, e0 + 1
        action = decide(c)
        before = post[cursor:s0]
        if action == "keep":
            inline, src = _render_original(c, out, segs)
        elif action == "replace":
            inline, src = _render_alternative(c["alternatives"][0], out, segs)
            before = CUE_BEFORE.sub("", before)
        else:
            inline, src = L[out]["removed"], None
            before = CUE_BEFORE.sub("", before)
        pieces.append(before)
        if src:
            sources.append(src)
            pieces.append(f"{inline} [{len(sources)}]")
        else:
            pieces.append(inline)
        replacements.append({"claim": c["claim_text"], "action": action, "status": c["status"],
                             "citation": len(sources) if src else None})
        cursor = e0
    pieces.append(post[cursor:])
    body = re.sub(r"[ \t]+\n", "\n", "".join(pieces))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    text = body
    if sources:
        text += "\n\n" + L[out]["sources"] + "\n" + "\n".join(f"[{i}] {s}" for i, s in enumerate(sources, 1))
        if any(r.get("action") == "keep" and c.get("ayah") for r, c in zip(replacements, claims, strict=False)):
            text += "\n" + L[out]["tanzil"]
    text += "\n\n" + L[out]["note"]
    return Prepared(text=text, sources=sources, replacements=replacements, segments=segs)


# ---------------- verbatim validator ----------------

def _in_dorar_cache(text: str) -> bool:
    c = repo.conn()
    for (js,) in c.execute("SELECT response_json FROM dorar_cache WHERE instr(response_json, ?) > 0 LIMIT 5",
                           (json.dumps(text, ensure_ascii=False)[1:-1],)):
        items = json.loads(js)
        if any(isinstance(it, dict) and it.get("text") == text for it in items):
            return True
    return False


def _translation_exists(text: str) -> bool:
    c = repo.conn()
    return bool(c.execute("SELECT 1 FROM ayahs WHERE text_en = ? LIMIT 1", (text,)).fetchone()
                or c.execute("SELECT 1 FROM hadiths WHERE text_en = ? LIMIT 1", (text,)).fetchone())


def validate(p: Prepared) -> Prepared:
    errors = []
    for seg in p.segments:
        if seg.kind == "ayah":
            ok = bool(repo.conn().execute("SELECT 1 FROM ayahs WHERE text_uthmani = ?", (seg.text,)).fetchone())
        elif seg.kind == "hadith":
            ok = repo.text_exists_verbatim(seg.text)
        elif seg.kind == "dorar":
            ok = _in_dorar_cache(seg.text)
        else:
            ok = _translation_exists(seg.text)
        if not ok:
            errors.append(f"{seg.kind} text not found verbatim in sources: {seg.text[:40]}…")
        elif seg.text not in p.text:
            errors.append(f"{seg.kind} text altered in output: {seg.text[:40]}…")
    p.validation_errors = errors
    p.validated = not errors
    return p


def prepare(post: str, claims: list[dict], out: str = "ar") -> Prepared:
    return validate(build(post, claims, out))
