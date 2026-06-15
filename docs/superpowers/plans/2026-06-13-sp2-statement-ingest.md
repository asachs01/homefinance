# SP2 — Statement & Bill Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the second `homeFinance` sub-project: a statement-file ingestion adapter (CSV / OFX / QFX / Docling-parsed PDF) that funnels parsed transactions through a two-phase write path (stage as `pending_review` → human confirms → atomic flip to `confirmed`) over SP1's canonical store, with no schema-incompatible changes and the lean install unaffected.

**Architecture:** Strategy-pattern parser registry (dispatch by file content; lazy-imported). Per-account TOML templates map parser output to canonical fields. Reconciliation gates by recording drift but never auto-confirming. The `StatementAccountSource` implements SP1's `AccountSource` Protocol so MCP read tools treat the new source identically. A single additive migration (`0002`) extends `transactions` with `status` + `batch_id` and adds the new `statement_batches` table. See spec: `docs/superpowers/specs/2026-06-12-sp2-statement-ingest-design.md`.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3`), `pydantic` v2, `typer` + `rich`, `yoyo-migrations`, official `mcp` SDK, `pytest` + `pytest-httpx`; new SP2 deps gated to `[ingest]` extra: `ofxtools` (OFX/QFX), `docling` (PDF/image).

---

## Prerequisites (one-off, before Task 1)

These are user-side setup steps, not implementation tasks:

```bash
cd /Users/asachs/Documents/projects/personal/homeFinance
git checkout main && git pull origin main
git checkout -b sp2-ingest
```

All commits in this plan land on the `sp2-ingest` branch. The venv from SP1 lives at `~/.virtualenvs/homeFinance/` and is reused throughout. Use absolute venv binary paths (`~/.virtualenvs/homeFinance/bin/{python,pytest,mypy,ruff}`) since subagent shells don't persist `workon` state.

After Task 1 lands the `[ingest]` extra in `pyproject.toml`, you'll re-run `~/.virtualenvs/homeFinance/bin/pip install -e ".[dev,ingest]"` once to pull in `ofxtools` and `docling` (plus PyTorch — first install will be slow and large).

---

## File Structure

These files will be created or modified across the 26 tasks. Each task lists exact paths.

```
homefinance/
├── pyproject.toml                                # Task 1 (add [ingest] extra)
├── README.md                                     # Task 26
├── CHANGELOG.md                                  # Task 26
├── .github/workflows/
│   ├── ci.yml                                    # Task 25 (no behavior change; reaffirm lean install)
│   └── ci-docling.yml                            # Task 25 (new manual-dispatch job)
│
├── plugin/skills/
│   ├── homefinance-setup/SKILL.md                # Task 22 (edit)
│   ├── homefinance-explore/SKILL.md              # Task 22 (edit)
│   └── homefinance-import-statement/SKILL.md     # Task 21 (new)
│
├── src/homefinance/
│   ├── db/
│   │   ├── migrations/0002-statement-batches.sql # Task 1
│   │   └── _upsert.py                            # Task 2 (extracted from sync.py)
│   ├── sources/
│   │   ├── ynab/sync.py                          # Task 2 (refactored to use _upsert.py)
│   │   └── statement/
│   │       ├── __init__.py                       # Task 3
│   │       ├── source.py                         # Task 14
│   │       ├── ingest.py                         # Tasks 10-13
│   │       ├── archive.py                        # Task 5
│   │       ├── templates.py                      # Task 4
│   │       └── parsers/
│   │           ├── __init__.py                   # Task 6 (registry)
│   │           ├── base.py                       # Task 3 (Protocol + ParsedStatement + exceptions)
│   │           ├── csv.py                        # Task 7
│   │           ├── ofx.py                        # Task 8 (OFX + QFX)
│   │           └── docling_pdf.py                # Task 9
│   ├── mcp_server/
│   │   ├── tools.py                              # Tasks 19-20
│   │   └── __main__.py                           # Tasks 19-20 (wrappers)
│   └── cli.py                                    # Tasks 15-18
│
├── scripts/record_docling_fixtures.py            # Task 24
│
├── tests/
│   ├── fixtures/
│   │   ├── statement/
│   │   │   ├── tiny.csv                          # Task 7
│   │   │   ├── tiny.ofx                          # Task 8
│   │   │   └── tiny.qfx                          # Task 8
│   │   └── docling/tiny-pdf/                     # Task 9 (captured Docling JSON)
│   ├── test_db_upsert.py                         # Task 2
│   ├── test_statement_parsers/
│   │   ├── __init__.py                           # Task 7
│   │   ├── test_csv.py                           # Task 7
│   │   ├── test_ofx.py                           # Task 8
│   │   └── test_docling_pdf.py                   # Task 9
│   ├── test_archive.py                           # Task 5
│   ├── test_templates.py                         # Task 4
│   ├── test_parser_registry.py                   # Task 6
│   ├── test_ingest.py                            # Tasks 10-13
│   ├── test_statement_source.py                  # Task 14
│   ├── test_cli.py                               # Tasks 15-18 (extended)
│   ├── test_mcp_tools.py                         # Tasks 19-20 (extended)
│   ├── test_lazy_import.py                       # Task 23
│   └── integration/
│       └── test_docling_live.py                  # Task 24 (manual-dispatch only)
│
└── docs/
    ├── quickstart.md                             # Task 26
    └── architecture.md                           # Task 26
```

---

## Task 1: Schema migration 0002 + `[ingest]` optional extra

**Goal:** Lock the schema delta (`statement_batches` table + two columns on `transactions`) and add the `[ingest]` optional dependency group. The SQL is verbatim from spec § 6.

**Files:**
- Create: `src/homefinance/db/migrations/0002-statement-batches.sql`
- Modify: `pyproject.toml` (append `[ingest]` extra)

- [ ] **Step 1: Create `src/homefinance/db/migrations/0002-statement-batches.sql`**

```sql
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
```

- [ ] **Step 2: Verify the migration applies cleanly**

Run:
```bash
~/.virtualenvs/homeFinance/bin/python -c "
import sqlite3, tempfile, pathlib
from homefinance.db.migrate import migrate
db = pathlib.Path(tempfile.mkdtemp()) / 'm2.sqlite3'
migrate(db)
with sqlite3.connect(db) as c:
    tables = {r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}
    cols   = {r[1] for r in c.execute('PRAGMA table_info(transactions)').fetchall()}
assert 'statement_batches' in tables, tables
assert {'status', 'batch_id'}.issubset(cols), cols
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 3: Add `[ingest]` extra to `pyproject.toml`**

Find the existing `[project.optional-dependencies]` block (it currently contains `dev = [...]`). Append a new key:

```toml
ingest = [
    "ofxtools>=0.10",
    "docling>=2.0",
]
```

After the edit, the section should contain BOTH `dev` and `ingest` keys (do not remove `dev`).

- [ ] **Step 4: Refresh the editable install to pull `[ingest]` deps**

Run: `~/.virtualenvs/homeFinance/bin/pip install -e ".[dev,ingest]"`

Expected: ends with `Successfully installed ... docling-2.x.x ... ofxtools-...`. This pulls PyTorch (~500 MB) on first install — may take several minutes. If install fails on a platform issue, report `BLOCKED` with the error rather than ad-hoc'ing around it.

- [ ] **Step 5: Verify the lean install path is still possible** (no regression — just sanity-check that `homefinance` imports without needing `docling`)

Run: `~/.virtualenvs/homeFinance/bin/python -c "import homefinance; print(homefinance.__version__)"`
Expected: `0.1.0`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/db/migrations/0002-statement-batches.sql pyproject.toml
git commit -m "feat(db): migration 0002 — statement_batches table + transactions.status/batch_id; add [ingest] extra"
```

---

## Task 2: Extract `db/_upsert.py` from `sources/ynab/sync.py`

**Goal:** Move SP1's four private upsert helpers (`_upsert_account`, `_upsert_category`, `_upsert_payee`, `_upsert_transaction`) and `_insert_subtransaction` plus the `_utcnow()` helper into a new shared module `src/homefinance/db/_upsert.py`. **No behavior change for YNAB.** The statement ingest path in later tasks reuses the same helpers.

**Files:**
- Create: `src/homefinance/db/_upsert.py`
- Modify: `src/homefinance/sources/ynab/sync.py` (replace helpers with re-exports / direct calls)
- Create: `tests/test_db_upsert.py` (focused tests of the extracted module so refactor is safe)

- [ ] **Step 1: Write failing test at `tests/test_db_upsert.py`** (asserts the new module exports the helpers, and that one of them does the right SQL on a fresh DB)

```python
"""Targeted tests for the extracted upsert helpers. End-to-end YNAB sync still
covers their integration; these tests pin the public-shape contract of the
module so the SP2 ingest path can rely on them too.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store


def test_module_exports_expected_helpers() -> None:
    from homefinance.db import _upsert

    for name in (
        "utcnow",
        "upsert_account",
        "upsert_category",
        "upsert_payee",
        "upsert_transaction",
        "insert_subtransaction",
    ):
        assert hasattr(_upsert, name), f"missing {name!r}"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "upsert.sqlite3"
    migrate(db)
    return Store.open(db)


def _seed_source(store: Store, source_id: str = "ynab:b") -> None:
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (source_id, "ynab", "test", None, datetime.now(timezone.utc).isoformat()),
    )


def test_upsert_account_inserts_then_updates(store: Store) -> None:
    from homefinance.db import _upsert
    from homefinance.sources.base import RemoteAccount

    a = RemoteAccount(
        external_id="acct-1", name="Checking", type="checking",
        on_budget=True, closed=False, deleted=False, currency="USD",
        cleared_balance_minor=10000, uncleared_balance_minor=0, balance_as_of=None,
    )

    with store.transaction():
        _seed_source(store)
        counters = {"accounts_touched": 0}
        _upsert.upsert_account(store, "ynab:b", a, counters)
        assert counters["accounts_touched"] == 1

    row = store.execute("SELECT name, cleared_balance_minor FROM accounts").fetchone()
    assert row["name"] == "Checking"
    assert row["cleared_balance_minor"] == 10000

    # Second call should update, not insert.
    a2 = RemoteAccount(
        external_id="acct-1", name="Renamed", type="checking",
        on_budget=True, closed=False, deleted=False, currency="USD",
        cleared_balance_minor=20000, uncleared_balance_minor=0, balance_as_of=None,
    )
    with store.transaction():
        counters2 = {"accounts_touched": 0}
        _upsert.upsert_account(store, "ynab:b", a2, counters2)
    row = store.execute("SELECT name, cleared_balance_minor FROM accounts").fetchone()
    assert row["name"] == "Renamed"
    assert row["cleared_balance_minor"] == 20000
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_db_upsert.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.db._upsert'`.

- [ ] **Step 3: Create `src/homefinance/db/_upsert.py`** by lifting the five private helpers from `src/homefinance/sources/ynab/sync.py` verbatim (rename leading underscore on the *function* names but keep the same signatures) and adding a small wrapper for `utcnow`:

```python
"""Shared upsert helpers used by every AccountSource adapter.

These were originally implemented inside ``sources/ynab/sync.py`` for SP1.
SP2 extracts them so the statement ingest path uses identical SQL discipline —
single atomic transaction, ``(source_id, external_id)`` UNIQUE upserts,
integer-money only. No behavior change vs the SP1 originals.
"""

from __future__ import annotations

from datetime import UTC, datetime

from homefinance.db.store import Store
from homefinance.sources.base import (
    RemoteAccount,
    RemoteCategory,
    RemotePayee,
    RemoteSubTxn,
    RemoteTransaction,
)
from homefinance.sources.ynab.ids import make_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def upsert_account(
    store: Store, source_id: str, a: RemoteAccount, counters: dict[str, int]
) -> None:
    acct_id = make_id(source_id, a.external_id)
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, "
        "closed, deleted, currency, cleared_balance_minor, uncleared_balance_minor, "
        "balance_as_of, last_synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, type = excluded.type, on_budget = excluded.on_budget, "
        "closed = excluded.closed, deleted = excluded.deleted, "
        "currency = excluded.currency, "
        "cleared_balance_minor = excluded.cleared_balance_minor, "
        "uncleared_balance_minor = excluded.uncleared_balance_minor, "
        "balance_as_of = excluded.balance_as_of, "
        "last_synced_at = excluded.last_synced_at",
        (
            acct_id, source_id, a.external_id, a.name, a.type, int(a.on_budget),
            int(a.closed), int(a.deleted), a.currency,
            a.cleared_balance_minor, a.uncleared_balance_minor,
            a.balance_as_of, utcnow(),
        ),
    )
    counters["accounts_touched"] = counters.get("accounts_touched", 0) + 1


def upsert_category(store: Store, source_id: str, c: RemoteCategory) -> None:
    cat_id = make_id(source_id, c.external_id)
    store.execute(
        "INSERT INTO categories (id, source_id, external_id, name, group_name, "
        "hidden, deleted) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, group_name = excluded.group_name, "
        "hidden = excluded.hidden, deleted = excluded.deleted",
        (cat_id, source_id, c.external_id, c.name, c.group_name,
         int(c.hidden), int(c.deleted)),
    )


def upsert_payee(store: Store, source_id: str, p: RemotePayee) -> None:
    payee_id = make_id(source_id, p.external_id)
    transfer_acct_id = (
        make_id(source_id, p.transfer_account_external_id)
        if p.transfer_account_external_id else None
    )
    store.execute(
        "INSERT INTO payees (id, source_id, external_id, name, transfer_account_id, "
        "deleted) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, transfer_account_id = excluded.transfer_account_id, "
        "deleted = excluded.deleted",
        (payee_id, source_id, p.external_id, p.name, transfer_acct_id, int(p.deleted)),
    )


def upsert_transaction(
    store: Store,
    source_id: str,
    t: RemoteTransaction,
    counters: dict[str, int],
    *,
    status: str = "confirmed",
    batch_id: int | None = None,
) -> None:
    """Insert or update one transaction row.

    The SP2 ingest path passes ``status='pending_review'`` and a ``batch_id``
    so staged rows are excluded from default analytics until confirmed.
    The YNAB path leaves the defaults (status='confirmed', batch_id NULL).
    """
    txn_id = make_id(source_id, t.external_id)
    acct_id = make_id(source_id, t.account_external_id)
    category_id = (
        make_id(source_id, t.category_external_id) if t.category_external_id else None
    )
    payee_id = (
        make_id(source_id, t.payee_external_id) if t.payee_external_id else None
    )
    transfer_acct_id = (
        make_id(source_id, t.transfer_account_external_id)
        if t.transfer_account_external_id else None
    )
    is_split_parent = 1 if t.subtransactions else 0

    existed = (
        store.execute("SELECT 1 FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        is not None
    )

    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "date = excluded.date, amount_minor = excluded.amount_minor, "
        "payee = excluded.payee, payee_id = excluded.payee_id, memo = excluded.memo, "
        "category_id = excluded.category_id, cleared = excluded.cleared, "
        "approved = excluded.approved, flag_color = excluded.flag_color, "
        "transfer_account_id = excluded.transfer_account_id, "
        "is_split_parent = excluded.is_split_parent, deleted = excluded.deleted, "
        "raw = excluded.raw, synced_at = excluded.synced_at, "
        "status = excluded.status, batch_id = excluded.batch_id",
        (
            txn_id, source_id, t.external_id, acct_id, t.date, t.amount_minor,
            t.currency, t.payee, payee_id, t.memo, category_id, t.cleared,
            int(t.approved), t.flag_color, t.import_id, transfer_acct_id,
            is_split_parent, int(t.deleted), None, utcnow(), status, batch_id,
        ),
    )

    if t.deleted:
        counters["deleted"] = counters.get("deleted", 0) + 1
    elif existed:
        counters["updated"] = counters.get("updated", 0) + 1
    else:
        counters["inserted"] = counters.get("inserted", 0) + 1

    if t.subtransactions:
        store.execute("DELETE FROM transactions WHERE parent_id = ?", (txn_id,))
        for i, sub in enumerate(t.subtransactions):
            insert_subtransaction(store, source_id, txn_id, acct_id, t, sub, i,
                                  status=status, batch_id=batch_id)


def insert_subtransaction(
    store: Store,
    source_id: str,
    parent_id: str,
    acct_id: str,
    parent: RemoteTransaction,
    sub: RemoteSubTxn,
    index: int,
    *,
    status: str = "confirmed",
    batch_id: int | None = None,
) -> None:
    sub_external = f"{parent.external_id}:sub:{index}"
    sub_id = make_id(source_id, sub_external)
    category_id = (
        make_id(source_id, sub.category_external_id) if sub.category_external_id else None
    )
    payee_id = (
        make_id(source_id, sub.payee_external_id) if sub.payee_external_id else None
    )
    transfer_acct_id = (
        make_id(source_id, sub.transfer_account_external_id)
        if sub.transfer_account_external_id else None
    )
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?)",
        (
            sub_id, source_id, sub_external, acct_id, parent.date, sub.amount_minor,
            parent.currency, parent.payee, payee_id, sub.memo, category_id,
            parent.cleared, int(parent.approved), parent.flag_color, parent.import_id,
            transfer_acct_id, parent_id, utcnow(), status, batch_id,
        ),
    )
```

