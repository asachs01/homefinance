-- Migration 0002: statement batches + transaction status/batch link.
-- Source of truth: docs/superpowers/specs/2026-06-12-sp2-statement-ingest-design.md §6

CREATE TABLE statement_batches (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                TEXT NOT NULL REFERENCES sources(id),
    file_hash                TEXT NOT NULL,
    file_path_original       TEXT NOT NULL,
    file_path_archive        TEXT,
    parser                   TEXT NOT NULL,
    statement_period_start   TEXT,
    statement_period_end     TEXT,
    opening_balance_minor    INTEGER,
    closing_balance_minor    INTEGER,
    parsed_at                TEXT NOT NULL,
    review_status            TEXT NOT NULL,
    review_resolved_at       TEXT,
    txn_count                INTEGER NOT NULL DEFAULT 0,
    reconciliation_status    TEXT NOT NULL,
    drift_minor              INTEGER,
    notes                    TEXT,
    UNIQUE (file_hash, source_id)
);

CREATE INDEX idx_statement_batches_source ON statement_batches(source_id);
CREATE INDEX idx_statement_batches_review ON statement_batches(review_status);

ALTER TABLE transactions ADD COLUMN status   TEXT NOT NULL DEFAULT 'confirmed';
ALTER TABLE transactions ADD COLUMN batch_id INTEGER REFERENCES statement_batches(id);

CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_batch  ON transactions(batch_id) WHERE batch_id IS NOT NULL;
