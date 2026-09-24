"""Hybrid retrieval: FTS5 BM25 (lexical) + Chroma bge-m3 (dense) -> Reciprocal Rank Fusion -> bge-reranker.

    python -m app.core.retrieve "نص الحديث المتداول"
    python -m app.core.retrieve --kind quran "text of a verse"

Degrades gracefully: without a vector index it is lexical-only; without the reranker it ranks by RRF.
"""

import logging
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.core import models, vectors
from app.core.normalize import detect_lang, normalize_ar, normalize_en, strip_diacritics
from app.db import repo

log = logging.getLogger(__name__)

RERANK_DOC_CHARS = 450


@dataclass
class Candidate:
    kind: str                       # "hadith" | "ayah"
    id: int
    rrf: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)   # list name -> 1-based rank
    bm25: float | None = None
    dense_sim: float | None = None
    rerank: float | None = None

    @property
    def confidence(self) -> float:
        """Match confidence in [0, 1]: reranker if available, else a rank-based proxy."""
        if self.rerank is not None:
            return self.rerank
        return min(1.0, self.rrf * get_settings().rrf_k / 2)


@dataclass
class RetrievalResult:
    query: str
    lang: str
    kind: str
    candidates: list[Candidate]
    timings_ms: dict[str, float]
    used_dense: bool
    used_rerank: bool

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def weak(self) -> bool:
        b = self.best
        return b is None or b.confidence < get_settings().weak_match_threshold


