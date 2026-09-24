"""Quran verse matching.

1) Exact: the normalized claim is searched in the whole Quran as ONE token stream (so quotes spanning several
   consecutive ayahs are found), reporting every occurrence (repeated verses exist).
2) Fuzzy: candidate ayahs from FTS5 + dense retrieval; each candidate is extended to a window of consecutive
   ayahs and compared with classify.compare (altered wording / partial quotes).
3) Meaning: for translations / paraphrases, the reranker score on the best candidate decides (paraphrase).

Text returned for display is always the verbatim Tanzil Uthmani text of the matched ayah range (P4).
"""

import bisect
from dataclasses import dataclass, field
from functools import lru_cache

from app.core import classify as cls
from app.core.normalize import detect_lang, normalize_ar, normalize_en
from app.core.retrieve import retrieve
from app.db import repo


@dataclass
class QuranMatch:
    start_id: int
    end_id: int
    match_type: str
    confidence: float
    classification: cls.Classification | None
    occurrences: list[tuple[int, int]] = field(default_factory=list)   # other (start_id, end_id) with same text
    rerank: float | None = None

    def ayahs(self) -> list[dict]:
        return repo.get_ayah_range(self.start_id, self.end_id)

    def ref(self) -> dict:
        ay = self.ayahs()
        first, last = ay[0], ay[-1]
        same = first["surah"] == last["surah"]
        rng = f"{first['ayah']}" if first["id"] == last["id"] else (
            f"{first['ayah']}-{last['ayah']}" if same else f"{first['ayah']}-{last['surah']}:{last['ayah']}")
        return {
            "surah": first["surah"], "surah_name_ar": first["surah_name_ar"], "surah_name_en": first["surah_name_en"],
            "ayah_start": first["ayah"], "ayah_end": last["ayah"], "surah_end": last["surah"],
            "ref": f"{first['surah']}:{rng}",
            "text_uthmani": " ".join(a["text_uthmani"] for a in ay),
            "text_clean": " ".join(a["text_clean"] for a in ay),
            "text_en": " ".join(a["text_en"] or "" for a in ay).strip() or None,
            "url": f"https://tanzil.net/#{first['surah']}:{first['ayah']}",
            "source": "Tanzil Quran Text (Uthmani) — tanzil.net",
        }


SPELLINGS = ("clean", "uthmani")  # users paste either imla'i text or Uthmani text copied from Quran apps


@lru_cache(maxsize=1)
def _norms(spelling: str) -> dict[int, str]:
    """ayah id -> normalized text in the given spelling."""
    if spelling == "clean":
        return {aid: t for aid, _s, _a, t in repo.all_ayahs("text_norm")}
    return {aid: normalize_ar(t, honorifics=False) for aid, _s, _a, t in repo.all_ayahs("text_uthmani")}


@lru_cache(maxsize=2)
def _stream(spelling: str = "clean") -> tuple[str, list[int], list[int]]:
    """(joined text, char offset of each token, ayah id of each token)."""
    parts, offsets, owners = [], [], []
    pos = 0
    for aid, norm in _norms(spelling).items():
        for tok in norm.split():
            offsets.append(pos)
            owners.append(aid)
            parts.append(tok)
            pos += len(tok) + 1
    return " ".join(parts), offsets, owners


def exact_matches(claim_norm: str, limit: int = 50, spelling: str = "clean") -> list[tuple[int, int, bool]]:
    """All occurrences as (start_ayah_id, end_ayah_id, covers_whole_ayahs)."""
    text, offsets, owners = _stream(spelling)
    n_tok = len(claim_norm.split())
    if n_tok == 0:
        return []
    needle = f" {claim_norm} "
    hay = f" {text} "
    out = []
    i = hay.find(needle)
    while i >= 0 and len(out) < limit:
        t0 = bisect.bisect_left(offsets, i)          # token index of first matched token
        t1 = t0 + n_tok - 1
        a0, a1 = owners[t0], owners[t1]
        whole = (t0 == 0 or owners[t0 - 1] != a0) and (t1 == len(owners) - 1 or owners[t1 + 1] != a1)
        out.append((a0, a1, whole))
        i = hay.find(needle, i + 1)
    return out


def _window_text(start_id: int, end_id: int, spelling: str = "clean") -> str:
    norms = _norms(spelling)
    return " ".join(norms[i] for i in range(start_id, end_id + 1) if i in norms)


def _key(m: QuranMatch) -> tuple:
    """Prefer the better match type, then the source that explains more of the claim, then confidence."""
    c = m.classification
    return (cls.RANK[m.match_type], round(c.coverage, 2) if c else 0.0, round(c.span_similarity, 3) if c else 0.0,
            m.confidence)


def match_quran(claim: str, lang: str | None = None, use_rerank: bool | None = None,
                use_dense: bool | None = None) -> QuranMatch | None:
    lang = lang or detect_lang(claim)
    norm = normalize_ar(claim, honorifics=False) if lang == "ar" else normalize_en(claim)

    # 1) exact
    for spelling in SPELLINGS if lang == "ar" else ():
        hits = exact_matches(norm, spelling=spelling)
        if hits:
            # prefer an occurrence that covers whole ayahs
            hits.sort(key=lambda h: (not h[2], h[0]))
            a0, a1, whole = hits[0]
            c = cls.compare(norm, _window_text(a0, a1, spelling), strict=True)
            c.match_type = "identical" if whole else "partial"
            c.diff = [{"op": "equal", "text": norm}]
            return QuranMatch(a0, a1, c.match_type, 1.0, c, occurrences=[(h[0], h[1]) for h in hits[1:]])

    # 2) fuzzy candidates
    res = retrieve(claim, kind="ayah", lang=lang, top_k=5, use_rerank=use_rerank, use_dense=use_dense)
    if not res.candidates:
        return None
    n_claim = len(norm.split())
    best: QuranMatch | None = None
    for cand in res.candidates:
        if lang == "ar":
            # window of consecutive ayahs around the candidate (one before, then forward until at least as long as
            # the claim); the alignment below trims it to the ayahs actually covered.
            start = end = cand.id
            if len(_norms("clean")[cand.id].split()) < n_claim and start > 1:
                start -= 1
            while len(_window_text(start, end).split()) < n_claim + 2 and end < 6236 and end - start < 12:
                end += 1
            c = cls.classify(norm, {sp: _window_text(start, end, sp) for sp in SPELLINGS}, cand.rerank, strict=True)
            s0, e0 = c.span
            # shrink to the ayahs actually covered by the aligned span
            norms = _norms(c.reference if c.reference in SPELLINGS else "clean")
            pos, first, last = 0, start, end
            for aid in range(start, end + 1):
                n = len(norms[aid].split())
                if pos + n <= s0:
                    first = aid + 1
                if pos < e0:
                    last = aid
                pos += n
            first = min(first, last)
        else:
            en = repo.get_ayah_by_id(cand.id)["text_en"] or ""
            c = cls.classify(norm, {"en": normalize_en(en)}, cand.rerank, cross_lang=True, strict=True)
            first = last = cand.id
        m = QuranMatch(first, last, c.match_type, cand.confidence if c.match_type != "not_found" else 0.0, c,
                       rerank=cand.rerank)
        if best is None or _key(m) > _key(best):
            best = m
    return best