- [ ] **Step 4: Replace the helpers in `src/homefinance/sources/ynab/sync.py`** with re-exported references. Open the file and:

1. Remove the local definitions of `_utcnow`, `_upsert_account`, `_upsert_category`, `_upsert_payee`, `_upsert_transaction`, `_insert_subtransaction` (everything from `def _utcnow()` through the end of `_insert_subtransaction`).
2. Replace all call-sites in `run_sync` (`_upsert_account(...)` → `_upsert.upsert_account(...)`; `_upsert_category(...)` → `_upsert.upsert_category(...)`; etc.) and `_utcnow()` → `_upsert.utcnow()`.
3. Add the import near the top: `from homefinance.db import _upsert`.

After the changes, `sync.py` should be roughly 80 lines shorter; `run_sync`'s logic stays identical.

- [ ] **Step 5: Run the targeted + full suite to confirm no regression**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_db_upsert.py tests/test_sync.py -v`
Expected: existing 7 sync tests still pass, plus 2 new `test_db_upsert` tests pass.

Run: `~/.virtualenvs/homeFinance/bin/pytest`
Expected: previously-passing count + 2 (now 83 total).

- [ ] **Step 6: Lint + typecheck**

Run: `~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format --check src tests && ~/.virtualenvs/homeFinance/bin/mypy`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/homefinance/db/_upsert.py src/homefinance/sources/ynab/sync.py tests/test_db_upsert.py
git commit -m "refactor(db): extract shared upsert helpers from ynab/sync.py to db/_upsert.py"
```

---

## Task 3: Statement adapter scaffolding — `StatementParser` Protocol + `ParsedStatement` + exception classes

**Goal:** Create the interface layer for SP2's adapter. Pure types — no I/O, no parsers yet. Mirrors how SP1 Task 8 staged the `AccountSource` seam before any parsers landed.

**Files:**
- Create: `src/homefinance/sources/statement/__init__.py` (empty docstring)
- Create: `src/homefinance/sources/statement/parsers/__init__.py` (empty docstring)
- Create: `src/homefinance/sources/statement/parsers/base.py`

This task ships no tests of its own; later tasks (Templates, parsers, registry, ingest) exercise the symbols defined here.

- [ ] **Step 1: Create `src/homefinance/sources/statement/__init__.py`**

```python
"""SP2 statement-ingestion adapter. Implements ``AccountSource`` for non-YNAB
accounts whose data lives in local statement files (CSV / OFX / QFX / PDF)."""
```

- [ ] **Step 2: Create `src/homefinance/sources/statement/parsers/__init__.py`**

```python
"""Parser registry and implementations. The registry dispatches by file
content (extension first, magic-byte fallback). Each parser is lazy-imported
so the lean install (``pip install homefinance``) never transitively loads
heavy deps such as ``docling`` or ``ofxtools``."""
```

- [ ] **Step 3: Create `src/homefinance/sources/statement/parsers/base.py`**

```python
"""``StatementParser`` Protocol + ``ParsedStatement`` dataclass + exception classes.

Pure interface layer. No I/O. Mirrors how SP1's ``sources/base.py`` staged
the ``AccountSource`` seam before any concrete implementations landed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from homefinance.sources.base import RemoteTransaction


# ---------------------------------------------------------------------------
# Exceptions — each has a stable ``code`` so MCP callers can branch on it.


class StatementIngestError(Exception):
    """Base class for any ingest-side failure. Carries a stable ``code``."""

    code: str = "statement_ingest_error"


class AccountNotConfigured(StatementIngestError):
    code = "account_not_configured"


class NoSuitableParser(StatementIngestError):
    code = "no_suitable_parser"


class TemplateNotFound(StatementIngestError):
    code = "template_not_found"


class ParseError(StatementIngestError):
    code = "parse_error"


class ArchiveFailed(StatementIngestError):
    code = "archive_failed"


class FileAlreadyIngested(StatementIngestError):
    code = "file_already_ingested"


# ---------------------------------------------------------------------------
# Data shapes


@dataclass(frozen=True, slots=True)
class ResolvedAccount:
    """Snapshot of the canonical account a statement is being ingested for."""

    source_id: str          # e.g. "statement:citi-cc"
    account_id: str         # e.g. "statement:citi-cc:account"
    nickname: str
    type: str               # canonical: checking | savings | credit_card | ...
    currency: str


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    """Everything a parser produced from one file."""

    statement_period_start: str | None        # YYYY-MM-DD
    statement_period_end: str | None
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    transactions: tuple[RemoteTransaction, ...]
    source_format: str                        # parser.name (e.g. "csv", "docling_pdf")
    parser_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol


@runtime_checkable
class StatementParser(Protocol):
    """A file-format-specific parser. Lazy-imported by the registry."""

    name: str  # 'csv' | 'ofx' | 'qfx' | 'docling_pdf'

    @classmethod
    def claims(cls, path: Path) -> bool:
        """True if this parser thinks it can handle this file (extension +
        light magic-byte sniffing). MUST NOT do expensive parsing here."""
        ...

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        """Parse the file. Raises ``ParseError``, ``TemplateNotFound``, etc."""
        ...
```

- [ ] **Step 4: Verify the module imports cleanly**

Run: `~/.virtualenvs/homeFinance/bin/python -c "from homefinance.sources.statement.parsers.base import StatementParser, ParsedStatement, ResolvedAccount, AccountNotConfigured, ParseError"`
Expected: exits 0 with no output.

- [ ] **Step 5: Lint + typecheck**

Run: `~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/sources/statement/__init__.py \
        src/homefinance/sources/statement/parsers/__init__.py \
        src/homefinance/sources/statement/parsers/base.py
git commit -m "feat(statement): StatementParser Protocol + ParsedStatement + exception classes"
```

---

## Task 4: Template loader

**Goal:** A small `load_template(source_id, config_dir) -> dict | None` that reads `<config_dir>/templates/<source_id>.toml` if present. Parsers consult this when needed (CSV always; OFX/QFX never; Docling PDF always).

**Files:**
- Create: `src/homefinance/sources/statement/templates.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write failing tests at `tests/test_templates.py`**

```python
from pathlib import Path

from homefinance.sources.statement.templates import load_template, templates_dir


def test_load_template_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_template("statement:nope", config_dir=tmp_path) is None


def test_load_template_reads_toml(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\n'
        'amount = "Amount"\n'
        'payee = "Description"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\n'
        'sign = "natural"\n'
    )
    tpl = load_template("statement:citi-cc", config_dir=tmp_path)
    assert tpl is not None
    assert tpl["parser"] == "csv"
    assert tpl["columns"]["date"] == "Transaction Date"
    assert tpl["options"]["sign"] == "natural"


def test_templates_dir_under_config_dir(tmp_path: Path) -> None:
    assert templates_dir(tmp_path) == tmp_path / "templates"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_templates.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.sources.statement.templates'`.

- [ ] **Step 3: Implement `src/homefinance/sources/statement/templates.py`**

```python
"""Per-account parser templates.

Templates live at ``<config_dir>/templates/<source_id>.toml``. ``config_dir``
is normally the resolved Config.config_path.parent (i.e. ``~/.homefinance/``
or its XDG equivalent). The ingest orchestrator passes the directory in;
this module does not call ``load_config()`` itself so tests stay hermetic.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def templates_dir(config_dir: Path) -> Path:
    return Path(config_dir) / "templates"


def load_template(source_id: str, *, config_dir: Path) -> dict[str, Any] | None:
    """Load the TOML template for the given source_id, or None if absent."""
    path = templates_dir(config_dir) / f"{source_id}.toml"
    if not path.exists():
        return None
    return tomllib.loads(path.read_text())
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_templates.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/templates.py tests/test_templates.py
git commit -m "feat(statement): TOML template loader"
```

---

## Task 5: Archive helper

**Goal:** `archive_file(path, source_id, file_hash, archive_dir) -> Path` copies the source file to `<archive_dir>/<source_id>/<file_hash>.<ext>` with the destination dir created at 0o700. Raises `ArchiveFailed` on any I/O failure **before** any caller has a chance to write to the DB.

**Files:**
- Create: `src/homefinance/sources/statement/archive.py`
- Create: `tests/test_archive.py`

- [ ] **Step 1: Write failing tests at `tests/test_archive.py`**

```python
import os
import stat
from pathlib import Path

import pytest

from homefinance.sources.statement.archive import archive_file
from homefinance.sources.statement.parsers.base import ArchiveFailed


def test_archive_file_copies_into_hash_named_path(tmp_path: Path) -> None:
    src = tmp_path / "statement.csv"
    src.write_text("some content")
    archive_root = tmp_path / "archive"

    dst = archive_file(src, source_id="statement:citi-cc",
                       file_hash="abc123", archive_dir=archive_root)
    assert dst == archive_root / "statement:citi-cc" / "abc123.csv"
    assert dst.exists()
    assert dst.read_text() == "some content"


def test_archive_file_creates_parent_dir_with_0o700(tmp_path: Path) -> None:
    src = tmp_path / "x.csv"
    src.write_text("hello")
    archive_root = tmp_path / "archive"

    dst = archive_file(src, source_id="statement:citi-cc",
                       file_hash="abc", archive_dir=archive_root)
    parent_mode = stat.S_IMODE(os.stat(dst.parent).st_mode)
    assert parent_mode == 0o700


def test_archive_file_raises_on_missing_source(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    with pytest.raises(ArchiveFailed):
        archive_file(tmp_path / "missing.csv", source_id="statement:s",
                     file_hash="h", archive_dir=archive_root)


def test_archive_file_preserves_original_extension(tmp_path: Path) -> None:
    pdf = tmp_path / "statement.PDF"  # uppercase
    pdf.write_bytes(b"%PDF-1.4 ...")
    dst = archive_file(pdf, source_id="statement:wells",
                       file_hash="h", archive_dir=tmp_path / "archive")
    assert dst.suffix == ".PDF"  # preserve case
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_archive.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/homefinance/sources/statement/archive.py`**

```python
"""Copy source files into the local archive.

Default layout: ``<archive_dir>/<source_id>/<file_hash><original_ext>``.
The destination directory is created with mode 0o700 (consistent with the
0o700 stance the SP1 config-write helper takes). Any failure raises
``ArchiveFailed`` **before** the ingest orchestrator touches the DB.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from homefinance.sources.statement.parsers.base import ArchiveFailed


def archive_file(
    source: Path, *, source_id: str, file_hash: str, archive_dir: Path
) -> Path:
    source = Path(source)
    if not source.exists():
        raise ArchiveFailed(f"source file not found: {source}")

    dest_dir = Path(archive_dir) / source_id
    try:
        dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # ``mkdir(mode=...)`` honors umask; force-tighten after creation.
        os.chmod(dest_dir, 0o700)
    except OSError as e:
        raise ArchiveFailed(f"could not create archive dir {dest_dir}: {e}") from e

    dest = dest_dir / f"{file_hash}{source.suffix}"
    try:
        shutil.copy2(source, dest)
    except OSError as e:
        raise ArchiveFailed(f"could not copy {source} to {dest}: {e}") from e

    return dest
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_archive.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/archive.py tests/test_archive.py
git commit -m "feat(statement): archive helper with 0o700 dir + ArchiveFailed on I/O errors"
```

Expected: `4 passed`.

---

## Task 6: Parser registry

**Goal:** A small module-level registry of `(extension, dotted_path)` pairs and a `find_parser(path)` dispatch function. Parsers are **lazy-imported** at dispatch time so the lean install never transitively loads heavy deps.

**Files:**
- Modify: `src/homefinance/sources/statement/parsers/__init__.py` (append registry + find_parser)
- Create: `tests/test_parser_registry.py`

- [ ] **Step 1: Write failing tests at `tests/test_parser_registry.py`**

```python
import sys
from pathlib import Path

import pytest

from homefinance.sources.statement.parsers import (
    _REGISTRY,
    find_parser,
)
from homefinance.sources.statement.parsers.base import NoSuitableParser


def test_find_parser_raises_when_registry_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "homefinance.sources.statement.parsers._REGISTRY",
        [],
    )
    p = tmp_path / "x.csv"
    p.write_text("")
    with pytest.raises(NoSuitableParser, match="no parser"):
        find_parser(p)


def test_find_parser_dispatches_by_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Stand up a stub parser module on the fly.
    stub = type(sys)("_test_stub_parser")

    class StubParser:
        name = "stub"

        @classmethod
        def claims(cls, path: Path) -> bool:
            return path.suffix == ".stub"

        @classmethod
        def parse(cls, path, account, template):  # pragma: no cover
            ...

    stub.StubParser = StubParser
    monkeypatch.setitem(sys.modules, "_test_stub_parser", stub)
    monkeypatch.setattr(
        "homefinance.sources.statement.parsers._REGISTRY",
        [(".stub", "_test_stub_parser:StubParser")],
    )

    p = tmp_path / "f.stub"
    p.write_text("")
    parser_cls = find_parser(p)
    assert parser_cls is StubParser


def test_registry_starts_empty_until_parsers_register() -> None:
    # The base module ships an empty registry; subsequent parser tasks
    # append to it. Until Task 7 (CSV) lands, _REGISTRY is empty.
    assert _REGISTRY == []
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_parser_registry.py -v`
Expected: `ImportError` on `_REGISTRY` / `find_parser`.

- [ ] **Step 3: Replace `src/homefinance/sources/statement/parsers/__init__.py`** with:

