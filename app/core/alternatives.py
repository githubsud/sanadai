"""Authentic alternatives for weak / fabricated / unfound claims (spec 6.7).

1) Dorar's «الصحيح البديل» for the matched Dorar hadith (quoted verbatim with its grader).
2) Otherwise: local hybrid search restricted to hadith whose quoted gradings aggregate to sahih/hasan and whose
   meaning score (reranker) is high enough. At most MAX_ALTERNATIVES, each with full source + gradings.
Nothing here is generated: every text and grading comes from Dorar or the local DB.
"""

import logging

from app.core.retrieve import retrieve
from app.core.score import aggregate_grade
from app.db import repo
from app.sources.dorar import DorarHadith, DorarUnavailable, client

log = logging.getLogger(__name__)

MAX_ALTERNATIVES = 2
MIN_MEANING = 0.35


def from_dorar_hadith(h: DorarHadith, origin: str = "dorar_alternate") -> dict:
    return {
        "origin": origin,
        "text_ar": h.text,
        "text_en": None,
        "source": {"collection": h.book, "number": h.number_or_page, "url": h.url, "narrator": h.rawi,
                   "provider": "dorar.net"},
        "gradings": [{"grade_ar": h.grade, "grade_en": None, "grade_class": h.grade_class, "grader": h.mohdith,
                      "reference": f"{h.book} {h.number_or_page}".strip(), "source": "dorar.net"}],
        "grade_class": h.grade_class,
    }


def from_local_hadith(hid: int, meaning: float | None, origin: str = "local_search") -> dict | None:
    h = repo.get_hadith(hid)
    if not h:
        return None
    return {
        "origin": origin,
        "hadith_id": hid,
        "text_ar": h["matn_ar"] or h["text_ar"],
        "text_ar_full": h["text_ar"],
        "text_en": h["text_en"],
        "source": {"collection": h["collection_name_ar"], "collection_en": h["collection_name_en"],
                   "number": h["number"], "url": h["source_url"], "narrator": h["narrator"],
                   "provider": h["source_dataset"]},
        "gradings": h["gradings"],
        "grade_class": aggregate_grade(h["gradings"]),
        "meaning_score": round(meaning, 3) if meaning is not None else None,
    }


def dorar_alternates(dorar_hits: list[DorarHadith]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for h in dorar_hits:
        if not (h.has_alternate and h.hadith_id):
            continue
        try:
            alt = client().alternate(h.hadith_id)
        except DorarUnavailable as e:
            log.info("dorar alternate unavailable: %s", e)
            break
        if alt and alt.grade_class in ("sahih", "hasan") and alt.text not in seen:
            seen.add(alt.text)
            out.append(from_dorar_hadith(alt))
        if len(out) >= MAX_ALTERNATIVES:
            break
    return out


def local_alternates(claim_text: str, exclude_ids: set[int] | None = None, lang: str | None = None) -> list[dict]:
    exclude_ids = exclude_ids or set()
    res = retrieve(claim_text, kind="hadith", lang=lang, top_k=10)
    out: list[dict] = []
    for c in res.candidates:
        if c.id in exclude_ids:
            continue
        meaning = c.rerank if c.rerank is not None else None
        if meaning is not None and meaning < MIN_MEANING:
            continue
        if meaning is None and c.confidence < MIN_MEANING:
            continue
        alt = from_local_hadith(c.id, meaning)
        if alt and alt["grade_class"] in ("sahih", "hasan"):
            out.append(alt)
        if len(out) >= MAX_ALTERNATIVES:
            break
    return out


def suggest(claim_text: str, dorar_hits: list[DorarHadith] | None = None, exclude_ids: set[int] | None = None,
            lang: str | None = None) -> list[dict]:
    alts = dorar_alternates(dorar_hits or [])
    if len(alts) < MAX_ALTERNATIVES:
        alts += local_alternates(claim_text, exclude_ids, lang)[: MAX_ALTERNATIVES - len(alts)]
    return alts[:MAX_ALTERNATIVES]
