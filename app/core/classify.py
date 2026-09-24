"""Deterministic match classification + word-level diff (difflib, on normalized text).

match types:
  identical   normalized char similarity to the whole source (or its matn) >= identical_min
  partial     the claim is a contiguous excerpt: best-aligned span similarity >= partial_span_min and
              claim coverage >= partial_coverage_min, while the span is only part of the source
  altered     best-aligned span similarity in [altered_min, identical_min): words substituted/added/removed
  paraphrase  low lexical similarity but high reranker (meaning) score, or a cross-language match
  not_found   below all thresholds
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.config import get_settings

MATCH_TYPES = ("identical", "partial", "altered", "paraphrase", "not_found")


@dataclass
class Thresholds:
    identical_min: float = 0.95
    partial_span_min: float = 0.90
    partial_coverage_min: float = 0.60
    altered_min: float = 0.60
    paraphrase_rerank_min: float = 0.50
    min_claim_tokens: int = 2


def thresholds() -> Thresholds:
    s = get_settings()
    return Thresholds(
        identical_min=s.th_identical, partial_span_min=s.th_partial_span, partial_coverage_min=s.th_partial_coverage,
        altered_min=s.th_altered, paraphrase_rerank_min=s.th_paraphrase_rerank,
    )


@dataclass
class Classification:
    match_type: str
    similarity: float                  # char similarity claim vs whole reference text
    span_similarity: float             # char similarity claim vs best-aligned span
    coverage: float                    # fraction of claim tokens aligned to the source
    span: tuple[int, int]              # token span [start, end) in the reference tokens
    diff: list[dict] = field(default_factory=list)
    reference: str = "text"            # which reference text won: "matn" | "text" | "en"

    def as_dict(self) -> dict:
        return {"match_type": self.match_type, "similarity": round(self.similarity, 4),
                "span_similarity": round(self.span_similarity, 4), "coverage": round(self.coverage, 4),
                "span": list(self.span), "reference": self.reference}


def char_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def best_window(claim: list[str], src: list[str]) -> tuple[int, int, float]:
    """Contiguous window of `src` that best matches `claim` (token-level ratio). Returns (start, end, ratio)."""
    n, m = len(claim), len(src)
    if n == 0 or m == 0:
        return 0, 0, 0.0
    if m <= n:
        return 0, m, SequenceMatcher(None, claim, src, autojunk=False).ratio()
    claim_set = set(claim)
    best = (0, n, -1.0)
    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(claim)
    sizes = sorted({max(1, round(n * f)) for f in (0.8, 1.0, 1.2)} | {n})
    for size in sizes:
        if size > m:
            continue
        # cheap prefilter: token overlap count in the window
        overlap = sum(1 for t in src[:size] if t in claim_set)
        for start in range(0, m - size + 1):
            if start:
                overlap += (src[start + size - 1] in claim_set) - (src[start - 1] in claim_set)
            if overlap * 2 / (n + size) <= best[2]:  # ratio upper bound cannot beat best
                continue
            sm.set_seq1(src[start:start + size])
            r = sm.ratio()
            if r > best[2]:
                best = (start, start + size, r)
    # trim unmatched edges of the window
    s0, e0, _ = best
    window = src[s0:e0]
    blocks = [b for b in SequenceMatcher(None, window, claim, autojunk=False).get_matching_blocks() if b.size]
    if blocks:
        s0, e0 = s0 + blocks[0].a, s0 + blocks[-1].a + blocks[-1].size
    return s0, e0, best[2]


def word_diff(claim: list[str], ref: list[str]) -> list[dict]:
    """What the circulating text changed relative to the source span.

    equal: shared words; insert: words added by the claim; delete: source words missing from the claim;
    replace: claim words (text) standing in for source words (source).
    """
    out: list[dict] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, ref, claim, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(ref[i1:i2])})
        elif op == "insert":
            out.append({"op": "insert", "text": " ".join(claim[j1:j2])})
        elif op == "delete":
            out.append({"op": "delete", "text": " ".join(ref[i1:i2])})
        else:
            out.append({"op": "replace", "text": " ".join(claim[j1:j2]), "source": " ".join(ref[i1:i2])})
    return out


def _coverage(claim: list[str], span: list[str]) -> float:
    if not claim:
        return 0.0
    matched = sum(b.size for b in SequenceMatcher(None, span, claim, autojunk=False).get_matching_blocks())
    return matched / len(claim)


_CLITICS = ("و", "ف")


def _is_minor(op: dict) -> bool:
    """A replace that only adds/drops a leading conjunction (و/ف), e.g. «وانما» vs «انما»."""
    if op["op"] != "replace":
        return False
    a, b = op["text"].split(), op["source"].split()
    if len(a) != len(b):
        return False
    strip = lambda w: w[1:] if len(w) > 2 and w[0] in _CLITICS else w  # noqa: E731
    return all(x == y or strip(x) == strip(y) or strip(x) == y or x == strip(y) for x, y in zip(a, b, strict=True))


def major_edits(diff: list[dict], strict: bool) -> list[dict]:
    """Word edits inside the aligned span (edge insertions are tolerated; they are shown in the diff)."""
    ops = list(diff)
    while ops and ops[0]["op"] == "insert":
        ops.pop(0)
    while ops and ops[-1]["op"] == "insert":
        ops.pop()
    return [o for o in ops if o["op"] != "equal" and (strict or not _is_minor(o))]


def compare(claim_norm: str, ref_norm: str, strict: bool = False) -> Classification:
    """Lexical comparison of a normalized claim against one normalized reference text (no meaning signal).

    Character similarity alone is too lenient for sacred text (one substituted word in a long verse still scores
    > 0.9), so identical/partial additionally require NO word edits inside the aligned span. `strict=True`
    (Quran) treats every word difference as an edit; hadith mode tolerates a leading و/ف conjunction.
    """
    th = thresholds()
    c_tok, r_tok = claim_norm.split(), ref_norm.split()
    whole = char_ratio(claim_norm, ref_norm)
    s, e, _ = best_window(c_tok, r_tok)
    span_toks = r_tok[s:e]
    span_sim = char_ratio(claim_norm, " ".join(span_toks))
    cov = _coverage(c_tok, span_toks)
    diff = word_diff(c_tok, span_toks)
    clean = not major_edits(diff, strict)
    if len(c_tok) < th.min_claim_tokens:
        mtype = "not_found"
    elif clean and cov >= th.partial_coverage_min and span_sim >= th.partial_span_min:
        whole_source = (e - s) >= len(r_tok) * th.identical_min or whole >= th.identical_min
        mtype = "identical" if whole_source else "partial"
    elif span_sim >= th.altered_min:
        mtype = "altered"
    else:
        mtype = "not_found"
    return Classification(mtype, whole, span_sim, cov, (s, e), diff)


RANK = {"identical": 4, "partial": 3, "altered": 2, "paraphrase": 1, "not_found": 0}


def classify(claim_norm: str, refs: dict[str, str], rerank: float | None, cross_lang: bool = False,
             strict: bool = False) -> Classification:
    """Classify against several normalized references of ONE source (e.g. matn, full text, English) and keep
    the best lexical result; fall back to paraphrase on a strong meaning score."""
    th = thresholds()
    best: Classification | None = None
    for name, ref in refs.items():
        if not ref:
            continue
        c = compare(claim_norm, ref, strict=strict)
        c.reference = name
        if best is None or (RANK[c.match_type], c.span_similarity) > (RANK[best.match_type], best.span_similarity):
            best = c
    if best is None:
        best = Classification("not_found", 0.0, 0.0, 0.0, (0, 0))
    # Meaning match (same language paraphrase, or any cross-language match such as English -> Arabic source).
    if best.match_type == "not_found" and rerank is not None and rerank >= th.paraphrase_rerank_min:
        best.match_type = "paraphrase"
    if best.match_type in ("not_found", "paraphrase"):
        best.diff = []
    if cross_lang and best.match_type == "identical" and best.reference != "en":
        best.match_type = "paraphrase"  # defensive: an English claim can't be identical to Arabic text
    return best