```python
"""Parser registry and dispatch.

Each parser registers itself by appending a ``(extension, dotted_path)``
tuple to ``_REGISTRY``. ``find_parser()`` walks the registry, importing the
target module lazily — the lean install (``pip install homefinance``) never
transitively loads ``docling`` or ``ofxtools``.

Dotted path format: ``module.path:ClassName`` (matches Python entry-point
conventions).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from homefinance.sources.statement.parsers.base import (
    NoSuitableParser,
    StatementParser,
)


# Populated by each parser module via ``register(extension, dotted_path)``
# in subsequent tasks. Tests may monkeypatch this list.
_REGISTRY: list[tuple[str, str]] = []


def register(extension: str, dotted_path: str) -> None:
    """Register a parser for files with the given extension.

    Idempotent: re-registering the same (extension, path) pair is a no-op
    so re-imports during testing don't double-register.
    """
    pair = (extension.lower(), dotted_path)
    if pair not in _REGISTRY:
        _REGISTRY.append(pair)


def find_parser(path: Path) -> type[StatementParser]:
    """Return the parser class that claims this file, or raise NoSuitableParser."""
    ext = Path(path).suffix.lower()
    for parser_ext, dotted in _REGISTRY:
        if ext != parser_ext:
            continue
        module_name, _, cls_name = dotted.partition(":")
        module = importlib.import_module(module_name)
        cls = getattr(module, cls_name)
        if cls.claims(Path(path)):
            return cls
    raise NoSuitableParser(
        f"no parser knows {str(path)!r} (saw extension {ext!r}). "
        "Supported: csv, ofx, qfx, pdf."
    )
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_parser_registry.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/parsers/__init__.py tests/test_parser_registry.py
git commit -m "feat(statement): lazy-import parser registry"
```

Expected: `3 passed`.

---

## Task 7: CSV parser

**Goal:** Template-driven CSV parser. Stdlib-only (no `[ingest]` dep needed). Refuses to parse without a template. Registers itself with the registry on import.

**Files:**
- Create: `src/homefinance/sources/statement/parsers/csv.py`
- Create: `tests/test_statement_parsers/__init__.py` (empty docstring)
- Create: `tests/test_statement_parsers/test_csv.py`
- Create: `tests/fixtures/statement/tiny.csv`

- [ ] **Step 1: Create `tests/fixtures/statement/tiny.csv`**

```csv
Transaction Date,Amount,Description,Notes
06/01/2026,-45.67,Trader Joe's,weekly shop
06/02/2026,-50.00,Shell,gas + snacks
06/03/2026,-20.00,Payment ,pay down card
```

(Note: trailing space on "Payment " is intentional to exercise whitespace stripping.)

- [ ] **Step 2: Create `tests/test_statement_parsers/__init__.py`** (empty docstring marker)

```python
"""Per-parser unit tests."""
```

- [ ] **Step 3: Write failing tests at `tests/test_statement_parsers/test_csv.py`**

```python
from pathlib import Path

import pytest

from homefinance.sources.statement.parsers.base import (
    ParseError,
    ResolvedAccount,
    TemplateNotFound,
)
from homefinance.sources.statement.parsers.csv import CSVParser

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "statement"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:citi-cc",
        account_id="statement:citi-cc:account",
        nickname="citi-cc",
        type="credit_card",
        currency="USD",
    )


def _natural_template() -> dict:
    return {
        "parser": "csv",
        "columns": {"date": "Transaction Date", "amount": "Amount",
                    "payee": "Description", "memo": "Notes"},
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }


def test_claims_csv_by_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.CSV"
    p.write_text("")
    assert CSVParser.claims(p) is True
    assert CSVParser.claims(tmp_path / "x.pdf") is False


def test_parse_tiny_csv_with_template() -> None:
    parsed = CSVParser.parse(FIX / "tiny.csv", _account(), _natural_template())
    assert parsed.source_format == "csv"
    assert len(parsed.transactions) == 3
    first = parsed.transactions[0]
    assert first.date == "2026-06-01"
    assert first.amount_minor == -4567
    assert first.payee == "Trader Joe's"
    assert first.memo == "weekly shop"
    # Whitespace stripped on payee:
    assert parsed.transactions[2].payee == "Payment"


def test_parse_without_template_raises() -> None:
    with pytest.raises(TemplateNotFound):
        CSVParser.parse(FIX / "tiny.csv", _account(), None)


def test_parse_missing_required_column_raises() -> None:
    template = _natural_template()
    template["columns"]["amount"] = "DoesNotExist"
    with pytest.raises(ParseError, match="column.*DoesNotExist"):
        CSVParser.parse(FIX / "tiny.csv", _account(), template)


def test_sign_invert_flips_amounts() -> None:
    template = _natural_template()
    template["options"]["sign"] = "invert"
    parsed = CSVParser.parse(FIX / "tiny.csv", _account(), template)
    # Originally -45.67 -> +45.67 after invert.
    assert parsed.transactions[0].amount_minor == 4567
```

- [ ] **Step 4: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_csv.py -v`
Expected: `ModuleNotFoundError` on `homefinance.sources.statement.parsers.csv`.

- [ ] **Step 5: Implement `src/homefinance/sources/statement/parsers/csv.py`**

```python
"""Template-driven CSV parser. Stdlib only."""

from __future__ import annotations

import csv as _csv
from datetime import datetime
from pathlib import Path
from typing import Any

from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.parsers import register
from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ParseError,
    ResolvedAccount,
    TemplateNotFound,
)


class CSVParser:
    name = "csv"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".csv"

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        if template is None:
            raise TemplateNotFound(
                f"no column-mapping template for {account.source_id!r}; "
                f"create one at <config_dir>/templates/{account.source_id}.toml"
            )
        cols = template.get("columns") or {}
        opts = template.get("options") or {}
        date_fmt = opts.get("date_format", "%Y-%m-%d")
        sign = opts.get("sign", "natural")

        date_col = cols.get("date")
        amount_col = cols.get("amount")
        if not date_col or not amount_col:
            raise ParseError(
                "template missing required columns: 'date' and 'amount' are mandatory"
            )

        payee_col = cols.get("payee")
        memo_col = cols.get("memo")

        transactions: list[RemoteTransaction] = []
        with Path(path).open(newline="", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            if reader.fieldnames is None or date_col not in reader.fieldnames:
                raise ParseError(f"column {date_col!r} not found in CSV header")
            if amount_col not in reader.fieldnames:
                raise ParseError(f"column {amount_col!r} not found in CSV header")
            for i, row in enumerate(reader):
                try:
                    canonical_date = datetime.strptime(row[date_col], date_fmt).date().isoformat()
                except ValueError as e:
                    raise ParseError(f"row {i + 2}: bad date {row[date_col]!r}: {e}") from e
                amount_str = (row[amount_col] or "").replace(",", "").replace("$", "").strip()
                if not amount_str:
                    raise ParseError(f"row {i + 2}: empty amount")
                try:
                    amount_minor = int(round(float(amount_str) * 100))
                except ValueError as e:
                    raise ParseError(f"row {i + 2}: bad amount {amount_str!r}: {e}") from e
                if sign == "invert":
                    amount_minor = -amount_minor
                payee = (row.get(payee_col, "").strip() or None) if payee_col else None
                memo = (row.get(memo_col, "").strip() or None) if memo_col else None
                # Synthetic external_id is assigned by the orchestrator; use a
                # placeholder here that the orchestrator overwrites.
                transactions.append(RemoteTransaction(
                    external_id="",
                    account_external_id="account",
                    date=canonical_date,
                    amount_minor=amount_minor,
                    currency=account.currency,
                    payee=payee,
                    payee_external_id=None,
                    memo=memo,
                    category_external_id=None,
                    cleared=None,
                    approved=True,
                    flag_color=None,
                    import_id=None,
                    transfer_account_external_id=None,
                    deleted=False,
                ))

        return ParsedStatement(
            statement_period_start=None,
            statement_period_end=None,
            opening_balance_minor=None,
            closing_balance_minor=None,
            transactions=tuple(transactions),
            source_format=cls.name,
            parser_metadata={"row_count": len(transactions)},
        )


# Register on import. The orchestrator imports this module lazily via the
# registry, so this side effect only fires when CSV is actually needed.
register(".csv", "homefinance.sources.statement.parsers.csv:CSVParser")
```

- [ ] **Step 6: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_csv.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/parsers/csv.py \
        tests/test_statement_parsers/__init__.py \
        tests/test_statement_parsers/test_csv.py \
        tests/fixtures/statement/tiny.csv
git commit -m "feat(statement): template-driven CSV parser; stdlib-only"
```

Expected: `5 passed`.

---

## Task 8: OFX + QFX parser

**Goal:** One module, two parser classes (`OFXParser` claims `.ofx`, `QFXParser` claims `.qfx`). Both use `ofxtools` to parse — no template needed since OFX is self-describing. Registers both with the registry on import.

**Files:**
- Create: `src/homefinance/sources/statement/parsers/ofx.py`
- Create: `tests/test_statement_parsers/test_ofx.py`
- Create: `tests/fixtures/statement/tiny.ofx`

- [ ] **Step 1: Create `tests/fixtures/statement/tiny.ofx`** (minimal valid OFX 1.0.3 / SGML)

```
OFXHEADER:100
DATA:OFXSGML
VERSION:103
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20260603120000</DTSERVER><LANGUAGE>ENG</LANGUAGE></SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>USD</CURDEF>
<BANKACCTFROM><BANKID>123</BANKID><ACCTID>456</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260601000000</DTSTART><DTEND>20260603235959</DTEND>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260601<TRNAMT>-45.67<FITID>T1<NAME>Trader Joe's<MEMO>weekly shop</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260602<TRNAMT>-50.00<FITID>T2<NAME>Shell</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>1234.56<DTASOF>20260603120000</DTASOF></LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
```

- [ ] **Step 2: Copy the OFX fixture to QFX** (QFX is OFX with a different extension; ofxtools handles both transparently)

Run: `cp tests/fixtures/statement/tiny.ofx tests/fixtures/statement/tiny.qfx`

- [ ] **Step 3: Write failing tests at `tests/test_statement_parsers/test_ofx.py`**

```python
from pathlib import Path

from homefinance.sources.statement.parsers.base import ResolvedAccount
from homefinance.sources.statement.parsers.ofx import OFXParser, QFXParser

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "statement"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:test",
        account_id="statement:test:account",
        nickname="test",
        type="checking",
        currency="USD",
    )


def test_ofx_claims_ofx_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.OFX"
    p.write_text("")
    assert OFXParser.claims(p) is True
    assert OFXParser.claims(tmp_path / "x.qfx") is False


def test_qfx_claims_qfx_extension(tmp_path: Path) -> None:
    assert QFXParser.claims(tmp_path / "x.qfx") is True
    assert QFXParser.claims(tmp_path / "x.ofx") is False


def test_parse_tiny_ofx_no_template_needed() -> None:
    parsed = OFXParser.parse(FIX / "tiny.ofx", _account(), template=None)
    assert parsed.source_format == "ofx"
    assert len(parsed.transactions) == 2
    first = parsed.transactions[0]
    assert first.date == "2026-06-01"
    assert first.amount_minor == -4567
    assert first.payee == "Trader Joe's"
    assert first.memo == "weekly shop"


def test_parse_qfx_same_as_ofx() -> None:
    parsed = QFXParser.parse(FIX / "tiny.qfx", _account(), template=None)
    assert parsed.source_format == "qfx"
    assert len(parsed.transactions) == 2
```

- [ ] **Step 4: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_ofx.py -v`
Expected: import errors.

- [ ] **Step 5: Implement `src/homefinance/sources/statement/parsers/ofx.py`**

```python
"""OFX + QFX parser via ``ofxtools`` (lazy import; gated to [ingest] extra)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.parsers import register
from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ParseError,
    ResolvedAccount,
)


def _parse_with_ofxtools(path: Path, account: ResolvedAccount, format_name: str) -> ParsedStatement:
    # Lazy import so the lean install never touches ofxtools.
    try:
        from ofxtools.Parser import OFXTree  # type: ignore[import-not-found]
    except ImportError as e:
        raise ParseError(
            "ofxtools is required for OFX/QFX parsing. "
            "Install with: pip install 'homefinance[ingest]'"
        ) from e

    tree = OFXTree()
    try:
        tree.parse(str(path))
    except Exception as e:
        raise ParseError(f"could not parse {path} as {format_name}: {e}") from e
    ofx = tree.convert()

    statements = list(ofx.statements)
    if not statements:
        raise ParseError(f"no statement found in {path}")
    stmt = statements[0]

    txns: list[RemoteTransaction] = []
    for raw in (stmt.transactions or []):
        amount = raw.trnamt
        amount_minor = int(round(float(amount) * 100))
        date_str = raw.dtposted.date().isoformat() if raw.dtposted else ""
        payee = (raw.name or "").strip() or None
        memo = (raw.memo or "").strip() or None
        if not date_str:
            raise ParseError(f"transaction missing date in {path}")
        txns.append(RemoteTransaction(
            external_id="",
            account_external_id="account",
            date=date_str,
            amount_minor=amount_minor,
            currency=account.currency,
            payee=payee,
            payee_external_id=None,
            memo=memo,
            category_external_id=None,
            cleared=None,
            approved=True,
            flag_color=None,
            import_id=str(raw.fitid) if raw.fitid else None,
            transfer_account_external_id=None,
            deleted=False,
        ))

    ledger_bal = getattr(stmt, "ledgerbal", None)
    closing = int(round(float(ledger_bal.balamt) * 100)) if ledger_bal is not None else None

    period_start = stmt.transactions.dtstart.date().isoformat() if stmt.transactions and stmt.transactions.dtstart else None
    period_end = stmt.transactions.dtend.date().isoformat() if stmt.transactions and stmt.transactions.dtend else None

    return ParsedStatement(
        statement_period_start=period_start,
        statement_period_end=period_end,
        opening_balance_minor=None,   # OFX 1.x rarely emits opening balance
        closing_balance_minor=closing,
        transactions=tuple(txns),
        source_format=format_name,
        parser_metadata={"row_count": len(txns)},
    )


class OFXParser:
    name = "ofx"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".ofx"

    @classmethod
    def parse(cls, path: Path, account: ResolvedAccount, template: dict[str, Any] | None) -> ParsedStatement:
        return _parse_with_ofxtools(Path(path), account, cls.name)


class QFXParser:
    name = "qfx"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".qfx"

    @classmethod
    def parse(cls, path: Path, account: ResolvedAccount, template: dict[str, Any] | None) -> ParsedStatement:
        return _parse_with_ofxtools(Path(path), account, cls.name)


register(".ofx", "homefinance.sources.statement.parsers.ofx:OFXParser")
register(".qfx", "homefinance.sources.statement.parsers.ofx:QFXParser")
```

- [ ] **Step 6: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_ofx.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/parsers/ofx.py \
        tests/test_statement_parsers/test_ofx.py \
        tests/fixtures/statement/tiny.ofx \
        tests/fixtures/statement/tiny.qfx
git commit -m "feat(statement): OFX/QFX parser via ofxtools (lazy-imported)"
```

Expected: `4 passed`.

---

## Task 9: Docling PDF parser + fake test double

**Goal:** Real `DoclingPDFParser` (lazy-imports `docling`), a free function `_map_cells_to_transactions(cells, account, template)` that contains the post-Docling logic, and a `FakeDoclingPDFParser` test double that consumes pre-captured Docling-output JSON for CI-friendly tests. Real Docling is exercised only in `tests/integration/` (Task 24).

**Files:**
- Create: `src/homefinance/sources/statement/parsers/docling_pdf.py`
- Create: `tests/test_statement_parsers/test_docling_pdf.py`
- Create: `tests/fixtures/docling/tiny-pdf/cells.json` (sanitized stand-in for Docling output)

- [ ] **Step 1: Create `tests/fixtures/docling/tiny-pdf/cells.json`** — hand-crafted Docling-shape output for a tiny statement (3 transactions, opening + closing balance, header row + body)

```json
{
  "statement_period_start": "2026-06-01",
  "statement_period_end": "2026-06-30",
  "opening_balance_minor": 1234560,
  "closing_balance_minor": 1100000,
  "table": {
    "header": ["Date", "Description", "Amount"],
    "rows": [
      ["06/01/2026", "Trader Joe's", "-45.67"],
      ["06/02/2026", "Shell", "-50.00"],
      ["06/03/2026", "Refund", "10.00"]
    ]
  }
}
```

- [ ] **Step 2: Write failing tests at `tests/test_statement_parsers/test_docling_pdf.py`**

```python
import json
import sys
from pathlib import Path

import pytest

from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ResolvedAccount,
    TemplateNotFound,
)
from homefinance.sources.statement.parsers.docling_pdf import (
    DoclingPDFParser,
    FakeDoclingPDFParser,
    _map_cells_to_transactions,
)

CELLS = Path(__file__).resolve().parent.parent / "fixtures" / "docling" / "tiny-pdf" / "cells.json"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:wells",
        account_id="statement:wells:account",
        nickname="wells",
        type="checking",
        currency="USD",
    )


def _template() -> dict:
    return {
        "parser": "docling_pdf",
        "table": {"header_match": ["Date", "Description", "Amount"]},
        "columns": {"date": 0, "payee": 1, "amount": 2},
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }


def test_claims_pdf_by_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.PDF"
    p.write_bytes(b"%PDF-1.4")
    assert DoclingPDFParser.claims(p) is True
    assert DoclingPDFParser.claims(tmp_path / "x.csv") is False


def test_map_cells_produces_transactions() -> None:
    cells = json.loads(CELLS.read_text())
    parsed = _map_cells_to_transactions(cells, _account(), _template())
    assert isinstance(parsed, ParsedStatement)
    assert parsed.source_format == "docling_pdf"
    assert len(parsed.transactions) == 3
    assert parsed.transactions[0].date == "2026-06-01"
    assert parsed.transactions[0].amount_minor == -4567
    assert parsed.opening_balance_minor == 1234560
    assert parsed.closing_balance_minor == 1100000


def test_map_cells_without_template_raises() -> None:
    cells = json.loads(CELLS.read_text())
    with pytest.raises(TemplateNotFound):
        _map_cells_to_transactions(cells, _account(), None)


def test_fake_parser_reads_json_fixture() -> None:
    parsed = FakeDoclingPDFParser.parse(CELLS, _account(), _template())
    assert len(parsed.transactions) == 3
    assert parsed.transactions[1].payee == "Shell"


def test_docling_pdf_module_does_not_import_docling_at_import_time() -> None:
    # Reload the module to test fresh
    mod = "homefinance.sources.statement.parsers.docling_pdf"
    if mod in sys.modules:
        del sys.modules[mod]
    leaks_before = {m for m in sys.modules if "docling" in m}
    import homefinance.sources.statement.parsers.docling_pdf  # noqa: F401
    leaks_after = {m for m in sys.modules if "docling" in m}
    assert leaks_after - leaks_before == set(), \
        f"importing docling_pdf eagerly loaded docling: {leaks_after - leaks_before}"
```

- [ ] **Step 3: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_docling_pdf.py -v`
Expected: import errors.

- [ ] **Step 4: Implement `src/homefinance/sources/statement/parsers/docling_pdf.py`**

```python
"""Docling-based PDF parser.

The real ``DoclingPDFParser.parse()`` lazy-imports ``docling`` only when
actually dispatched. The post-Docling logic — taking a ``cells`` dict
(header + rows + balances) and producing a ``ParsedStatement`` — lives in
the free function ``_map_cells_to_transactions``. Tests bypass Docling via
``FakeDoclingPDFParser`` which loads pre-captured ``cells.json`` directly.

CI never imports ``docling``; see the lazy-import enforcement test in
``tests/test_lazy_import.py``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.parsers import register
from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ParseError,
    ResolvedAccount,
    TemplateNotFound,
)