def rrf_fuse(ranked_lists: dict[str, list[int]], k: int = 60) -> dict[int, tuple[float, dict[str, int]]]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank(d))."""
    fused: dict[int, tuple[float, dict[str, int]]] = {}
    for name, ids in ranked_lists.items():
        for rank, doc_id in enumerate(ids, start=1):
            score, ranks = fused.get(doc_id, (0.0, {}))
            ranks[name] = rank
            fused[doc_id] = (score + 1.0 / (k + rank), ranks)
    return fused


def _dense_available() -> bool:
    s = get_settings()
    return s.use_dense and s.resolve(s.chroma_path).exists() and any(vectors.index_counts().values())


def _doc_text(kind: str, doc_id: int, lang: str) -> str:
    if kind == "ayah":
        a = repo.get_ayah_by_id(doc_id)
        return (a["text_en"] if lang == "en" and a.get("text_en") else a["text_clean"]) if a else ""
    row = repo.conn().execute("SELECT matn_ar, text_ar, text_en FROM hadiths WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        return ""
    if lang == "en" and row["text_en"]:
        return row["text_en"][:RERANK_DOC_CHARS]
    return strip_diacritics(row["matn_ar"] or row["text_ar"])[:RERANK_DOC_CHARS]


def retrieve(text: str, kind: str = "hadith", lang: str | None = None, top_k: int | None = None,
             use_rerank: bool | None = None, hadith_collections: list[str] | None = None,
             use_dense: bool | None = None) -> RetrievalResult:
    s = get_settings()
    lang = lang or detect_lang(text)
    top_k = top_k or s.keep_top
    use_rerank = s.use_reranker if use_rerank is None else use_rerank
    timings: dict[str, float] = {}
    lists: dict[str, list[int]] = {}
    bm25: dict[int, float] = {}
    dense: dict[int, float] = {}

    q_ar = normalize_ar(text, honorifics=(kind != "ayah"))
    q_en = normalize_en(text)

    # 1) lexical
    t = time.perf_counter()
    if kind == "ayah":
        hits = repo.fts_ayahs(q_ar, s.lexical_k) if lang == "ar" else []
        lists["lex_ar"] = [i for i, _ in hits]
        bm25.update(hits)
    else:
        if lang == "ar":
            hits = repo.fts_hadiths(q_ar, s.lexical_k, "ar", hadith_collections)
            lists["lex_ar"] = [i for i, _ in hits]
        else:
            hits = repo.fts_hadiths(q_en, s.lexical_k, "en", hadith_collections)
            lists["lex_en"] = [i for i, _ in hits]
        bm25.update(hits)
    timings["lexical"] = (time.perf_counter() - t) * 1000

    # 2) dense
    used_dense = False
    t = time.perf_counter()
    if (use_dense is None or use_dense) and _dense_available():
        try:
            qvec = models.embed([q_ar if lang == "ar" else text])[0]
            names = ([f"{kind}_ar"] + ([f"{kind}_en"] if lang == "en" else []))
            for name in names:
                hits = vectors.query(name, qvec, s.dense_k)
                if hadith_collections and kind == "hadith" and hits:
                    allowed = {r[0] for r in repo.conn().execute(
                        f"SELECT id FROM hadiths WHERE collection IN ({','.join('?' * len(hadith_collections))})",
                        hadith_collections)}
                    hits = [h for h in hits if h[0] in allowed]
                lists[f"dense_{name}"] = [i for i, _ in hits]
                for i, sim in hits:
                    dense[i] = max(dense.get(i, -1.0), sim)
            used_dense = True
        except Exception as e:  # noqa: BLE001 - dense retrieval is optional
            log.warning("dense retrieval unavailable: %s", e)
    timings["dense"] = (time.perf_counter() - t) * 1000

    # 3) fuse
    fused = rrf_fuse(lists, s.rrf_k)
    ordered = sorted(fused.items(), key=lambda kv: kv[1][0], reverse=True)[: s.fuse_top]
    cands = [Candidate(kind=kind, id=i, rrf=sc, ranks=ranks, bm25=bm25.get(i), dense_sim=dense.get(i))
             for i, (sc, ranks) in ordered]

    # 4) rerank
    used_rerank = False
    t = time.perf_counter()
    if use_rerank and cands:
        try:
            q = strip_diacritics(text)
            head = cands[: s.rerank_top]
            scores = models.rerank(q, [_doc_text(kind, c.id, lang) for c in head])
            for c, sc in zip(head, scores, strict=True):
                c.rerank = sc
            cands = sorted(head, key=lambda c: c.rerank, reverse=True) + cands[s.rerank_top:]
            used_rerank = True
        except Exception as e:  # noqa: BLE001 - reranker is optional
            log.warning("reranker unavailable: %s", e)
    timings["rerank"] = (time.perf_counter() - t) * 1000

    return RetrievalResult(query=text, lang=lang, kind=kind, candidates=cands[:top_k], timings_ms=timings,
                           used_dense=used_dense, used_rerank=used_rerank)


def _cli() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="SanadAI retrieval sanity check")
    ap.add_argument("text")
    ap.add_argument("--kind", choices=["hadith", "ayah", "quran"], default="hadith")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    kind = "ayah" if a.kind == "quran" else a.kind
    res = retrieve(a.text, kind=kind, top_k=a.k, use_rerank=not a.no_rerank)
    print(f"lang={res.lang} dense={res.used_dense} rerank={res.used_rerank} "
          f"timings={ {k: round(v) for k, v in res.timings_ms.items()} } weak={res.weak}")
    for n, c in enumerate(res.candidates, 1):
        if kind == "ayah":
            a_ = repo.get_ayah_by_id(c.id)
            label, body = f"{a_['surah_name_ar']} {a_['surah']}:{a_['ayah']}", a_["text_clean"]
        else:
            h = repo.get_hadith(c.id)
            label, body = f"{h['collection']} {h['number']}", strip_diacritics(h["matn_ar"] or h["text_ar"])
        rr = f"{c.rerank:.3f}" if c.rerank is not None else "-"
        print(f"{n}. [{label}] id={c.id} rerank={rr} rrf={c.rrf:.4f} ranks={c.ranks}")
        print(f"   {body[:160]}")


if __name__ == "__main__":
    _cli()
