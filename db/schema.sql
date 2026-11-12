-- Food composition database schema.
-- Portable SQL: runs on SQLite (local build), Cloudflare D1 and Turso/libSQL.
-- Keep it free of engine-specific features (except the FTS5 table at the end)
-- so a later move to Postgres stays a rebuild, not a redesign.
--
-- All nutrient values are per 100 g (or 100 ml) edible portion.

PRAGMA foreign_keys = ON;

-- One row per data publisher / dataset release.
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,          -- short stable key, e.g. 'cfs', 'usda_sr'
    name          TEXT NOT NULL,
    publisher     TEXT,
    country       TEXT,                      -- ISO 3166 alpha-2, e.g. 'HK', 'US'
    licence       TEXT,
    attribution   TEXT,                      -- text we must show on the site
    url           TEXT,
    version       TEXT,
    retrieved_at  TEXT                       -- ISO date
);

-- Master list of nutrients. Every importer maps its own columns to these ids.
CREATE TABLE IF NOT EXISTS nutrients (
    id           TEXT PRIMARY KEY,           -- our stable key, e.g. 'protein'
    infoods_tag  TEXT,                       -- INFOODS tagname where the meaning is certain
    name_en      TEXT NOT NULL,
    name_zh      TEXT,
    unit         TEXT NOT NULL,              -- 'g', 'mg', 'ug', 'kcal', 'kJ'
    sort_order   INTEGER NOT NULL DEFAULT 0
);

-- Raw layer: one row per food per source, exactly as published.
-- id format: '<source_id>:<source_code>'. It must never change between re-imports,
-- because links, embeddings and external users all reference it.
CREATE TABLE IF NOT EXISTS foods (
    id             TEXT PRIMARY KEY,
    source_id      TEXT NOT NULL REFERENCES sources(id),
    source_code    TEXT NOT NULL,            -- the publisher's own food code
    name_en        TEXT,
    name_zh        TEXT,                     -- Traditional Chinese where available
    name_local     TEXT,                     -- original-language name if not en/zh (e.g. Japanese)
    alias          TEXT,
    group_en       TEXT,
    group_zh       TEXT,
    subgroup_en    TEXT,
    subgroup_zh    TEXT,
    description    TEXT,                     -- source's own description (state, preparation); not used for search
    origin_source  TEXT,                     -- for republished data: where the values first came from
    origin_code    TEXT,                     -- for republished data: the original publisher's food code (e.g. USDA NDB number)
    search_text    TEXT NOT NULL DEFAULT '', -- built by pipeline/common.py:search_text()
    -- display layer (pipeline/display.py), filled at the end of the build:
    cluster_id     TEXT,                     -- id of the main record of this food's group
    is_primary     INTEGER NOT NULL DEFAULT 1,  -- 1 = main record of its group (shown in search)
    display_zh     TEXT,                     -- name shown to HK users (HK word where possible)
    display_en     TEXT,
    sample_note    TEXT,                     -- sampling date removed from the name, e.g. '2018', '2月'
    category       TEXT,                     -- database-wide category (pipeline/categories.py)
    UNIQUE (source_id, source_code)
);
CREATE INDEX IF NOT EXISTS idx_foods_source ON foods(source_id);
CREATE INDEX IF NOT EXISTS idx_foods_cluster ON foods(cluster_id);

-- Nutrient values. A missing value ('NA') has NO row.
-- flag: NULL = normal number; 'ND' = not detected; 'TRACE' = trace amount (value is NULL for both).
-- method: optional qualifier, e.g. 'total' or 'difference' for carbohydrate, 'atwater_specific' for energy.
CREATE TABLE IF NOT EXISTS food_nutrients (
    food_id      TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    nutrient_id  TEXT NOT NULL REFERENCES nutrients(id),
    value        REAL,
    flag         TEXT CHECK (flag IN ('ND', 'TRACE')),
    method       TEXT,
    estimated    INTEGER NOT NULL DEFAULT 0 CHECK (estimated IN (0, 1)),  -- 1 = source marks the value as estimated/calculated
    PRIMARY KEY (food_id, nutrient_id)
);
CREATE INDEX IF NOT EXISTS idx_fn_nutrient_value ON food_nutrients(nutrient_id, value);

-- Typical serving sizes ("1 small bottle = 330 g").
CREATE TABLE IF NOT EXISTS servings (
    food_id   TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    label_en  TEXT,
    label_zh  TEXT,
    amount    REAL NOT NULL,
    unit      TEXT NOT NULL CHECK (unit IN ('g', 'ml'))
);
CREATE INDEX IF NOT EXISTS idx_servings_food ON servings(food_id);

-- Other codes a publisher gives the same food (e.g. USDA NDB number next to the FDC id).
CREATE TABLE IF NOT EXISTS food_codes (
    food_id  TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    scheme   TEXT NOT NULL,                  -- e.g. 'usda_ndb'
    code     TEXT NOT NULL,
    PRIMARY KEY (food_id, scheme)
);
CREATE INDEX IF NOT EXISTS idx_food_codes ON food_codes(scheme, code);

-- Link layer: duplicates and cross-source equivalents. Raw rows are never deleted.
-- match_type: 'exact_copy' = same values republished (hide one by default)
--             'equivalent' = same food, different source/country (keep both)
--             'similar'    = related food, weaker match
CREATE TABLE IF NOT EXISTS food_links (
    food_id       TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    canonical_id  TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    match_type    TEXT NOT NULL CHECK (match_type IN ('exact_copy', 'equivalent', 'similar')),
    confidence    REAL,                      -- 0..1
    method        TEXT,                      -- how the link was made, e.g. 'name+values', 'manual'
    PRIMARY KEY (food_id, canonical_id)
);
CREATE INDEX IF NOT EXISTS idx_links_canonical ON food_links(canonical_id);

-- Database-wide categories (pipeline/categories.py); foods.category refers to id.
CREATE TABLE IF NOT EXISTS categories (
    id          TEXT PRIMARY KEY,
    name_zh     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    sort_order  INTEGER NOT NULL
);

-- Synonym concepts a food belongs to (pipeline/synonyms.csv), e.g. 'broccoli'.
CREATE TABLE IF NOT EXISTS food_concepts (
    food_id  TEXT NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
    concept  TEXT NOT NULL,
    PRIMARY KEY (food_id, concept)
);
CREATE INDEX IF NOT EXISTS idx_food_concepts ON food_concepts(concept);

-- Keyword search. Trigram tokenizer gives substring matching for Chinese text
-- (no spaces between words). Queries shorter than 3 characters must fall back to LIKE.
CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
    search_text,
    content='foods',
    content_rowid='rowid',
    tokenize='trigram'
);

-- NOT YET CREATED (planned, see PROJECT.md):
-- food_embeddings(food_id, model, vector) - added only when vector search is needed (Turso/libSQL).
