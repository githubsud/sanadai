## Analysis of the remaining mismatches

- **No false "verified".** No item expected amber or red is shown green. An earlier run had 3 proverbs shown green
  because the reranker scored them > 0.8 against unrelated authentic hadith sharing a few words; since then a
  same-language meaning-only match needs reranker ≥ 0.90 **and** ≥ 40% shared words, and is at most amber
  («meaning only — this wording was not found»). Cross-language matches (English → Arabic) keep the 0.50 threshold,
  where the reranker is reliable (true translations score ≈ 1.0).
- **weak → red (12 items): labelling policy, not retrieval.** All 12 are matched to the expected Dorar record.
  Their silver label comes from Dorar's *top* verdict («ضعيف»), but among the verdicts on the same wording at least
  one muhaddith rates the text fabricated / baseless and none authenticates it, so the cautious aggregation rule
  shows red. Pending the owner's decision (keep cautious rule vs. majority vote).
- **nobasis-17 → amber**: "Cleanliness is next to godliness" is linked cross-lingually to Dorar's «النظافة من
  الإيمان» (a circulating text with its own verdicts) — arguably a better answer than "not found".
- **Source top-1 misses (2)**: one weak item is matched to a local hadith (Ibn Majah) instead of the expected Dorar
  record — same text, valid source; one English Quran translation is matched to a verse with near-identical
  English wording.

## Changes made from failure analysis

| Failure seen | Fix |
|---|---|
| Uthmani-script verses not matched exactly | Second exact-match stream over normalized Uthmani text |
| A substituted word in a verse classified "partial" | identical/partial require no word edits in the aligned span |
| Short weak sayings mislabelled sahih via an "altered" match to a different authentic hadith | Dorar is also consulted for "altered" local matches and preferred when its match is strictly better |
| Gradings of longer, different hadith mixed into a fabricated text's verdicts | Only hits matching at the best level contribute gradings |
| English proverbs "altered"-matched against English translations | Lexical "altered" is meaningless against a translation → not found |
| English Quran translations not found without the vector index | FTS5 index over the Saheeh International translation |
| The spec's English headline example not found (Dorar search is Arabic-only) | Cross-lingual search over embedded Dorar cache texts |
| Proverbs shown green via reranker-only meaning match | Stricter same-language paraphrase rule; meaning-only is never green |
