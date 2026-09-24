# AGENTS.md — rules for any AI agent working on SanadAI

SanadAI (سند AI) verifies religious claims (Quran verses, hadith, attributed sayings) in circulating
posts against a trusted local corpus + Dorar.net, and prepares a verbatim, cited version for publishing.

## Non-negotiable principles
- **P1 No rulings, no sacred text generation.** The LLM never issues a religious ruling and never produces
  or rewrites a Quran verse or hadith text. All grades, sources, and sacred texts come from the DB / Dorar
  with provenance (source, url, grader).
- **P2 Evidence or nothing.** Every result carries its evidence. Below threshold → `not_found`, UI shows
  «لم يُعثر عليه في المصادر المعتمدة». Never guess.
- **P3 Narrow LLM use.** Only for: claim extraction (structured JSON), image OCR, short neutral UI summaries.
  Validate every LLM JSON with Pydantic; on failure retry once, then fall back to the rule-based extractor.
- **P4 Quran verbatim from Tanzil.** No modification; credit + link tanzil.net.
- **P5 Synthetic data only** in tests/demos. No real user conversations or personal data.
- **P6 Every dataset in SOURCES.md** with URL, license, version/date, and purpose.
- **P7 Simple and demo-ready** beats extra features.
- **Never invent** hadith text, gradings, hadith numbers, or scholar names — in code, seeds, tests, or docs.
  Fetch examples from the DB/Dorar and cite them; mark unverified seeds `needs_review`.

## Fixed stack (ask before changing)
- Python 3.11+ (venv uses 3.12), FastAPI async, Uvicorn, Pydantic v2, httpx.
- SQLite = source of truth for texts, FTS5 BM25 for lexical search. ChromaDB (persistent) for vectors only.
- Embeddings BAAI/bge-m3 (sentence-transformers); reranker BAAI/bge-reranker-v2-m3. Auto CUDA/MPS/CPU,
  batched, fp16 on GPU.
- LLM + vision: Anthropic API behind `app/llm/provider.py`; keys only from `.env` (never committed).
- Diff: difflib, word level, after normalization.
- Frontend: vanilla HTML/CSS/JS ES modules, no build step, RTL-first, served by FastAPI StaticFiles;
  evidence graph in inline SVG; AR/EN toggle.
- pytest, ruff, requirements.txt, Makefile + scripts/*.ps1 and *.sh (Windows-friendly).

## How to work
- Phases in order (see PROGRESS.md). Each phase ends with: run it, tests green, PROGRESS.md updated, commit.
- Small verifiable steps; never claim something works without running it.
- When a dataset differs from expectations, adapt and log the decision in PROGRESS.md.
- Ask the owner only for: unclear licenses, scope/stack changes, keys/credentials.
- Keep PROGRESS.md accurate: `[x]` done, `[ ]` todo, "Next step", "Decisions", "Known issues".
