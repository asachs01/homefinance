-- Migration 0003: categorization rules + canonical category columns.
-- Source of truth: docs/superpowers/specs/2026-06-15-sp3-analysis-design.md §6

CREATE TABLE category_rules (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    priority           INTEGER NOT NULL,
    match_field        TEXT NOT NULL,
    pattern            TEXT NOT NULL,
    is_regex           INTEGER NOT NULL DEFAULT 0,
    canonical_category TEXT NOT NULL,
    note               TEXT,
    created_at         TEXT NOT NULL
);

CREATE INDEX idx_category_rules_priority ON category_rules(priority);

ALTER TABLE transactions ADD COLUMN canonical_category TEXT;
ALTER TABLE transactions ADD COLUMN category_source    TEXT;

CREATE INDEX idx_transactions_canonical ON transactions(canonical_category);