def _map_cells_to_transactions(
    cells: dict[str, Any],
    account: ResolvedAccount,
    template: dict[str, Any] | None,
) -> ParsedStatement:
    if template is None:
        raise TemplateNotFound(
            f"no layout template for {account.source_id!r}; "
            f"create one at <config_dir>/templates/{account.source_id}.toml"
        )

    cols = template.get("columns") or {}
    opts = template.get("options") or {}
    date_fmt = opts.get("date_format", "%Y-%m-%d")
    sign = opts.get("sign", "natural")

    table = cells.get("table") or {}
    rows = table.get("rows") or []

    if "date" not in cols or "amount" not in cols:
        raise ParseError("template missing required column indices: 'date' and 'amount'")
    date_idx = int(cols["date"])
    amount_idx = int(cols["amount"])
    payee_idx = cols.get("payee")
    memo_idx = cols.get("memo")

    transactions: list[RemoteTransaction] = []
    for i, row in enumerate(rows):
        try:
            date_str = datetime.strptime(row[date_idx], date_fmt).date().isoformat()
        except (IndexError, ValueError) as e:
            raise ParseError(f"row {i}: bad date {row[date_idx]!r}: {e}") from e
        amount_str = str(row[amount_idx]).replace(",", "").replace("$", "").strip()
        try:
            amount_minor = int(round(float(amount_str) * 100))
        except ValueError as e:
            raise ParseError(f"row {i}: bad amount {amount_str!r}: {e}") from e
        if sign == "invert":
            amount_minor = -amount_minor

        payee = (str(row[payee_idx]).strip() or None) if payee_idx is not None and len(row) > payee_idx else None
        memo = (str(row[memo_idx]).strip() or None) if memo_idx is not None and len(row) > memo_idx else None

        transactions.append(RemoteTransaction(
            external_id="",
            account_external_id="account",
            date=date_str,
            amount_minor=amount_minor,
            currency=account.currency,
            payee=payee,
            payee_external_id=None,
            memo=memo,
            category_external_id=None,
            cleared=None,
            approved=True,
            flag_color=None,
            import_id=None,
            transfer_account_external_id=None,
            deleted=False,
        ))

    return ParsedStatement(
        statement_period_start=cells.get("statement_period_start"),
        statement_period_end=cells.get("statement_period_end"),
        opening_balance_minor=cells.get("opening_balance_minor"),
        closing_balance_minor=cells.get("closing_balance_minor"),
        transactions=tuple(transactions),
        source_format="docling_pdf",
        parser_metadata={"row_count": len(transactions)},
    )


def _extract_cells_with_docling(path: Path) -> dict[str, Any]:
    """Real Docling path. Imports docling lazily."""
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except ImportError as e:
        raise ParseError(
            "docling is required for PDF parsing. "
            "Install with: pip install 'homefinance[ingest]'"
        ) from e

    converter = DocumentConverter()
    result = converter.convert(str(path))
    # Real Docling returns a richly structured doc; for now collapse to the
    # same {header, rows} shape the fake consumes. Production wiring of
    # tables-and-balances is exercised only in tests/integration/.
    table = next(iter(result.document.tables or []), None)
    return {
        "statement_period_start": None,
        "statement_period_end": None,
        "opening_balance_minor": None,
        "closing_balance_minor": None,
        "table": {
            "header": [c.text for c in table.header] if table and table.header else [],
            "rows": [[c.text for c in r] for r in (table.rows or [])] if table else [],
        },
    }


class DoclingPDFParser:
    name = "docling_pdf"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    @classmethod
    def parse(cls, path: Path, account: ResolvedAccount, template: dict[str, Any] | None) -> ParsedStatement:
        cells = _extract_cells_with_docling(Path(path))
        return _map_cells_to_transactions(cells, account, template)


class FakeDoclingPDFParser:
    """Test double: reads a pre-captured ``cells.json`` and runs the same
    post-Docling mapping logic as the real parser."""

    name = "docling_pdf"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() in {".pdf", ".json"}

    @classmethod
    def parse(cls, path: Path, account: ResolvedAccount, template: dict[str, Any] | None) -> ParsedStatement:
        cells = json.loads(Path(path).read_text())
        return _map_cells_to_transactions(cells, account, template)


register(".pdf", "homefinance.sources.statement.parsers.docling_pdf:DoclingPDFParser")
```

- [ ] **Step 5: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_parsers/test_docling_pdf.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/parsers/docling_pdf.py \
        tests/test_statement_parsers/test_docling_pdf.py \
        tests/fixtures/docling/tiny-pdf/cells.json
git commit -m "feat(statement): Docling PDF parser (lazy import) + FakeDoclingPDFParser test double"
```

Expected: `5 passed`.

---

## Task 10: Account registration + small ingest helpers

**Goal:** Stand up `src/homefinance/sources/statement/ingest.py` with the small leaf functions the orchestrator (T11) will compose: `register_account()`, `resolve_account()`, `compute_file_hash()`, `row_external_id()`, `reconcile()`, and the `BatchPreview` dataclass. All pure / single-purpose; each gets its own test.

**Files:**
- Create: `src/homefinance/sources/statement/ingest.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Write failing tests at `tests/test_ingest.py`**

```python
from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.statement.ingest import (
    AccountAlreadyRegistered,
    compute_file_hash,
    reconcile,
    register_account,
    resolve_account,
    row_external_id,
)
from homefinance.sources.statement.parsers.base import AccountNotConfigured


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "ingest.sqlite3"
    migrate(db)
    return Store.open(db)


def test_register_account_creates_source_and_account_rows(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card",
                     currency="USD", display_name="Citi Credit Card")
    src = store.execute("SELECT id, kind, nickname FROM sources").fetchone()
    assert src["id"] == "statement:citi-cc"
    assert src["kind"] == "statement"
    assert src["nickname"] == "Citi Credit Card"

    acct = store.execute("SELECT id, source_id, external_id, name, type FROM accounts").fetchone()
    assert acct["id"] == "statement:citi-cc:account"
    assert acct["source_id"] == "statement:citi-cc"
    assert acct["external_id"] == "account"
    assert acct["name"] == "Citi Credit Card"
    assert acct["type"] == "credit_card"


