## Method

**Test set** (`data/eval/testset.jsonl`, built by `scripts/build_testset.py`, seed 7). No religious text was written
by hand or by an LLM: every verse/hadith comes from the local datasets, every weak/fabricated phrasing comes from the
seed list whose Dorar results are cached, and the "no basis" probes are common proverbs.

| Category | Items | How inputs are made | Expected label |
|---|---|---|---|
| authentic | 40 | Bukhari/Muslim matn taken from quoted prophetic speech: 15 verbatim, 10 first-60% excerpts, 8 dataset English translations, 7 with one word dropped | green (altered → amber) |
| weak_fabricated | 40 | circulating phrasings from `data/seeds/circulating.txt` whose Dorar top hit matched (≥0.9) | top hit's verdict: fabricated/baseless → red, weak → amber |
| quran | 20 | Tanzil verses: 7 single + 3 two-verse ranges, 4 excerpts, 4 with one word replaced by the marked token `كلمةتجريبية`, 2 English translations | green (altered → amber) |
| no_basis | 20 | 16 Arabic + 4 English proverbs presented as «قال رسول الله ﷺ» / "The Prophet ﷺ said" | red, not found |

**Metrics**
- *Claim-extraction recall*: a claim was extracted whose tokens cover ≥80% of the quoted text of the input.
- *Top-1 source accuracy*: the source shown to the user is the expected one (any hadith containing the same text,
  the expected Dorar record, or an ayah range containing the expected verse).
- *Top-5 source accuracy*: the expected source is the shown source or among the top-5 candidates recorded in the
  evidence trace (lexical/hybrid retrieval, Dorar hits, Quran candidates).
- *Status accuracy / confusion matrix*: traffic light vs. expected.
- *Latency*: wall-clock per input on the evaluation machine (CPU laptop, int8 ONNX models), warm models.

## Sanad Score (deterministic)

The score measures **match & evidence confidence** — how sure the system is that the circulating text corresponds to
the cited source, combined with the quoted grading. It is **not a religious ruling**.

```
score = round(40 × match_confidence + TYPE[match_type] + GRADE[grade])      (0 if not found)
TYPE  = identical 30 · partial 20 · paraphrase 15 · altered 5 · not_found 0
GRADE = sahih 30 · hasan 25 · daif 5 · mawdu 0 · unknown 10 · Quran 30
```

`match_confidence` = cross-encoder (bge-reranker-v2-m3) relevance in [0, 1], or the lexical span similarity for exact
and excerpt matches found without the reranker.

**Grade aggregation** (several graders): inclusion in Sahih al-Bukhari/Muslim → sahih; if any grader says
fabricated/baseless and none authenticates it → mawdu; otherwise the majority class, ties → the more cautious class.
All verdicts are always quoted with grader, book and reference.

**Traffic light**
- 🟢 green — Quran verse matched (identical / excerpt / meaning), or a hadith graded sahih/hasan matched identically,
  as an excerpt, or by meaning with confidence ≥ 0.5.
- 🟡 amber — needs review: weak grading, unknown grading, altered wording, low confidence, or an unattributed saying
  not found.
- 🔴 red — graded fabricated/baseless, or attributed to the Prophet ﷺ / presented as Quran but not found in the
  approved sources («لم يُعثر عليه في المصادر المعتمدة»).

## Classification thresholds (`app/config.py`, env-overridable)

| Threshold | Value | Meaning |
|---|---|---|
| `TH_IDENTICAL` | 0.95 | whole-source char similarity (or aligned span covering ≥95% of the source) |
| `TH_PARTIAL_SPAN` | 0.90 | char similarity of the aligned span |
| `TH_PARTIAL_COVERAGE` | 0.60 | share of claim tokens aligned to the source |
| `TH_ALTERED` | 0.60 | minimum span similarity to call it an altered quote |
| `TH_PARAPHRASE_RERANK` | 0.50 | reranker relevance for a meaning / cross-language match |
| `TH_LOW_CONFIDENCE` | 0.50 | below this, a sahih/hasan match is only amber |

identical/partial additionally require **no word edits inside the aligned span** (strict for Quran; hadith tolerate
a leading و/ف), because one substituted word in a long verse still scores > 0.9 on character similarity.
