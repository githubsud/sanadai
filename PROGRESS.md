# PROGRESS — SanadAI

## Phases
- [x] Phase 0 — Setup: skeleton, AGENTS.md, PROGRESS.md, requirements, .env.example, Makefile/scripts, health endpoint, hello page
- [x] Phase 1 — Data: download_data.py, build_db.py (normalization + FTS5), SOURCES.md, normalize tests
  - 6,236 ayahs; 36,104 hadith (bukhari 7580, muslim 7360, abudawud 5272, tirmidhi 3924, nasai 5679,
    ibnmajah 4338, malik 1829, nawawi 42, qudsi 40, dehlawi 40); 82k gradings; matn extracted for 88%
  - repo.py data layer + GET /api/hadith/{id}, /api/ayah/{s}/{a}
- [ ] Phase 2 — Index: build_index.py (bge-m3, resumable, DEMO_SUBSET), retrieval + RRF + rerank, CLI
- [ ] Phase 3 — Quran matching, classification, diff, score + unit tests
- [ ] Phase 4 — Dorar client + cache + seed_dorar.py + alternatives (offline from cache)
- [ ] Phase 5 — LLM provider, extraction (JSON schema) + rule-based fallback, OCR, pipeline + trace, /api/verify
- [ ] Phase 6 — Frontend (all 6.10 components) wired to API
- [ ] Phase 7 — Prepare-for-publishing + verbatim validator
- [ ] Phase 8 — Eval set, run_eval.py, EVALUATION.md, threshold tuning
- [ ] Phase 9 — Hardening, ruff clean, fresh-clone test
- [ ] Phase 10 — Submission pack

## Next step
Phase 2: build_index.py (bge-m3) + retrieve.py (FTS5 + Chroma + RRF + rerank).

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

## Known issues
- matn heuristic misses some chain-only variant narrations (e.g. Muslim «ح» chains); full text is always matched too.
- 9 Muslim items lack an Abdul-Baqi number → stored as '<in-book no>-inbook'. Muslim decimal numbers (e.g. 1149.03)
  link to the integer page on sunnah.com.
- ~0.6% source rows with empty Arabic text are skipped.
