-- homeFinance SP1 canonical schema.
-- Source of truth: docs/superpowers/specs/2026-06-10-sp1-foundation-design.md §6.2

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id          TEXT PRIMARY KEY,           -- "ynab:<budget_id>"
    kind        TEXT NOT NULL,              -- "ynab" | "statement"
    nickname    TEXT,
    config      TEXT,                       -- JSON snapshot of source-specific config
    created_at  TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE TABLE accounts (
    id                       TEXT PRIMARY KEY,
    source_id                TEXT NOT NULL REFERENCES sources(id),
    external_id              TEXT NOT NULL,
    name                     TEXT NOT NULL,
    type                     TEXT NOT NULL,
    on_budget                INTEGER NOT NULL DEFAULT 1,
    closed                   INTEGER NOT NULL DEFAULT 0,
    deleted                  INTEGER NOT NULL DEFAULT 0,
    currency                 TEXT NOT NULL DEFAULT 'USD',
    cleared_balance_minor    INTEGER,
    uncleared_balance_minor  INTEGER,
    balance_as_of            TEXT,
    last_synced_at           TEXT,
    UNIQUE (source_id, external_id)
);

CREATE TABLE categories (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,
    name         TEXT NOT NULL,
    group_name   TEXT,
    hidden       INTEGER NOT NULL DEFAULT 0,
    deleted      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE payees (
    id                  TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES sources(id),
    external_id         TEXT NOT NULL,
    name                TEXT NOT NULL,
    transfer_account_id TEXT REFERENCES accounts(id),
    deleted             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE transactions (
    id                     TEXT PRIMARY KEY,
    source_id              TEXT NOT NULL REFERENCES sources(id),
    external_id            TEXT NOT NULL,
    account_id             TEXT NOT NULL REFERENCES accounts(id),
    date                   TEXT NOT NULL,
    amount_minor           INTEGER NOT NULL,
    currency               TEXT NOT NULL,
    payee                  TEXT,
    payee_id               TEXT REFERENCES payees(id),
    memo                   TEXT,
    category_id            TEXT REFERENCES categories(id),
    cleared                TEXT,
    approved               INTEGER NOT NULL DEFAULT 1,
    flag_color             TEXT,
    import_id              TEXT,
    transfer_account_id    TEXT REFERENCES accounts(id),
    parent_id              TEXT REFERENCES transactions(id),
    is_split_parent        INTEGER NOT NULL DEFAULT 0,
    deleted                INTEGER NOT NULL DEFAULT 0,
    raw                    TEXT,
    synced_at              TEXT NOT NULL,
    UNIQUE (source_id, external_id)
);

CREATE TABLE sync_state (
    source_id         TEXT PRIMARY KEY REFERENCES sources(id),
    last_sync_at      TEXT NOT NULL,
    server_knowledge  INTEGER,
    last_error        TEXT,
    last_error_at     TEXT
);

CREATE TABLE sync_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         TEXT NOT NULL REFERENCES sources(id),
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    txns_inserted     INTEGER NOT NULL DEFAULT 0,
    txns_updated      INTEGER NOT NULL DEFAULT 0,
    txns_deleted      INTEGER NOT NULL DEFAULT 0,
    accounts_touched  INTEGER NOT NULL DEFAULT 0,
    reconciliation    TEXT NOT NULL,
    drift_report      TEXT,
    error             TEXT
);

CREATE INDEX idx_transactions_account_date ON transactions(account_id, date);
CREATE INDEX idx_transactions_date         ON transactions(date);
CREATE INDEX idx_transactions_category     ON transactions(category_id);
CREATE INDEX idx_transactions_payee        ON transactions(payee);
CREATE INDEX idx_transactions_parent       ON transactions(parent_id);
CREATE INDEX idx_accounts_source           ON accounts(source_id);
CREATE INDEX idx_sync_runs_source_time     ON sync_runs(source_id, started_at);