def test_register_account_twice_raises(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    with pytest.raises(AccountAlreadyRegistered):
        register_account(store, nickname="citi-cc", type="credit_card", currency="USD")


def test_resolve_account_returns_resolved_account(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    ra = resolve_account(store, "citi-cc")
    assert ra.source_id == "statement:citi-cc"
    assert ra.account_id == "statement:citi-cc:account"
    assert ra.type == "credit_card"
    assert ra.currency == "USD"


def test_resolve_account_unknown_nickname_raises(store: Store) -> None:
    with pytest.raises(AccountNotConfigured, match="nope"):
        resolve_account(store, "nope")


def test_compute_file_hash_is_stable(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    a.write_bytes(b"hello world")
    h1 = compute_file_hash(a)
    h2 = compute_file_hash(a)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    b = tmp_path / "b.bin"
    b.write_bytes(b"hello world!")
    assert compute_file_hash(b) != h1


def test_row_external_id_collides_for_identical_rows() -> None:
    a = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", None)
    b = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", None)
    assert a == b
    c = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", "diff memo")
    assert c != a


def test_reconcile_ok_when_balances_match() -> None:
    status, drift = reconcile(opening=100000, closing=99500, txn_total=-500)
    assert status == "ok"
    assert drift is None


def test_reconcile_drift_when_mismatch() -> None:
    status, drift = reconcile(opening=100000, closing=99500, txn_total=-450)
    assert status == "drift"
    assert drift == 50  # actual(-450) - expected(-500)


def test_reconcile_na_when_balance_missing() -> None:
    status, drift = reconcile(opening=None, closing=99500, txn_total=-500)
    assert status == "n/a"
    assert drift is None
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.sources.statement.ingest'`.

- [ ] **Step 3: Implement `src/homefinance/sources/statement/ingest.py`**

```python
"""Statement ingest orchestrator and its helpers.

This module is built up across Tasks 10-12 of the SP2 plan:
- Task 10: small helpers + register/resolve account + BatchPreview shape
- Task 11: ``ingest_file()`` — parse + reconcile + atomic stage
- Task 12: ``confirm_batch()``, ``reject_batch()``, ``list_batches()``
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homefinance.db.store import Store
from homefinance.sources.statement.parsers.base import (
    AccountNotConfigured,
    ResolvedAccount,
)


# ---------------------------------------------------------------------------
# Errors specific to this layer


class AccountAlreadyRegistered(Exception):
    code = "account_already_registered"


# ---------------------------------------------------------------------------
# BatchPreview — what ingest_file() returns to its caller


@dataclass(frozen=True, slots=True)
class TxnPreview:
    date: str
    amount_minor: int
    payee: str | None
    memo: str | None


@dataclass(frozen=True, slots=True)
class BatchPreview:
    batch_id: int
    source_id: str
    txn_count: int
    reconciliation_status: str          # 'ok' | 'drift' | 'n/a'
    drift_minor: int | None
    statement_period_start: str | None
    statement_period_end: str | None
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    file_path_archive: str | None
    first_transactions: tuple[TxnPreview, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def compute_file_hash(path: Path) -> str:
    """SHA-256 of the file content, hex-encoded."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def row_external_id(
    account_id: str,
    date: str,
    amount_minor: int,
    payee: str | None,
    memo: str | None,
) -> str:
    """Synthetic 16-hex-char external_id for a parsed statement row."""
    payload = f"{account_id}|{date}|{amount_minor}|{payee or ''}|{memo or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def reconcile(
    *, opening: int | None, closing: int | None, txn_total: int
) -> tuple[str, int | None]:
    """Return (status, drift) where status ∈ {'ok','drift','n/a'} and drift is
    None when status is 'ok' or 'n/a'."""
    if opening is None or closing is None:
        return "n/a", None
    expected = closing - opening
    drift = txn_total - expected
    if drift == 0:
        return "ok", None
    return "drift", drift


# ---------------------------------------------------------------------------
# Account registration


_VALID_TYPES = {
    "checking", "savings", "credit_card", "investment",
    "loan", "cash", "other",
}


def register_account(
    store: Store,
    *,
    nickname: str,
    type: str,
    currency: str = "USD",
    display_name: str | None = None,
) -> ResolvedAccount:
    """Create a new statement-fed source + canonical account in one atomic txn.

    Raises ``AccountAlreadyRegistered`` if a source with this nickname exists.
    """
    if type not in _VALID_TYPES:
        raise ValueError(f"invalid type {type!r}; one of {sorted(_VALID_TYPES)}")
    source_id = f"statement:{nickname}"
    account_id = f"{source_id}:account"
    name = display_name or nickname

    existing = store.execute(
        "SELECT 1 FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if existing:
        raise AccountAlreadyRegistered(f"source {source_id!r} already exists")

    now = _utcnow()
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_id, "statement", name, None, now),
        )
        store.execute(
            "INSERT INTO accounts (id, source_id, external_id, name, type, "
            "on_budget, closed, deleted, currency, cleared_balance_minor, "
            "uncleared_balance_minor, balance_as_of, last_synced_at) "
            "VALUES (?, ?, ?, ?, ?, 1, 0, 0, ?, NULL, NULL, NULL, NULL)",
            (account_id, source_id, "account", name, type, currency),
        )

    return ResolvedAccount(
        source_id=source_id,
        account_id=account_id,
        nickname=nickname,
        type=type,
        currency=currency,
    )


def resolve_account(store: Store, nickname: str) -> ResolvedAccount:
    """Look up a previously-registered statement-fed account by nickname."""
    source_id = f"statement:{nickname}"
    row = store.execute(
        "SELECT a.id AS account_id, a.type, a.currency "
        "FROM accounts a WHERE a.source_id = ? AND a.external_id = 'account'",
        (source_id,),
    ).fetchone()
    if not row:
        raise AccountNotConfigured(
            f"no account {nickname!r} configured. Run "
            f"`homefinance accounts add --nickname {nickname} --type checking` first."
        )
    return ResolvedAccount(
        source_id=source_id,
        account_id=row["account_id"],
        nickname=nickname,
        type=row["type"],
        currency=row["currency"],
    )
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/ingest.py tests/test_ingest.py
git commit -m "feat(statement): register/resolve account helpers + file_hash + row_external_id + reconcile"
```

Expected: `9 passed`.

---

## Task 11: `ingest_file()` orchestrator — the heart of SP2

**Goal:** The end-to-end pipeline that parses, reconciles, archives, and atomically stages a batch. Returns a `BatchPreview`. The single largest task in SP2.

**Files:**
- Modify: `src/homefinance/sources/statement/ingest.py` (append `ingest_file`)
- Modify: `tests/test_ingest.py` (append orchestrator integration tests)

- [ ] **Step 1: Append failing tests to `tests/test_ingest.py`**

```python
from homefinance.sources.statement.ingest import BatchPreview, ingest_file
from homefinance.sources.statement.parsers.base import (
    FileAlreadyIngested,
)


def test_ingest_file_csv_stages_pending_batch(store: Store, tmp_path: Path) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    # Write template to a tmp config dir.
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\nAmount\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )

    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    archive_dir = tmp_path / "archive"

    preview = ingest_file(
        store,
        path=fixture,
        account_nickname="citi-cc",
        config_dir=config_dir,
        archive_dir=archive_dir,
    )

    assert isinstance(preview, BatchPreview)
    assert preview.txn_count == 3
    assert preview.source_id == "statement:citi-cc"
    assert preview.reconciliation_status == "n/a"   # CSV has no balances
    assert preview.file_path_archive is not None
    assert Path(preview.file_path_archive).exists()

    # Pending rows in transactions
    rows = store.execute(
        "SELECT status, batch_id FROM transactions WHERE batch_id = ?",
        (preview.batch_id,),
    ).fetchall()
    assert len(rows) == 3
    assert {r["status"] for r in rows} == {"pending_review"}

    # statement_batches row exists with review_status='pending'
    batch = store.execute(
        "SELECT review_status, txn_count, file_hash FROM statement_batches WHERE id = ?",
        (preview.batch_id,),
    ).fetchone()
    assert batch["review_status"] == "pending"
    assert batch["txn_count"] == 3


def test_ingest_file_blocks_re_ingest_of_same_file(store: Store, tmp_path: Path) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\namount = "Amount"\npayee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    archive_dir = tmp_path / "archive"

    ingest_file(store, path=fixture, account_nickname="citi-cc",
                config_dir=config_dir, archive_dir=archive_dir)

    with pytest.raises(FileAlreadyIngested, match="already ingested"):
        ingest_file(store, path=fixture, account_nickname="citi-cc",
                    config_dir=config_dir, archive_dir=archive_dir)


def test_ingest_file_reconciles_when_balances_present(store: Store, tmp_path: Path) -> None:
    """Use the Docling cells.json fixture via FakeDoclingPDFParser to exercise
    the balance-known reconciliation path. We pass the fixture path with a
    .json extension; the fake parser is registered ad-hoc for this test."""
    from homefinance.sources.statement.parsers import _REGISTRY, register

    register_account(store, nickname="wells", type="checking", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:wells.toml").write_text(
        'parser = "docling_pdf"\n'
        "[columns]\ndate = 0\npayee = 1\namount = 2\n"
        "[options]\ndate_format = \"%m/%d/%Y\"\nsign = \"natural\"\n"
    )
    cells = Path(__file__).resolve().parent / "fixtures" / "docling" / "tiny-pdf" / "cells.json"

    original = list(_REGISTRY)
    _REGISTRY.clear()
    register(".json", "homefinance.sources.statement.parsers.docling_pdf:FakeDoclingPDFParser")
    try:
        preview = ingest_file(
            store, path=cells, account_nickname="wells",
            config_dir=config_dir, archive_dir=tmp_path / "archive",
        )
    finally:
        _REGISTRY.clear()
        _REGISTRY.extend(original)

    # cells.json sum is -45.67 + -50.00 + 10.00 = -85.67 = -8567 cents.
    # opening 1234560, closing 1100000, expected delta -134560.
    # drift = -8567 - (-134560) = 125993.
    assert preview.reconciliation_status == "drift"
    assert preview.drift_minor == 125993
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v -k ingest_file`
Expected: `ImportError` on `ingest_file`.

- [ ] **Step 3: Append `ingest_file()` to `src/homefinance/sources/statement/ingest.py`**

```python
# Imports to add at the top of the file:
from typing import cast

from homefinance.db import _upsert
from homefinance.sources.statement.archive import archive_file
from homefinance.sources.statement.parsers import find_parser
from homefinance.sources.statement.parsers.base import FileAlreadyIngested
from homefinance.sources.statement.templates import load_template


def ingest_file(
    store: Store,
    *,
    path: Path,
    account_nickname: str,
    config_dir: Path,
    archive_dir: Path,
    archive: bool = True,
    allow_reingest: bool = False,
    preview_sample_size: int = 5,
) -> BatchPreview:
    """Parse + reconcile + atomically stage one statement file.

    Pipeline: resolve account → hash → file-level dedup → find parser → load
    template → parse → row-level external IDs → reconcile → archive →
    ATOMIC: insert statement_batches + insert transactions (status='pending_review').
    """
    path = Path(path)
    account = resolve_account(store, account_nickname)
    file_hash = compute_file_hash(path)

    # File-level dedup
    prior = store.execute(
        "SELECT id, review_status FROM statement_batches "
        "WHERE file_hash = ? AND source_id = ?",
        (file_hash, account.source_id),
    ).fetchone()
    if prior:
        if prior["review_status"] in ("pending", "confirmed") and not allow_reingest:
            raise FileAlreadyIngested(
                f"already ingested as batch #{prior['id']} "
                f"(status: {prior['review_status']}). Use --reingest to re-process."
            )
        if allow_reingest:
            store.execute(
                "DELETE FROM statement_batches WHERE id = ?", (prior["id"],)
            )

    parser_cls = find_parser(path)
    template = load_template(account.source_id, config_dir=config_dir)
    parsed = parser_cls.parse(path, account, template)

    # Build synthetic external IDs, suffixing within-batch collisions
    seen: dict[str, int] = {}
    txns_with_ids: list[tuple[str, RemoteTransaction]] = []
    for txn in parsed.transactions:
        base = row_external_id(
            account.account_id, txn.date, txn.amount_minor, txn.payee, txn.memo
        )
        n = seen.get(base, 0)
        external_id = base if n == 0 else f"{base}:{n}"
        seen[base] = n + 1
        txns_with_ids.append((external_id, txn))

    # Reconcile
    txn_total = sum(t.amount_minor for _, t in txns_with_ids)
    recon_status, drift_minor = reconcile(
        opening=parsed.opening_balance_minor,
        closing=parsed.closing_balance_minor,
        txn_total=txn_total,
    )

    # Archive — abort before any DB write if it fails
    archive_path: Path | None = None
    if archive:
        archive_path = archive_file(
            path,
            source_id=account.source_id,
            file_hash=file_hash,
            archive_dir=archive_dir,
        )

    # Atomic stage
    parsed_at = _utcnow()
    with store.transaction():
        cur = store.execute(
            "INSERT INTO statement_batches (source_id, file_hash, file_path_original, "
            "file_path_archive, parser, statement_period_start, statement_period_end, "
            "opening_balance_minor, closing_balance_minor, parsed_at, review_status, "
            "review_resolved_at, txn_count, reconciliation_status, drift_minor, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?, ?, NULL)",
            (
                account.source_id, file_hash, str(path),
                str(archive_path) if archive_path else None,
                parsed.source_format,
                parsed.statement_period_start, parsed.statement_period_end,
                parsed.opening_balance_minor, parsed.closing_balance_minor,
                parsed_at, len(txns_with_ids), recon_status, drift_minor,
            ),
        )
        batch_id = cast(int, cur.lastrowid)

        # Stage each transaction as pending_review with batch_id linking back.
        counters: dict[str, int] = {}
        for external_id, txn in txns_with_ids:
            # Replace the placeholder external_id from the parser with the
            # synthetic hash; account_external_id is normalized to "account".
            from dataclasses import replace
            stamped = replace(txn, external_id=external_id, account_external_id="account")
            _upsert.upsert_transaction(
                store, account.source_id, stamped, counters,
                status="pending_review", batch_id=batch_id,
            )

    first_n = tuple(
        TxnPreview(date=t.date, amount_minor=t.amount_minor, payee=t.payee, memo=t.memo)
        for _, t in txns_with_ids[:preview_sample_size]
    )
    return BatchPreview(
        batch_id=batch_id,
        source_id=account.source_id,
        txn_count=len(txns_with_ids),
        reconciliation_status=recon_status,
        drift_minor=drift_minor,
        statement_period_start=parsed.statement_period_start,
        statement_period_end=parsed.statement_period_end,
        opening_balance_minor=parsed.opening_balance_minor,
        closing_balance_minor=parsed.closing_balance_minor,
        file_path_archive=str(archive_path) if archive_path else None,
        first_transactions=first_n,
    )
```

Note: also add `from homefinance.sources.base import RemoteTransaction` at the top.

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/ingest.py tests/test_ingest.py
git commit -m "feat(statement): ingest_file orchestrator — atomic stage + reconciliation"
```

Expected: `12 passed` (9 from T10 + 3 new).

---

## Task 12: confirm / reject / list batches

**Goal:** The three operations that close the batch lifecycle. All atomic. Idempotent on already-resolved batches.

**Files:**
- Modify: `src/homefinance/sources/statement/ingest.py` (append three functions)
- Modify: `tests/test_ingest.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_ingest.py`**

```python
from homefinance.sources.statement.ingest import (
    confirm_batch,
    list_batches,
    reject_batch,
)


def _seed_batch(store: Store, tmp_path: Path) -> int:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\namount = "Amount"\npayee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    preview = ingest_file(
        store, path=fixture, account_nickname="citi-cc",
        config_dir=config_dir, archive_dir=tmp_path / "archive",
    )
    return preview.batch_id


def test_confirm_batch_flips_status(store: Store, tmp_path: Path) -> None:
    batch_id = _seed_batch(store, tmp_path)
    result = confirm_batch(store, batch_id)
    assert result["batch_id"] == batch_id
    assert result["review_status"] == "confirmed"

    statuses = {r["status"] for r in store.execute(
        "SELECT status FROM transactions WHERE batch_id = ?", (batch_id,)
    ).fetchall()}
    assert statuses == {"confirmed"}


def test_reject_batch_deletes_transactions(store: Store, tmp_path: Path) -> None:
    batch_id = _seed_batch(store, tmp_path)
    result = reject_batch(store, batch_id)
    assert result["review_status"] == "rejected"

    n = store.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE batch_id = ?", (batch_id,)
    ).fetchone()["n"]
    assert n == 0
    # statement_batches row preserved
    row = store.execute(
        "SELECT review_status FROM statement_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    assert row["review_status"] == "rejected"


def test_confirm_after_reject_returns_error(store: Store, tmp_path: Path) -> None:
    batch_id = _seed_batch(store, tmp_path)
    reject_batch(store, batch_id)
    with pytest.raises(ValueError, match="not pending"):
        confirm_batch(store, batch_id)


def test_list_batches_filters_by_status(store: Store, tmp_path: Path) -> None:
    batch_id = _seed_batch(store, tmp_path)
    pending = list_batches(store, review_status="pending")
    assert len(pending) == 1
    assert pending[0]["id"] == batch_id

    confirmed = list_batches(store, review_status="confirmed")
    assert confirmed == []

    confirm_batch(store, batch_id)
    pending = list_batches(store, review_status="pending")
    confirmed = list_batches(store, review_status="confirmed")
    assert pending == []
    assert len(confirmed) == 1
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v -k "confirm or reject or list_batches"`
Expected: `ImportError` on the new functions.

- [ ] **Step 3: Append to `src/homefinance/sources/statement/ingest.py`**

```python
def confirm_batch(store: Store, batch_id: int) -> dict[str, Any]:
    """Flip a pending batch's transactions to ``status='confirmed'`` atomically."""
    row = store.execute(
        "SELECT review_status FROM statement_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"batch {batch_id} not found")
    if row["review_status"] != "pending":
        raise ValueError(
            f"batch {batch_id} is not pending (status: {row['review_status']!r})"
        )

    now = _utcnow()
    with store.transaction():
        store.execute(
            "UPDATE transactions SET status = 'confirmed' "
            "WHERE batch_id = ? AND status = 'pending_review'",
            (batch_id,),
        )
        store.execute(
            "UPDATE statement_batches "
            "SET review_status = 'confirmed', review_resolved_at = ? "
            "WHERE id = ?",
            (now, batch_id),
        )
    return {"batch_id": batch_id, "review_status": "confirmed", "review_resolved_at": now}


def reject_batch(store: Store, batch_id: int) -> dict[str, Any]:
    """Delete a pending batch's staged transactions; keep batch row for audit."""
    row = store.execute(
        "SELECT review_status FROM statement_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"batch {batch_id} not found")
    if row["review_status"] != "pending":
        raise ValueError(
            f"batch {batch_id} is not pending (status: {row['review_status']!r})"
        )

    now = _utcnow()
    with store.transaction():
        store.execute("DELETE FROM transactions WHERE batch_id = ?", (batch_id,))
        store.execute(
            "UPDATE statement_batches "
            "SET review_status = 'rejected', review_resolved_at = ? "
            "WHERE id = ?",
            (now, batch_id),
        )
    return {"batch_id": batch_id, "review_status": "rejected", "review_resolved_at": now}


def list_batches(
    store: Store,
    *,
    source_id: str | None = None,
    review_status: str | None = "pending",
) -> list[dict[str, Any]]:
    """List batches matching the filters (most-recent first)."""
    where: list[str] = []
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if review_status is not None:
        where.append("review_status = ?")
        params.append(review_status)
    sql = (
        "SELECT id, source_id, parser, txn_count, review_status, "
        "reconciliation_status, drift_minor, parsed_at, file_path_original "
        "FROM statement_batches "
    )
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY id DESC"
    return [
        {k: r[k] for k in r.keys()}
        for r in store.execute(sql, params).fetchall()
    ]
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_ingest.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/ingest.py tests/test_ingest.py
git commit -m "feat(statement): confirm_batch / reject_batch / list_batches"
```

Expected: `16 passed`.

---

## Task 13: `StatementAccountSource`

**Goal:** A small adapter implementing SP1's `AccountSource` Protocol so statement-fed accounts appear in MCP `list_sources` / `get_sync_status` queries uniformly. `validate()` checks that the account is registered; `pull()` returns an empty `SyncDelta` (statements don't sync from a remote — the write path is `ingest_file`).

**Files:**
- Create: `src/homefinance/sources/statement/source.py`
- Create: `tests/test_statement_source.py`

- [ ] **Step 1: Write failing tests at `tests/test_statement_source.py`**

```python
from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.base import AccountSource, SyncDelta
from homefinance.sources.statement.ingest import register_account
from homefinance.sources.statement.parsers.base import AccountNotConfigured
from homefinance.sources.statement.source import StatementAccountSource


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "ss.sqlite3"
    migrate(db)
    return Store.open(db)


def test_satisfies_account_source_protocol(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    assert isinstance(src, AccountSource)
    assert src.source_id == "statement:citi-cc"
    assert src.kind == "statement"
    assert src.nickname == "citi-cc"


def test_validate_passes_for_registered_account(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    src.validate()


def test_validate_raises_for_unregistered_account(store: Store) -> None:
    src = StatementAccountSource(store=store, nickname="nope")
    with pytest.raises(AccountNotConfigured):
        src.validate()


def test_pull_returns_empty_sync_delta(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    delta = src.pull(cursor=None)
    assert isinstance(delta, SyncDelta)
    assert delta.accounts == ()
    assert delta.transactions == ()
    assert delta.new_cursor is None
```

- [ ] **Step 2: Confirm tests fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_source.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/sources/statement/source.py`**

```python
"""``StatementAccountSource`` — implements ``AccountSource`` for statement-fed accounts.

Honest divergence from YNAB: statements don't sync from a remote. ``pull()``
returns an empty ``SyncDelta``; the actual write path is ``ingest_file()`` in
``ingest.py``. The Protocol is honored so MCP read tools treat statement
sources uniformly with YNAB sources.
"""

from __future__ import annotations

from typing import Literal

from homefinance.db.store import Store
from homefinance.sources.base import SyncDelta
from homefinance.sources.statement.ingest import resolve_account


class StatementAccountSource:
    """One statement-fed account surfaced as an ``AccountSource``."""

    kind: Literal["statement"] = "statement"

    def __init__(self, *, store: Store, nickname: str) -> None:
        self._store = store
        self.nickname = nickname
        self.source_id = f"statement:{nickname}"

    def validate(self) -> None:
        """Raises ``AccountNotConfigured`` if the nickname isn't registered."""
        resolve_account(self._store, self.nickname)

    def pull(self, cursor: int | None) -> SyncDelta:
        """Statements don't sync from a remote. Return an empty delta."""
        return SyncDelta(
            accounts=(),
            categories=(),
            payees=(),
            transactions=(),
            new_cursor=None,
        )
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_statement_source.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/sources/statement/source.py tests/test_statement_source.py
git commit -m "feat(statement): StatementAccountSource implementing AccountSource Protocol"
```

Expected: `4 passed`.

---

## Task 14: SP1 MCP-tool surgical updates (read-side compatibility)

**Goal:** Three SP1 tools need to respect the new `status` column. `query_transactions` gains an `include_pending` opt-in; `summarize_spending` always filters `status='confirmed'`; `get_sync_status` adds `pending_batch_count` per source.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py`
- Modify: `src/homefinance/mcp_server/__main__.py` (wrappers)
- Modify: `tests/test_mcp_tools.py` (append assertions on new behavior)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`**

```python
from homefinance.sources.statement.ingest import (
    confirm_batch,
    ingest_file,
    register_account,
)


def _stage_pending_csv(store, tmp_path, tiny_fixtures_dir):
    """Helper: register an account and stage a pending CSV batch."""
    from pathlib import Path
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\npayee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "statement"
    return ingest_file(
        store, path=fixture_root / "tiny.csv", account_nickname="citi-cc",
        config_dir=config_dir, archive_dir=tmp_path / "archive",
    )


def test_query_transactions_excludes_pending_by_default(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    preview = _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    rows = query_transactions(synced_store)
    ext_ids = {r["external_id"] for r in rows}
    # YNAB rows are present; statement pending rows are not.
    assert "txn-non-split" in ext_ids
    pending_ids = {f"sub-csv-{i}" for i in range(3)}  # placeholder
    assert all(p not in ext_ids for p in pending_ids)


def test_query_transactions_includes_pending_when_opted_in(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    preview = _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    all_rows = query_transactions(synced_store, include_deleted=False)  # confirmed only
    with_pending = query_transactions(synced_store, include_pending=True)
    assert len(with_pending) > len(all_rows)


def test_summarize_spending_always_excludes_pending(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    preview = _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    before_total = sum(r["total_minor"] for r in summarize_spending(synced_store, group_by="account"))
    # Confirming the pending batch SHOULD increase the total.
    confirm_batch(synced_store, preview.batch_id)
    after_total = sum(r["total_minor"] for r in summarize_spending(synced_store, group_by="account"))
    assert after_total != before_total


def test_get_sync_status_includes_pending_batch_count(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    statuses = get_sync_status(synced_store)
    by_id = {s["source_id"]: s for s in statuses}
    assert "pending_batch_count" in by_id["statement:citi-cc"]
    assert by_id["statement:citi-cc"]["pending_batch_count"] == 1
```

- [ ] **Step 2: Modify the three tools in `src/homefinance/mcp_server/tools.py`** with these surgical edits:

In `query_transactions`, add the parameter and one WHERE clause:

```python
def query_transactions(
    store: Store,
    source_id: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category_id: str | None = None,
    payee_contains: str | None = None,
    amount_min_minor: int | None = None,
    amount_max_minor: int | None = None,
    cleared: str | None = None,
    include_deleted: bool = False,
    include_pending: bool = False,            # <-- new
    mode: Mode = "leaves",
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """..."""
    where: list[str] = []
    params: list[Any] = []

    if mode == "leaves":
        where.append("is_split_parent = 0")
    elif mode == "tops":
        where.append("parent_id IS NULL")
    else:
        raise ValueError(f"invalid mode: {mode!r}")

    if not include_deleted:
        where.append("deleted = 0")
    if not include_pending:                                  # <-- new
        where.append("status = 'confirmed'")                 # <-- new
    # ... rest of the function unchanged ...
```

In `summarize_spending`, ensure the WHERE has the status filter (no opt-in):

```python
def summarize_spending(...):
    ...
    where: list[str] = ["t.is_split_parent = 0", "t.deleted = 0", "t.status = 'confirmed'"]
    # ... rest unchanged ...
```

In `get_sync_status`, extend the SELECT with a sub-query for pending_batch_count:

```python
def get_sync_status(store: Store) -> list[dict[str, Any]]:
    """..."""
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_reconciliation, "
        "(SELECT drift_report FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_drift_report, "
        "(SELECT COUNT(*) FROM statement_batches "
        "  WHERE source_id = s.id AND review_status = 'pending') "
        "  AS pending_batch_count "
        "FROM sources s LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        drift_count = 0
        if r["last_drift_report"]:
            try:
                drift_count = len(json.loads(r["last_drift_report"]).get("accounts", []))
            except (json.JSONDecodeError, AttributeError, TypeError):
                drift_count = 0
        out.append({
            "source_id":           r["source_id"],
            "kind":                r["kind"],
            "nickname":            r["nickname"],
            "last_sync_at":        r["last_sync_at"],
            "server_knowledge":    r["server_knowledge"],
            "last_reconciliation": r["last_reconciliation"],
            "drift_account_count": drift_count,
            "pending_batch_count": int(r["pending_batch_count"] or 0),    # <-- new
        })
    return out
```

- [ ] **Step 3: Update the `@mcp.tool()` wrapper in `__main__.py`** for `query_transactions` to pass the new param. Find the existing `def query_transactions(...)` wrapper and add `include_pending: bool = False` alongside the other params, then thread it into the `_tools.query_transactions(...)` call.

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): surgical SP1 updates — include_pending + status filters + pending_batch_count"
```

Expected: previously-passing SP1 MCP tests + 4 new tests all pass.

---

## Task 15: CLI — `homefinance accounts add`

**Goal:** Wire the SP2 account registration into the CLI as a new `accounts` sub-typer with one command. Calls the library `register_account()` from T10.

**Files:**
- Modify: `src/homefinance/cli.py` (add `accounts_app` and `accounts add` command)
- Modify: `tests/test_cli.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
def test_accounts_add_creates_source_row(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])  # ensures DB exists
    # Use the env fixture; HOMEFINANCE_DB and CONFIG already pointed at tmp_path.
    result = runner.invoke(
        app, ["accounts", "add",
              "--nickname", "citi-cc",
              "--type", "credit_card",
              "--currency", "USD",
              "--display-name", "Citi Credit Card"],
    )
    assert result.exit_code == 0, result.stdout
    assert "Added" in result.stdout
    assert "statement:citi-cc" in result.stdout

    import sqlite3
    with sqlite3.connect(env / "db.sqlite3") as conn:
        srcs = {r[0] for r in conn.execute("SELECT id FROM sources").fetchall()}
        accts = {r[0] for r in conn.execute("SELECT id FROM accounts").fetchall()}
    assert "statement:citi-cc" in srcs
    assert "statement:citi-cc:account" in accts


def test_accounts_add_invalid_type_errors(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    result = runner.invoke(
        app, ["accounts", "add", "--nickname", "x", "--type", "banana"]
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Add the `accounts` sub-typer + command to `src/homefinance/cli.py`**

Near the end of the file (where `ynab_app` and other sub-typers are already registered), append:

```python
from homefinance.sources.statement.ingest import (
    AccountAlreadyRegistered,
    register_account as _register_statement_account,
)


accounts_app = typer.Typer(help="Manage local accounts (e.g., statement-fed).")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("add")
def accounts_add(
    nickname: str = typer.Option(..., "--nickname", "-n"),  # noqa: B008
    account_type: str = typer.Option(..., "--type", "-t",   # noqa: B008
        help="checking | savings | credit_card | investment | loan | cash | other"),
    currency: str = typer.Option("USD", "--currency"),      # noqa: B008
    display_name: str | None = typer.Option(None, "--display-name"),  # noqa: B008
) -> None:
    """Register a statement-fed account in the local store."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)
    try:
        ra = _register_statement_account(
            store,
            nickname=nickname,
            type=account_type,
            currency=currency,
            display_name=display_name,
        )
    except AccountAlreadyRegistered as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(
        f"[green]Added[/] {ra.source_id} (type: {ra.type}, currency: {ra.currency})"
    )
```

- [ ] **Step 3: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v -k accounts_add
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): accounts add subcommand for registering statement-fed accounts"
```

Expected: `2 passed` for the new tests; full test_cli.py suite still passes.

---

## Task 16: CLI — `homefinance ingest` with inline prompt

**Goal:** A new top-level `ingest` command that parses + stages a statement, prints a Rich preview, and prompts `Confirm? [y/N/show-more]`. `--no-prompt` makes it scriptable.

**Files:**
- Modify: `src/homefinance/cli.py` (add `ingest` command + small render helper)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
def test_ingest_with_no_prompt_stages_batch(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    runner.invoke(app, ["accounts", "add", "--nickname", "citi-cc",
                        "--type", "credit_card", "--currency", "USD"])
    # Drop a CSV template in the resolved config dir
    cfg_dir = env  # env IS the resolved HOMEFINANCE_CONFIG parent
    templates = cfg_dir / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = (Path(__file__).resolve().parent
               / "fixtures" / "statement" / "tiny.csv")
    result = runner.invoke(app, [
        "ingest", str(fixture),
        "--account", "citi-cc", "--no-prompt", "--no-archive",
    ])
    assert result.exit_code == 0, result.stdout
    assert "batch_id" in result.stdout


def test_ingest_prompt_y_confirms(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    runner.invoke(app, ["accounts", "add", "--nickname", "citi-cc",
                        "--type", "credit_card", "--currency", "USD"])
    cfg_dir = env
    (cfg_dir / "templates").mkdir(parents=True, exist_ok=True)
    (cfg_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = (Path(__file__).resolve().parent
               / "fixtures" / "statement" / "tiny.csv")
    result = runner.invoke(
        app,
        ["ingest", str(fixture), "--account", "citi-cc", "--no-archive"],
        input="y\n",
    )
    assert result.exit_code == 0, result.stdout
    assert "Confirmed" in result.stdout
```

- [ ] **Step 2: Add the `ingest` command in `src/homefinance/cli.py`**

```python
from homefinance.sources.statement.ingest import (
    confirm_batch as _confirm_batch,
    ingest_file as _ingest_file,
    reject_batch as _reject_batch,
)
from homefinance.sources.statement.parsers.base import StatementIngestError


def _render_preview(preview: object) -> Table:
    """Render a BatchPreview as a small Rich table for inline confirmation."""
    from homefinance.sources.statement.ingest import BatchPreview
    p = preview if isinstance(preview, BatchPreview) else None
    assert p is not None
    summary = Table(title=f"Batch #{p.batch_id} — {p.source_id}")
    summary.add_column("field")
    summary.add_column("value")
    summary.add_row("transactions", str(p.txn_count))
    summary.add_row("period",
                    f"{p.statement_period_start or '?'} → {p.statement_period_end or '?'}")
    summary.add_row("reconciliation",
                    f"{p.reconciliation_status}" +
                    (f" (drift: {p.drift_minor / 100:+.2f})" if p.drift_minor else ""))
    return summary


@app.command()
def ingest(
    path: str = typer.Argument(...),
    account: str = typer.Option(..., "--account", "-a"),  # noqa: B008
    no_archive: bool = typer.Option(False, "--no-archive"),
    no_prompt: bool = typer.Option(False, "--no-prompt"),
    reingest: bool = typer.Option(False, "--reingest"),
) -> None:
    """Parse + stage a statement file; prompt to confirm or reject."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)

    try:
        preview = _ingest_file(
            store,
            path=Path(path),
            account_nickname=account,
            config_dir=cfg.config_path.parent,
            archive_dir=cfg.config_path.parent / "archive",
            archive=not no_archive,
            allow_reingest=reingest,
        )
    except StatementIngestError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None

    console.print(_render_preview(preview))

    if no_prompt:
        console.print(f"[yellow]Staged[/] batch_id={preview.batch_id} "
                      "(pending review). Confirm with: "
                      f"[bold]homefinance batch confirm {preview.batch_id}[/]")
        return

    choice = typer.prompt("Confirm? [y/N/show-more]", default="N").strip().lower()
    if choice == "show-more":
        for t in preview.first_transactions:
            console.print(f"  {t.date}  {t.amount_minor / 100:+9.2f}  "
                          f"{t.payee or '-'}  {t.memo or ''}")
        choice = typer.prompt("Confirm? [y/N]", default="N").strip().lower()
    if choice == "y":
        _confirm_batch(store, preview.batch_id)
        console.print(f"[green]Confirmed[/] batch #{preview.batch_id}.")
    else:
        _reject_batch(store, preview.batch_id)
        console.print(f"[yellow]Rejected[/] batch #{preview.batch_id}.")
```

- [ ] **Step 3: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v -k ingest
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): ingest command with inline confirm/reject prompt"
```

Expected: `2 new passed`.

---

## Task 17: CLI — `batches` list + `batch confirm/reject` + status update

**Goal:** Three commands wrapping the library functions from T12, plus a small addition to `status` so pending batches surface in the regular status output.

**Files:**
- Modify: `src/homefinance/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Append failing tests**

```python
def test_batches_lists_pending(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    runner.invoke(app, ["accounts", "add", "--nickname", "citi-cc",
                        "--type", "credit_card"])
    (env / "templates").mkdir(parents=True, exist_ok=True)
    (env / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = (Path(__file__).resolve().parent
               / "fixtures" / "statement" / "tiny.csv")
    runner.invoke(app, ["ingest", str(fixture), "--account", "citi-cc",
                        "--no-prompt", "--no-archive"])

    result = runner.invoke(app, ["batches"])
    assert result.exit_code == 0, result.stdout
    assert "statement:citi-cc" in result.stdout
    assert "pending" in result.stdout


def test_batch_confirm_then_status_shows_no_pending(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    runner.invoke(app, ["accounts", "add", "--nickname", "citi-cc",
                        "--type", "credit_card"])
    (env / "templates").mkdir(parents=True, exist_ok=True)
    (env / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = (Path(__file__).resolve().parent
               / "fixtures" / "statement" / "tiny.csv")
    res1 = runner.invoke(app, ["ingest", str(fixture), "--account", "citi-cc",
                               "--no-prompt", "--no-archive"])
    # batch_id will be 1 since this is the only one
    res2 = runner.invoke(app, ["batch", "confirm", "1"])
    assert res2.exit_code == 0
    assert "Confirmed" in res2.stdout

    listing = runner.invoke(app, ["batches"])
    assert "1" not in listing.stdout or "pending" not in listing.stdout
```

- [ ] **Step 2: Add the commands in `src/homefinance/cli.py`**

```python
from homefinance.sources.statement.ingest import list_batches as _list_batches


@app.command()
def batches(
    pending: bool = typer.Option(True, "--pending"),
    confirmed: bool = typer.Option(False, "--confirmed"),
    rejected: bool = typer.Option(False, "--rejected"),
    all_: bool = typer.Option(False, "--all"),
    source: str | None = typer.Option(None, "--source"),  # noqa: B008
) -> None:
    """List statement batches in the local store."""
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print("[yellow]No database. Nothing to list.[/]")
        return
    store = Store.open(cfg.db_path)

    if all_:
        status = None
    elif rejected:
        status = "rejected"
    elif confirmed:
        status = "confirmed"
    else:
        status = "pending"

    rows = _list_batches(store, source_id=source, review_status=status)
    if not rows:
        label = "any" if status is None else status
        console.print(f"[yellow]No {label} batches.[/]")
        return

    table = Table(title=f"Statement Batches ({status or 'all'})")
    table.add_column("batch_id", justify="right")
    table.add_column("source")
    table.add_column("parsed_at")
    table.add_column("count", justify="right")
    table.add_column("reconciliation")
    table.add_column("status")
    for r in rows:
        recon = r["reconciliation_status"]
        if r["drift_minor"]:
            recon += f" ({r['drift_minor'] / 100:+.2f})"
        table.add_row(str(r["id"]), r["source_id"], r["parsed_at"],
                      str(r["txn_count"]), recon, r["review_status"])
    console.print(table)


batch_app = typer.Typer(help="Per-batch operations.")
app.add_typer(batch_app, name="batch")


@batch_app.command("confirm")
def batch_confirm_cmd(batch_id: int) -> None:
    """Confirm a pending batch."""
    cfg = load_config()
    store = Store.open(cfg.db_path)
    try:
        _confirm_batch(store, batch_id)
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Confirmed[/] batch #{batch_id}.")


@batch_app.command("reject")
def batch_reject_cmd(batch_id: int) -> None:
    """Reject a pending batch (deletes its staged transactions)."""
    cfg = load_config()
    store = Store.open(cfg.db_path)
    try:
        _reject_batch(store, batch_id)
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[yellow]Rejected[/] batch #{batch_id}.")
```

Also append to the existing `status` command (find it in cli.py — replace the function with the version below):

```python
@app.command()
def status() -> None:
    """Show configured sources and their last-sync state."""
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print("[yellow]No sources configured.[/] Run [bold]homefinance init[/] first.")
        return
    store = Store.open(cfg.db_path)
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_recon, "
        "(SELECT COUNT(*) FROM statement_batches "
        " WHERE source_id = s.id AND review_status = 'pending') AS pending_batches "
        "FROM sources s "
        "LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    if not rows:
        console.print("[yellow]No sources configured.[/] Run [bold]homefinance init[/] first.")
        return

    table = Table(title="Sources")
    table.add_column("source_id")
    table.add_column("nickname")
    table.add_column("last sync")
    table.add_column("cursor", justify="right")
    table.add_column("reconciliation")
    table.add_column("pending", justify="right")
    for r in rows:
        table.add_row(
            r["source_id"],
            r["nickname"] or "-",
            r["last_sync_at"] or "(never)",
            str(r["server_knowledge"] or "-"),
            r["last_recon"] or "-",
            str(r["pending_batches"] or "-"),
        )
    console.print(table)
```

- [ ] **Step 3: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): batches list + batch confirm/reject + status pending-batch column"
```

Expected: all CLI tests pass (existing + the new ones).

---

## Task 18: 4 new MCP tools

**Goal:** `ingest_statement`, `list_batches`, `confirm_batch`, `reject_batch` as tools + their `@mcp.tool()` wrappers.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py`
- Modify: `src/homefinance/mcp_server/__main__.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: Append failing tests**

```python
from homefinance.mcp_server.tools import (
    confirm_batch as mcp_confirm_batch,
    ingest_statement as mcp_ingest_statement,
    list_batches as mcp_list_batches,
    reject_batch as mcp_reject_batch,
)


def test_mcp_ingest_statement_returns_preview_dict(
    synced_store: Store, tmp_path: Path
) -> None:
    register_account(synced_store, nickname="citi-cc", type="credit_card", currency="USD")
    cfg_dir = tmp_path / "homefinance"
    (cfg_dir / "templates").mkdir(parents=True)
    (cfg_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    result = mcp_ingest_statement(
        synced_store, path=str(fixture), account_nickname="citi-cc",
        config_dir=str(cfg_dir), archive_dir=str(tmp_path / "archive"),
        archive=True,
    )
    assert result["batch_id"] >= 1
    assert result["txn_count"] == 3
    assert "first_transactions" in result


def test_mcp_list_batches(synced_store: Store) -> None:
    rows = mcp_list_batches(synced_store, review_status="pending")
    # In this test the store has no batches yet
    assert isinstance(rows, list)


def test_mcp_confirm_batch(synced_store: Store, tmp_path: Path) -> None:
    register_account(synced_store, nickname="citi-cc", type="credit_card", currency="USD")
    cfg_dir = tmp_path / "homefinance"
    (cfg_dir / "templates").mkdir(parents=True)
    (cfg_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    preview = mcp_ingest_statement(
        synced_store, path=str(fixture), account_nickname="citi-cc",
        config_dir=str(cfg_dir), archive_dir=str(tmp_path / "archive"),
    )
    result = mcp_confirm_batch(synced_store, batch_id=preview["batch_id"])
    assert result["review_status"] == "confirmed"


def test_mcp_reject_batch(synced_store: Store, tmp_path: Path) -> None:
    register_account(synced_store, nickname="citi-cc", type="credit_card", currency="USD")
    cfg_dir = tmp_path / "homefinance"
    (cfg_dir / "templates").mkdir(parents=True)
    (cfg_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    preview = mcp_ingest_statement(
        synced_store, path=str(fixture), account_nickname="citi-cc",
        config_dir=str(cfg_dir), archive_dir=str(tmp_path / "archive"),
    )
    result = mcp_reject_batch(synced_store, batch_id=preview["batch_id"])
    assert result["review_status"] == "rejected"
```

- [ ] **Step 2: Append to `src/homefinance/mcp_server/tools.py`**

```python
from dataclasses import asdict
from pathlib import Path

from homefinance.sources.statement.ingest import (
    BatchPreview,
    confirm_batch as _confirm_batch_lib,
    ingest_file as _ingest_file_lib,
    list_batches as _list_batches_lib,
    reject_batch as _reject_batch_lib,
)
from homefinance.sources.statement.parsers.base import StatementIngestError


def _preview_to_dict(p: BatchPreview) -> dict[str, Any]:
    d = asdict(p)
    return d


def ingest_statement(
    store: Store,
    *,
    path: str,
    account_nickname: str,
    config_dir: str,
    archive_dir: str,
    archive: bool = True,
) -> dict[str, Any]:
    """Parse + stage a statement file. Returns a BatchPreview dict.

    Does not prompt; the caller (usually Claude) is expected to inspect the
    preview, decide, and call ``confirm_batch`` or ``reject_batch``.
    """
    try:
        preview = _ingest_file_lib(
            store,
            path=Path(path),
            account_nickname=account_nickname,
            config_dir=Path(config_dir),
            archive_dir=Path(archive_dir),
            archive=archive,
        )
    except StatementIngestError as e:
        return {"error": e.code, "message": str(e)}
    return _preview_to_dict(preview)


def list_batches(
    store: Store,
    *,
    source_id: str | None = None,
    review_status: str | None = "pending",
) -> list[dict[str, Any]]:
    return _list_batches_lib(store, source_id=source_id, review_status=review_status)


def confirm_batch(store: Store, *, batch_id: int) -> dict[str, Any]:
    return _confirm_batch_lib(store, batch_id)


def reject_batch(store: Store, *, batch_id: int) -> dict[str, Any]:
    return _reject_batch_lib(store, batch_id)
```

- [ ] **Step 3: Add the `@mcp.tool()` wrappers in `__main__.py`**

```python
@mcp.tool()
def ingest_statement(
    path: str,
    account_nickname: str,
    archive: bool = True,
) -> dict:
    """Parse + stage one statement file. Returns the BatchPreview as a dict."""
    cfg = _cfg_cached()
    return _tools.ingest_statement(
        _store_cached(),
        path=path,
        account_nickname=account_nickname,
        config_dir=str(cfg.config_path.parent),
        archive_dir=str(cfg.config_path.parent / "archive"),
        archive=archive,
    )


@mcp.tool()
def list_batches(
    source_id: str | None = None,
    review_status: str = "pending",
) -> list[dict]:
    """List statement batches in the local store."""
    return _tools.list_batches(_store_cached(), source_id=source_id,
                               review_status=review_status)


@mcp.tool()
def confirm_batch(batch_id: int) -> dict:
    """Promote a pending batch's transactions to status='confirmed'."""
    return _tools.confirm_batch(_store_cached(), batch_id=batch_id)


@mcp.tool()
def reject_batch(batch_id: int) -> dict:
    """Delete a pending batch's staged transactions; preserve the batch row."""
    return _tools.reject_batch(_store_cached(), batch_id=batch_id)
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): ingest_statement/list_batches/confirm_batch/reject_batch tools"
```

Expected: previously-passing MCP tests + 4 new tests all pass.

---

## Task 19: `homefinance-import-statement` skill

**Goal:** A new SKILL.md that orchestrates the ingest → preview → confirm/reject flow for Claude. Embeds the rule "**never auto-confirm**" even when reconciliation is `ok`.

**Files:**
- Create: `plugin/skills/homefinance-import-statement/SKILL.md`

- [ ] **Step 1: Create `plugin/skills/homefinance-import-statement/SKILL.md`**

```markdown
---
name: homefinance-import-statement
description: Use when the user asks to import or ingest a bank or credit-card statement, mentions a path to a .csv/.ofx/.qfx/.pdf file in a financial context, asks about pending batches awaiting review, or invokes /homefinance:import-statement. Walks the user through parse → preview → confirm/reject with money-safety guardrails.
---

# homefinance — Import a statement

You are helping the user import one statement file (CSV / OFX / QFX / PDF) into the local homefinance store.

## Pre-flight

1. Confirm the statement-fed **account** the file belongs to. If the user didn't specify, call `list_sources` and offer the statement-kind sources as choices. If the right account isn't registered, tell them to run `homefinance accounts add --nickname <nick> --type <type>` first (or do it for them via MCP — there is no `register_statement_account` MCP tool, so this step is CLI-only).

2. Confirm the file path exists. Don't guess.

## The flow

1. **`ingest_statement(path, account_nickname)`** — parses, stages, returns a `BatchPreview` dict.
2. **Always show the preview** — list `txn_count`, `reconciliation_status`, `drift_minor` (if any), `statement_period_start` / `_end`, and the first few transactions (under `first_transactions`).
3. **Then ask the user**: confirm, reject, or look at more details.

## Reconciliation status — how to read it

- `reconciliation_status='ok'` — the parser's sum matches the statement's opening→closing delta exactly. **Confirmation is low-risk.** Suggest confirm, but still require an explicit "yes" before calling `confirm_batch`.
- `reconciliation_status='drift'` — there is a `drift_minor` mismatch. Show the drift in dollars (`drift_minor / 100`). Walk through the per-row preview; ask the user whether one of the rows looks wrong. Do not confirm until they look at it.
- `reconciliation_status='n/a'` — the parser couldn't extract opening or closing balance, so there's no reconciliation safety net. Emphasize that **manual review is the only check**. Offer to render the full transaction list.

## Rules

- **Never auto-confirm.** Even when reconciliation is `ok`, require an explicit human approval.
- After the user approves: call `confirm_batch(batch_id)`. Tell them how many transactions are now confirmed.
- After the user declines: call `reject_batch(batch_id)`. Tell them the staged rows have been removed; the batch row remains for audit.
- **Don't call `sync_ynab` here.** SP2 is statement ingestion; it has nothing to do with YNAB.
- Amounts in `BatchPreview` and the underlying transactions are in **signed integer minor units (cents)**. Convert to dollars in your message text by dividing by 100 with two decimal places.

## When something goes wrong

- The tool returns `{"error": "<code>", "message": "..."}`. Surface the message verbatim.
- `error="template_not_found"` — explain templates and offer to write a starter template (suggest a path, leave content for the user to confirm).
- `error="file_already_ingested"` — the user has imported this file before. Show the prior batch's status (`list_batches(source_id=..., review_status=None)`).
- `error="archive_failed"` — disk-full or permission issue. Don't proceed; flag the underlying I/O message.

## After confirmation succeeds

Suggest one of:
- `summarize_spending(group_by='category')` — see how the new transactions land.
- `query_transactions(account_id='statement:<nick>:account')` — list the just-imported set.
- `/homefinance:explore` — broader analysis skill if they want guided questions.
```

- [ ] **Step 2: Verify frontmatter parses**

Run:
```bash
~/.virtualenvs/homeFinance/bin/python -c "
import re, pathlib
text = pathlib.Path('plugin/skills/homefinance-import-statement/SKILL.md').read_text()
m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
assert m, 'no frontmatter'
fm = m.group(1)
assert 'name: homefinance-import-statement' in fm
assert 'description:' in fm
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/homefinance-import-statement/SKILL.md
git commit -m "feat(plugin): homefinance-import-statement skill"
```

---

## Task 20: Edit `homefinance-setup` + `homefinance-explore` skills

**Goal:** Add the statement-account section to setup; add the `include_pending` note to explore.

**Files:**
- Modify: `plugin/skills/homefinance-setup/SKILL.md`
- Modify: `plugin/skills/homefinance-explore/SKILL.md`

- [ ] **Step 1: Append to `plugin/skills/homefinance-setup/SKILL.md`** (immediately before the "Suggest the `homefinance-explore` skill" closing line):

```markdown
## Statement-fed accounts (SP2)

For accounts YNAB does not already cover (e.g., a credit card whose data only comes from a downloaded PDF or CSV), register them locally before ingesting any statement file:

1. Tell the user to run, for each non-YNAB account:
   ```
   homefinance accounts add --nickname citi-cc --type credit_card --currency USD
   ```
   Valid types: `checking`, `savings`, `credit_card`, `investment`, `loan`, `cash`, `other`.

2. If the parser they need is **CSV** or **Docling PDF**, that account also needs a per-account template at `~/.homefinance/templates/statement:<nickname>.toml`. Walk them through writing one based on what their bank actually exports. OFX/QFX never need a template.

3. Once an account is registered (and template authored if needed), invoke the `/homefinance:import-statement` skill to walk through ingesting their first file.

```

- [ ] **Step 2: Append to `plugin/skills/homefinance-explore/SKILL.md`**'s "Rules" section, after the existing "Never call `sync_ynab` unprompted" bullet:

```markdown
- Statement-imported transactions live in two states: **`confirmed`** (analytically visible) and **`pending_review`** (excluded by default). If the user explicitly asks "what's awaiting review?" pass `include_pending=True` to `query_transactions`. Never include pending rows in spending summaries — `summarize_spending` already filters them out.
- If `get_sync_status` shows `pending_batch_count > 0` for any source, mention it: the user may have forgotten to confirm a batch. Suggest `/homefinance:import-statement` or `homefinance batch confirm <id>`.
```

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/homefinance-setup/SKILL.md \
        plugin/skills/homefinance-explore/SKILL.md
git commit -m "docs(plugin): setup + explore skills updated for SP2 statement ingestion"
```

---

## Task 21: Lazy-import enforcement test

**Goal:** The load-bearing test that asserts `import homefinance` (and importing the package without the `ingest` extra) does not transitively load `docling`. Subprocess-based so it gets a clean Python interpreter.

**Files:**
- Create: `tests/test_lazy_import.py`

- [ ] **Step 1: Write the test**

```python
"""Load-bearing test for SP2's C-10 constraint (lean install stays lean).

If a future top-level ``import docling`` ever sneaks into a parser module,
this test fails — forcing the import to move inside the method that needs it.
"""

import subprocess
import sys


def test_homefinance_does_not_import_docling_at_package_import_time() -> None:
    code = (
        "import sys, homefinance, homefinance.sources.statement, "
        "homefinance.sources.statement.parsers; "
        "leaks = [m for m in sys.modules if 'docling' in m]; "
        "assert leaks == [], f'Docling leaked: {leaks}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_homefinance_does_not_import_ofxtools_at_package_import_time() -> None:
    code = (
        "import sys, homefinance, homefinance.sources.statement, "
        "homefinance.sources.statement.parsers; "
        "leaks = [m for m in sys.modules if 'ofxtools' in m]; "
        "assert leaks == [], f'ofxtools leaked: {leaks}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_lazy_import.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add tests/test_lazy_import.py
git commit -m "test(statement): subprocess-based lazy-import enforcement"
```

Expected: `2 passed`.

---

## Task 22: Docling fixture-recording script + integration test stub

**Goal:** A maintainer script `scripts/record_docling_fixtures.py` that takes a real PDF, runs Docling, sanitizes, and writes a `cells.json` fixture. Plus a `tests/integration/test_docling_live.py` stub that runs *only* when the `docling` marker is passed.

**Files:**
- Create: `scripts/record_docling_fixtures.py`
- Create: `tests/integration/__init__.py` (empty docstring)
- Create: `tests/integration/test_docling_live.py`
- Modify: `pyproject.toml` (add `docling` marker to `[tool.pytest.ini_options].markers`)

- [ ] **Step 1: Create `scripts/record_docling_fixtures.py`**

```python
"""Record sanitized Docling output for use as test fixtures.

Usage:
    python scripts/record_docling_fixtures.py --pdf /path/to/statement.pdf \
        --out tests/fixtures/docling/<name>/

Writes a single ``cells.json`` shaped like the fake parser expects. Sanitizes
identifiers (amounts kept; names/memos replaced with placeholders) — the
maintainer should still review the output before committing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except ImportError:
        print("error: docling is required. Install with: pip install 'homefinance[ingest]'",
              file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    result = converter.convert(str(args.pdf))

    table = next(iter(result.document.tables or []), None)
    cells = {
        "statement_period_start": None,
        "statement_period_end": None,
        "opening_balance_minor": None,
        "closing_balance_minor": None,
        "table": {
            "header": [c.text for c in (table.header or [])] if table else [],
            "rows": [
                [f"[scrubbed col {i}]" if i not in (0, 2) else c.text
                 for i, c in enumerate(r)]
                for r in (table.rows or [])
            ] if table else [],
        },
    }

    out_file = args.out / "cells.json"
    out_file.write_text(json.dumps(cells, indent=2, sort_keys=True))
    print(f"wrote {out_file}")
    print("\nREVIEW the output before committing — automated scrubbing is rough.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Create `tests/integration/__init__.py`**

```python
"""Integration tests gated to manual CI runs (not in default pytest)."""
```

- [ ] **Step 3: Create `tests/integration/test_docling_live.py`**

```python
"""Live-Docling integration test. Run via:

    pytest tests/integration -m docling

Default ``pytest`` does NOT collect this module (filterwarnings + the
``docling`` marker keep it out of the standard run). The
``test-docling`` CI job (manual dispatch) is the only place this runs in CI.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.docling


def test_docling_can_be_imported() -> None:
    docling = pytest.importorskip("docling")
    assert hasattr(docling, "document_converter")


def test_docling_pdf_parser_real_path_against_bundled_sample(tmp_path: Path) -> None:
    """Live Docling against the bundled tiny PDF fixture (maintainer ships one).

    If ``tests/fixtures/docling/tiny-pdf/sample.pdf`` does not exist, this test
    is skipped — we don't want this job hard-fail if the sample isn't yet
    captured.
    """
    sample = (Path(__file__).resolve().parent.parent
              / "fixtures" / "docling" / "tiny-pdf" / "sample.pdf")
    if not sample.exists():
        pytest.skip(f"no live sample at {sample}; capture one via record_docling_fixtures.py")

    from homefinance.sources.statement.parsers.base import ResolvedAccount
    from homefinance.sources.statement.parsers.docling_pdf import DoclingPDFParser

    account = ResolvedAccount(
        source_id="statement:test", account_id="statement:test:account",
        nickname="test", type="checking", currency="USD",
    )
    template = {
        "parser": "docling_pdf",
        "columns": {"date": 0, "payee": 1, "amount": 2},
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }
    parsed = DoclingPDFParser.parse(sample, account, template)
    assert parsed.source_format == "docling_pdf"
    assert len(parsed.transactions) >= 0
```

- [ ] **Step 4: Add the `docling` marker to `pyproject.toml`**

Find the `[tool.pytest.ini_options]` block and append/extend the `markers` list:

```toml
markers = [
    "docling: live Docling tests; only run with `pytest tests/integration -m docling`",
]
```

(If `markers` already exists, append the `"docling: ..."` entry to it.)

- [ ] **Step 5: Verify default `pytest` does NOT collect integration tests**

Run: `~/.virtualenvs/homeFinance/bin/pytest --collect-only 2>&1 | grep test_docling_live | head`
Expected: empty output (the file is not collected by default; the `pytest.mark.docling` marker keeps it out).

Run: `~/.virtualenvs/homeFinance/bin/pytest -v --co tests/integration -m docling`
Expected: 2 tests collected.

- [ ] **Step 6: Commit**

```bash
git add scripts/record_docling_fixtures.py \
        tests/integration/__init__.py \
        tests/integration/test_docling_live.py \
        pyproject.toml
git commit -m "tooling: record_docling_fixtures.py + tests/integration/test_docling_live.py (manual-dispatch)"
```

---

## Task 23: CI — add `test-docling` workflow

**Goal:** A new `.github/workflows/ci-docling.yml` that installs the `[ingest]` extra and runs `pytest tests/integration -m docling`. Triggered only by `workflow_dispatch`. The existing `ci.yml` is left unchanged — it stays lean.

**Files:**
- Create: `.github/workflows/ci-docling.yml`

- [ ] **Step 1: Create the workflow**

```yaml
name: ci-docling

on:
  workflow_dispatch:

jobs:
  test-docling:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install with [ingest] extra
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev,ingest]"

      - name: Run live Docling integration tests
        run: pytest tests/integration -m docling -v
```

- [ ] **Step 2: Sanity-check the YAML**

Run:
```bash
~/.virtualenvs/homeFinance/bin/python -c "
import importlib.util, pathlib
# Bare minimum: file exists and looks like a YAML document.
text = pathlib.Path('.github/workflows/ci-docling.yml').read_text()
assert 'workflow_dispatch' in text
assert 'pytest tests/integration' in text
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-docling.yml
git commit -m "ci: add manual-dispatch test-docling workflow for live integration tests"
```

---

## Task 24: Quickstart + architecture + CHANGELOG for SP2

**Goal:** Update user-facing docs to mention statement ingestion alongside YNAB sync. Append to `CHANGELOG.md` under `[Unreleased] / ### Added`.

**Files:**
- Modify: `README.md`
- Modify: `docs/quickstart.md`
- Modify: `docs/architecture.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update `README.md`** — in the "What it does" section, add bullets:

Find the existing bullet list and add (preserving existing entries):

```markdown
- Ingests **statement files** (CSV / OFX / QFX / PDF via Docling) into the same canonical store, with a two-phase confirm/reject lifecycle so the parser's output is never trusted without human review.
- 12 read tools (8 from SP1 plus `ingest_statement`, `list_batches`, `confirm_batch`, `reject_batch`).
- Ships a third skill (`homefinance-import-statement`) for guided statement imports.
```

In the install section, add a note:

```markdown
**Lean install** (`pip install -e .`) supports YNAB sync only.
**Full install** (`pip install -e ".[ingest]"`) adds the Docling PDF + OFX/QFX parsers (~500MB of PyTorch + models on first use).
```

- [ ] **Step 2: Update `docs/quickstart.md`** — add a new section "Importing a statement" after the YNAB workflow:

```markdown
## Importing a statement

For accounts YNAB doesn't cover (or for one-off PDF statements), register the account once and then ingest files.

```bash
homefinance accounts add --nickname citi-cc --type credit_card --currency USD
# (For CSV or PDF parsers, also author ~/.homefinance/templates/statement:citi-cc.toml.)
homefinance ingest ~/Downloads/citi-2026-06.pdf --account citi-cc
```

The CLI parses, reconciles balance against the statement's closing total, and shows a preview. Pressing `y` confirms; anything else rejects (deletes the staged rows; keeps the batch row for audit).

For a fully scripted flow, pass `--no-prompt`, then later run `homefinance batch confirm <id>` when you're ready.
```

- [ ] **Step 3: Update `docs/architecture.md`** — under "Layout", extend the `sources/` line and add the statement subtree:

```markdown
sources/
├── base.py         # AccountSource Protocol + RemoteX dataclasses ← the seam (unchanged by SP2)
├── ynab/           # SP1 adapter
└── statement/      # SP2 adapter
    ├── source.py       # StatementAccountSource
    ├── ingest.py       # ingest_file orchestrator + confirm/reject
    ├── archive.py      # source-file archiving
    ├── templates.py    # per-account TOML template loader
    └── parsers/        # Strategy registry; lazy-imported parser impls
```

And add a new section:

```markdown
## Two-phase write path (SP2)

Statement parses don't go straight into the canonical store. Pipeline:

1. `ingest_file` parses + reconciles + stages rows with `status='pending_review'` and `batch_id=<batch>`.
2. The user reviews via the `homefinance-import-statement` skill or the `homefinance ingest` CLI prompt.
3. `confirm_batch` atomically flips the rows to `status='confirmed'`. `reject_batch` deletes them; the `statement_batches` row stays for audit.

`summarize_spending` always filters `status='confirmed'`. `query_transactions` excludes pending rows by default; opt in with `include_pending=True`.
```

- [ ] **Step 4: Update `CHANGELOG.md`** — under the `[Unreleased]` section, add to `### Added`:

```markdown
- SP2 statement ingestion: CSV / OFX / QFX / Docling-PDF parsers behind a Strategy-pattern registry, per-account TOML templates, two-phase write path (`pending_review` → confirm/reject), 4 new MCP tools (`ingest_statement`, `list_batches`, `confirm_batch`, `reject_batch`), 5 new CLI commands (`accounts add`, `ingest`, `batches`, `batch confirm/reject`), and the `homefinance-import-statement` skill. Lean install (`pip install -e .`) keeps the same dependency footprint; statement support gated to the new `[ingest]` extra. Migration 0002 adds `transactions.status` + `transactions.batch_id` and the `statement_batches` table.
```

- [ ] **Step 5: Run the whole test suite one more time**

```bash
~/.virtualenvs/homeFinance/bin/pytest --cov=homefinance --cov-report=term --cov-fail-under=80
~/.virtualenvs/homeFinance/bin/ruff check src tests
~/.virtualenvs/homeFinance/bin/ruff format --check src tests
~/.virtualenvs/homeFinance/bin/mypy
```

Expected: all clean, coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/quickstart.md docs/architecture.md CHANGELOG.md
git commit -m "docs: SP2 quickstart, architecture, changelog updates"
```

---

## Closing — what SP2 delivers

After Task 24 the repository contains:

- A new `statement` AccountSource adapter sitting behind SP1's unchanged seam.
- 4 file-format parsers (CSV, OFX, QFX, Docling PDF) behind a Strategy registry; lazy-imported so the lean install stays lean.
- Atomic two-phase ingest pipeline: stage as `pending_review` → human confirms → flip to `confirmed`. Reject deletes rows; batch metadata preserved.
- 5 new CLI commands, 4 new MCP tools, 3 surgical updates to SP1's MCP read tools.
- A new `homefinance-import-statement` skill; the existing setup + explore skills updated to mention SP2.
- A second CI workflow gated to manual dispatch for live-Docling integration tests; default CI stays under a minute.
- Migration 0002, with `DEFAULT 'confirmed'` on the new `status` column so SP1's YNAB rows need zero touching.

## Plan self-review

Spec coverage verified section-by-section:

| Spec section | Implemented in |
|---|---|
| §3 C-8 (no LLM in money path) | Templates-only parser layer; no Claude call sites in T7-T9 |
| §3 C-9 (every batch needs human confirm) | T11 stages as pending; T12 confirm/reject; T16 CLI prompts inline; T19 skill rule |
| §3 C-10 (lean install stays lean) | T9 lazy import; T8 lazy import; T21 subprocess enforcement test |
| §4.1 Invariant 4 (pending excluded by default) | T14 `query_transactions.include_pending=False`; `summarize_spending` always filters; T17 status column |
| §4.2 parser registry | T6 |
| §4.3 two-phase write path | T11 stages; T12 confirm/reject |
| §4.4 AccountSource Protocol kept; pull empty | T13 |
| §5 layout + [ingest] extra | T1, T3, T9 |
| §6 migration 0002 | T1 |
| §7.1 StatementParser Protocol | T3 |
| §7.2 ParsedStatement | T3 |
| §7.3 per-parser notes (CSV needs template; OFX/QFX don't; Docling needs template) | T7, T8, T9 |
| §7.4 templates at `~/.homefinance/templates/<source_id>.toml` | T4 |
| §8.1-8.5 pipeline + row external_id + file dedup + archive + lifecycle | T10, T11, T12 |
| §8.6 confirm/reject SQL | T12 |
| §9.1 5 new CLI commands | T15, T16, T17 |
| §9.2 4 new MCP tools + 3 SP1 tool updates | T14, T18 |
| §9.3 skills (1 new, 2 edited) | T19, T20 |
| §10.1 parser error model | T3 (exception classes); T11/T15/T16 user-facing messages |
| §10.2 drift policy | T11 (always pending, never reject); T19 skill rule |
| §10.3 three-tier tests | T7-T9 unit; T10-T13 integration; T15-T18 CLI/MCP end-to-end |
| §10.4 Docling carve-out | T9 (Fake double); T22 (record script); T22 (integration test stub) |
| §10.5 lazy-import enforcement | T21 |
| §10.6 CI updates | T23 |
| §10.7 80% coverage threshold | T24 final test run |

No placeholders; type/method names consistent across tasks; commit messages and file paths fully specified.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-13-sp2-statement-ingest.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

