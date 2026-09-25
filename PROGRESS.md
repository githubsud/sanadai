# PROGRESS — SanadAI

## Phases
- [x] Phase 0 — Setup: skeleton, AGENTS.md, PROGRESS.md, requirements, .env.example, Makefile/scripts, health endpoint, hello page
- [x] Phase 1 — Data: download_data.py, build_db.py (normalization + FTS5), SOURCES.md, normalize tests
  - 6,236 ayahs; 36,104 hadith (bukhari 7580, muslim 7360, abudawud 5272, tirmidhi 3924, nasai 5679,
    ibnmajah 4338, malik 1829, nawawi 42, qudsi 40, dehlawi 40); 82k gradings; matn extracted for 88%
  - repo.py data layer + GET /api/hadith/{id}, /api/ayah/{s}/{a}
- [x] Phase 2 — Index: build_index.py (bge-m3, resumable, DEMO_SUBSET), retrieval + RRF + rerank, CLI
  - ayah_ar + ayah_en (6,236 each), hadith_ar (15,062 demo docs), dorar_ar (1,199 cached Dorar texts); CLI verified
- [x] Phase 3 — Quran matching (exact stream, clean+Uthmani spellings, fuzzy windows), classification, diff, score + tests
- [x] Phase 4 — Dorar client (Python port, urllib) + permanent cache + seed_dorar.py + alternatives
  - 146 seed queries → 130 with Dorar results cached (report: data/seeds/seed_report.jsonl, needs owner review)
- [x] Phase 5 — LLM provider, extraction (JSON schema) + rule-based fallback, OCR, pipeline + trace, /api/verify
  - LLM path unit-tested with a fake provider; no API key on dev machine yet (rules fallback used live)
- [x] Phase 6 — Frontend (all 6.10 components) wired to API; screenshots in docs/screenshots (desktop + mobile)
- [x] Phase 7 — Prepare-for-publishing (deterministic, no LLM) + verbatim validator; AR/EN output
- [x] Phase 8 — Eval set (120 items, needs owner review), run_eval.py, EVALUATION.md, fixes from failure analysis
  - final run (2026-09-25, 50,703 hadith, owner-policy labels): top-5 98%, top-1 98%, extraction 100%,
    match-type 98.8%, status 99.2% (no false green), median 2.8 s / p90 8.9 s on CPU
- [x] Phase 9 — Hardening (warm-up, timeouts, JSON 500, health), ruff clean, fresh-clone test passed
  (clone → setup.ps1 → download → build_db → 156 passed / 2 skipped; server works before the vector index)
- [x] Phase 10 — README (bilingual, 4-command setup, diagram, screenshots, eval table), ARCHITECTURE, DEMO_SCRIPT,
  SOURCES, LICENSE, included/not-included list

## Next step
Owner decisions applied, Gemini live-tested, pushed to https://github.com/githubsud/sanadai. Pending: owner label review, demo video.

## Owner decisions (2026-09-25)
1. Cautious policy KEPT: any fabricated/baseless verdict and no authenticating one → red. Test-set labels for
   weak/fabricated items now computed with this policy over all Dorar verdicts on the same wording (12 relabelled).
2. Red Sanad Score capped at 30 (evidence still shown in full).
3. Dorar cache export COMMITTED (data/seeds/dorar_cache.jsonl, 198 responses); build_db imports it.
4. AhmedBaset/hadith-json INCLUDED despite no license: +7 books, 50,703 hadith / 17 collections. Primary collections
   are cited over secondary compilations (Riyad, Mishkat, Bulugh, 40s) when both match.
