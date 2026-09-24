-- SanadAI SQLite schema. SQLite is the source of truth for all sacred texts.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ayahs (
    id             INTEGER PRIMARY KEY,         -- global ayah index 1..6236
    surah          INTEGER NOT NULL,
    ayah           INTEGER NOT NULL,
    surah_name_ar  TEXT NOT NULL,
    surah_name_en  TEXT NOT NULL,
    text_uthmani   TEXT NOT NULL,               -- Tanzil verbatim (display)
    text_clean     TEXT NOT NULL,               -- Tanzil simple-clean verbatim
    text_norm      TEXT NOT NULL,               -- normalize_ar(text_clean, honorifics=False)
    text_en        TEXT,                        -- Tanzil en.sahih (non-commercial)
    bismillah      TEXT,                        -- Tanzil's separate Basmala attribute of verse 1 (verbatim)
    UNIQUE (surah, ayah)
);

CREATE TABLE IF NOT EXISTS hadiths (
    id             INTEGER PRIMARY KEY,
    collection     TEXT NOT NULL,               -- e.g. bukhari
    book           TEXT,                        -- section / kitab name
    number         TEXT NOT NULL,               -- hadith number as displayed by the dataset
    text_ar        TEXT NOT NULL,               -- dataset verbatim (display)
    matn_ar        TEXT,                        -- verbatim substring of text_ar after the isnad (heuristic)
    text_norm      TEXT NOT NULL,               -- normalize_ar(text_ar)
    matn_norm      TEXT,                        -- normalize_ar(matn_ar)
    text_en        TEXT,
    text_en_norm   TEXT,
    narrator       TEXT,
    source_url     TEXT,
    source_dataset TEXT NOT NULL,
    UNIQUE (collection, number)
);
CREATE INDEX IF NOT EXISTS idx_hadiths_collection ON hadiths(collection);

CREATE TABLE IF NOT EXISTS gradings (
    id          INTEGER PRIMARY KEY,
    hadith_id   INTEGER NOT NULL REFERENCES hadiths(id) ON DELETE CASCADE,
    grade_ar    TEXT,
    grade_en    TEXT,
    grade_class TEXT NOT NULL CHECK (grade_class IN ('sahih', 'hasan', 'daif', 'mawdu', 'unknown')),
    grader      TEXT NOT NULL,
    reference   TEXT,
    source      TEXT NOT NULL                   -- dataset / provenance of this grading
);
CREATE INDEX IF NOT EXISTS idx_gradings_hadith ON gradings(hadith_id);

CREATE TABLE IF NOT EXISTS dorar_cache (
    key           TEXT PRIMARY KEY,
    endpoint      TEXT NOT NULL,
    response_json TEXT NOT NULL,
    fetched_at    TEXT NOT NULL
);

-- Distinct hadith texts seen in cached Dorar responses (for cross-lingual lookup; vectors in Chroma "dorar_ar").
CREATE TABLE IF NOT EXISTS dorar_texts (
    key       TEXT PRIMARY KEY,                -- sha1 of the text
    hadith_id TEXT,
    text      TEXT NOT NULL
);

-- Synthetic/test runs only. No PII: input is stored only as a hash.
CREATE TABLE IF NOT EXISTS checks (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    input_hash  TEXT NOT NULL,
    result_json TEXT NOT NULL
);

-- FTS5 over normalized text (external content, BM25 ranking).
CREATE VIRTUAL TABLE IF NOT EXISTS hadiths_fts USING fts5(
    text_norm, content='hadiths', content_rowid='id', tokenize='unicode61 remove_diacritics 0'
);
CREATE VIRTUAL TABLE IF NOT EXISTS hadiths_en_fts USING fts5(
    text_en_norm, content='hadiths', content_rowid='id', tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE IF NOT EXISTS ayahs_en_fts USING fts5(
    text_en, content='ayahs', content_rowid='id', tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE IF NOT EXISTS ayahs_fts USING fts5(
    text_norm, content='ayahs', content_rowid='id', tokenize='unicode61 remove_diacritics 0'
);