5. onnx-community reranker export (no license tag, Apache-2.0 base) accepted.
6. Owner has a Gemini key (no Anthropic key) → GeminiProvider added (LLM_PROVIDER=auto|anthropic|gemini).
   LIVE-TESTED 2026-09-25 with gemini-3.8-flash: extraction verbatim on 3 synthetic posts (caught a companion's
   saying and an English paraphrase the rules missed; a du'a post → no claims); OCR of a synthetic screenshot
   (docs/demo/synthetic_post.png) → both claims verified. gemini-3.8-flash returned 503 "high demand" at times →
   fallback chain GEMINI_FALLBACK_MODELS (gemini-2.5-flash, gemini-flash-latest).
7. Owner will review needs_review data (seeds, seed report, test set).
8. LICENSE: Ahmed Abayazid Mussaad (SanadAI). Publish to https://github.com/githubsud (repo: sanadai) — needs the
   empty repository to be created (no gh CLI on this machine). Demo video: owner records per DEMO_SCRIPT.md.

## Decisions
- 2026-09-24: venv on Python 3.12 (3.13 also installed) for best torch/chromadb wheel compatibility.
- 2026-09-24: No NVIDIA GPU detected on dev laptop → CPU embeddings; DEMO_SUBSET is the default dev path.
- 2026-09-24: Primary hadith dataset = fawazahmed0/hadith-api (Unlicense, 10 collections, ~36k hadith, per-hadith
  gradings by named graders). AhmedBaset/hadith-json has NO license → not used pending owner decision.
- 2026-09-24: No public Dorar wrapper instance exists and it needs Node; dorar.net's own JSON endpoint works from Python
  with browser-like headers (bare requests get a Cloudflare 403). Plan: port the wrapper's endpoints/parsing (MIT) to
  Python in app/sources/dorar.py — no Node dependency.
- 2026-09-24: English Quran translation = Saheeh International via Tanzil (non-commercial terms); not committed.
- 2026-09-24: Matching uses Tanzil simple-clean (Uthmani rasm is not recoverable by normalization); Uthmani for display.
- 2026-09-24: Bukhari/Muslim have no per-hadith grades in the dataset → attributed grading row
  "Sahih (included in Sahih al-Bukhari/Muslim)", source=collection_inclusion.
- 2026-09-24: gradings.grade_class = deterministic bucket of the grader's quoted label (app/core/grades.py).
- 2026-09-24: ruff line-length 120.
- 2026-09-24: CPU speed: fp32 bge-m3 = 1.6 docs/s and reranking 20 pairs = 36 s on this 8 GB laptop (swapping).
  → int8 ONNX graphs of the SAME weights (Xenova/bge-m3, onnx-community/bge-reranker-v2-m3-ONNX) via
  sentence-transformers' ONNX backend (scripts/fetch_models.py). Fidelity: cosine 0.975 vs fp32, NN agreement 0.90;
  reranker separation 0.995 vs <0.06. Speed ~3.6x. MODEL_BACKEND=torch keeps the original models (GPU).
  sentence-transformers pinned to 5.x (transformers 4.x) for optimum compatibility.
- 2026-09-24: Reranker rescores top RERANK_TOP=10 fused candidates (spec: 20) for CPU latency; 20 on GPU.
- 2026-09-24: DEMO_SUBSET vectors = ayah_ar, ayah_en, hadith_ar for bukhari/muslim/nawawi/qudsi/dehlawi. hadith_en
  skipped in demo (English input uses English FTS over ALL collections + cross-lingual bge-m3). Lexical FTS always
  covers all 36k hadith.
- 2026-09-24: Classification deviates from pure char thresholds: identical/partial also require NO word edits in
  the aligned span (a single substituted word in a long verse otherwise scores >0.9). Quran = strict; hadith
  tolerates a leading و/ف. Ties between candidates broken by claim coverage.
- 2026-09-24: Pipeline does a lexical-only pass first; the reranker runs only if no identical/partial match.
- 2026-09-24: Dorar via urllib, not httpx: dorar.net's Cloudflare returns 403 to httpx (lower-case header names
  from h11) and 200 to urllib/curl. robots.txt allows all; 1 request/1.2 s; permanent cache.
- 2026-09-24: Grade aggregation: collection inclusion → sahih; any fabricated/baseless verdict with NO sahih/hasan
  verdict → mawdu (red); otherwise majority, ties → more cautious class. All verdicts quoted.
- 2026-09-24: Uncued text (no «قال رسول الله», no quotes) is a "saying" of unknown attribution: re-typed when it
  matches a verse/hadith; a miss is amber "not found", never red.
- 2026-09-24: The posted text is kept in memory only (for /api/prepare); checks table stores hash + result.
- 2026-09-24: Quran imported from Tanzil XML (not TXT): TXT prefixes the Basmala to verse 1 of 112 surahs; XML keeps
  it as a separate attribute (stored in ayahs.bismillah) with the verse verbatim.
- 2026-09-24: Pipeline also queries Dorar when the local match is only "altered", and prefers Dorar's source when its
  match is strictly better (short weak sayings resembling part of an authentic hadith were mislabelled sahih).
- 2026-09-24: Prepare is deterministic: keep → verbatim original (partial quotes → verbatim excerpt of the source),
  fabricated/not found → Dorar/local alternative with a fixed connective phrase, or removed with its attribution cue
  and a note. No LLM involved; validator checks every inserted segment verbatim against DB / Dorar cache.
- 2026-09-24: UI example chips: fabricated (EN, spec example), weak «كما تكونوا يولى عليكم» (all Dorar verdicts
  weak), authentic Bukhari 6138 excerpt, Quran 112:1-4 (texts copied from the DB).
- 2026-09-25: Same-language meaning-only matches need reranker ≥ 0.90 AND ≥ 40% shared words and are never green
  (reranker gave unrelated proverbs > 0.8 against authentic hadith). Cross-language threshold stays 0.50.
- 2026-09-25: Dorar gradings are taken only from hits matching at the best level (the text as circulated).
- 2026-09-25: English claims → cross-lingual search over embedded Dorar cache texts (dorar_ar), then the cached search.
- 2026-09-24: LLM default model claude-opus-5 (LLM_MODEL), effort low, JSON-schema output. Server-side refusal
  fallbacks not enabled: a refusal falls back to the rule-based extractor instead.

## Known issues
- matn heuristic misses some chain-only variant narrations (e.g. Muslim «ح» chains); full text is always matched too.
- 9 Muslim items lack an Abdul-Baqi number → stored as '<in-book no>-inbook'. Muslim decimal numbers (e.g. 1149.03)
  link to the integer page on sunnah.com.
- ~0.6% source rows with empty Arabic text are skipped.
- Sanad Score follows spec 6.6 literally: a well-evidenced FABRICATED text scores ~70 (high match confidence) while
  red. Pending owner decision on whether to cap the score for red items.
- English claims with no local match reach Dorar only via texts already in the Dorar cache (cross-lingual lookup).
- Hadith «الجنة تحت أقدام الأمهات» is red, not amber: al-Albani «موضوع» (الضعيفة 593) among weak verdicts and no
  authenticating verdict → cautious rule. Intended; all verdicts are quoted.
- Startup warm-up takes ~35 s on CPU (background); requests needing the reranker take 3-12 s on this laptop.
