# SP3 — Spending & Cash-Flow Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the homeFinance analytics layer: hybrid categorization (deterministic rule engine + a canonical "mirror-YNAB" taxonomy), cash-flow, recurring/bill forecasting, and anomaly detection — all deterministic, behind 7 new MCP tools + 2 new skills, with one additive migration.

**Architecture:** A new `src/homefinance/analysis/` package holds four pure modules (`categorize`, `cashflow`, `recurring`, `anomaly`) that read the SP1 canonical store via the existing `Store`. Categorization writes two new columns (`transactions.canonical_category`, `transactions.category_source`) through one idempotent pass that derives YNAB categories from their names, fills statement rows from ordered rules, and never clobbers manual edits. Analytics are plain SQL + stdlib arithmetic (no numpy/pandas). MCP tools and a `categorize` CLI group wrap the library; Claude only assists the categorization long tail at the skill layer. See spec: `docs/superpowers/specs/2026-06-15-sp3-analysis-design.md`.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3`), `pydantic` v2, `typer` + `rich`, `yoyo-migrations`, official `mcp` SDK, `pytest`. No new third-party dependencies.

---

## Prerequisites (one-off, before Task 1)

```bash
cd /Users/asachs/Documents/projects/personal/homeFinance
# Branch already created: sp3-analysis (off main, which has SP1+SP2 merged).
git rev-parse --abbrev-ref HEAD   # → sp3-analysis
```

Reuse the SP1/SP2 venv at `~/.virtualenvs/homeFinance/`. Use absolute venv binary paths (`~/.virtualenvs/homeFinance/bin/{python,pytest,mypy,ruff}`); subagent shells don't persist `workon`. The venv already has all deps (incl. `[ingest]`).

**Baseline at start:** full suite = 143 passing.

---

## File Structure

```
src/homefinance/
├── db/migrations/0003-categorization-analytics.sql   # Task 1
├── analysis/
│   ├── __init__.py                                   # exists (empty) from SP1
│   ├── categorize.py                                 # Tasks 2-4
│   ├── cashflow.py                                   # Task 5
│   ├── recurring.py                                  # Task 6
│   └── anomaly.py                                    # Task 7
├── mcp_server/
│   ├── tools.py                                      # Tasks 8-9 (extend)
│   └── __main__.py                                   # Task 9 (wrappers)
└── cli.py                                            # Task 10 (categorize group)

plugin/skills/
├── homefinance-categorize/SKILL.md                   # Task 11
├── homefinance-analyze/SKILL.md                      # Task 12
└── homefinance-explore/SKILL.md                      # Task 12 (edit)

tests/
├── test_categorize.py                                # Tasks 2-4
├── test_cashflow.py                                  # Task 5
├── test_recurring.py                                 # Task 6
├── test_anomaly.py                                   # Task 7
├── test_mcp_tools.py                                 # Tasks 8-9 (extend)
└── test_cli.py                                       # Task 10 (extend)

docs/{quickstart,architecture}.md + README.md + CHANGELOG.md   # Task 13
```

A shared test helper (used by Tasks 2-9) seeds a store with **both** YNAB-categorized rows and statement-uncategorized rows. It is defined inline in `tests/test_categorize.py` Task 2 and copied where needed (the plan repeats it so tasks read independently).

---

## Task 1: Migration 0003 — category_rules + canonical columns

**Files:**
- Create: `src/homefinance/db/migrations/0003-categorization-analytics.sql`

- [ ] **Step 1: Create `src/homefinance/db/migrations/0003-categorization-analytics.sql`**

```sql
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
```

- [ ] **Step 2: Verify the migration applies on a fresh DB and on a DB that already has SP1/SP2 schema**

Run:
```bash
~/.virtualenvs/homeFinance/bin/python -c "
import sqlite3, tempfile, pathlib
from homefinance.db.migrate import migrate
db = pathlib.Path(tempfile.mkdtemp()) / 'm3.sqlite3'
migrate(db)
with sqlite3.connect(db) as c:
    tables = {r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}
    cols = {r[1] for r in c.execute('PRAGMA table_info(transactions)').fetchall()}
assert 'category_rules' in tables, tables
assert {'canonical_category', 'category_source'}.issubset(cols), cols
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 3: Confirm full suite still green (migration is additive, nothing references the new columns yet)**

Run: `~/.virtualenvs/homeFinance/bin/pytest -q`
Expected: `143 passed`.

- [ ] **Step 4: Commit**

```bash
git add src/homefinance/db/migrations/0003-categorization-analytics.sql
git commit -m "feat(db): migration 0003 — category_rules table + transactions canonical_category/category_source"
```

---

## Task 2: Rule CRUD — `add_rule` + `list_rules`

**Files:**
- Create: `src/homefinance/analysis/categorize.py`
- Create: `tests/test_categorize.py`

- [ ] **Step 1: Write failing tests at `tests/test_categorize.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homefinance.analysis.categorize import add_rule, list_rules
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "cat.sqlite3"
    migrate(db)
    return Store.open(db)


def test_add_rule_inserts_and_returns_id(store: Store) -> None:
    rid = add_rule(
        store, priority=10, match_field="payee", pattern="TRADER JOE",
        is_regex=False, canonical_category="Groceries",
    )
    assert isinstance(rid, int) and rid >= 1
    rows = list_rules(store)
    assert len(rows) == 1
    assert rows[0]["pattern"] == "TRADER JOE"
    assert rows[0]["canonical_category"] == "Groceries"
    assert rows[0]["match_field"] == "payee"
    assert rows[0]["is_regex"] == 0


def test_list_rules_ordered_by_priority_then_id(store: Store) -> None:
    add_rule(store, priority=20, match_field="payee", pattern="B", is_regex=False, canonical_category="X")
    add_rule(store, priority=10, match_field="payee", pattern="A", is_regex=False, canonical_category="Y")
    add_rule(store, priority=10, match_field="memo", pattern="C", is_regex=False, canonical_category="Z")
    patterns = [r["pattern"] for r in list_rules(store)]
    assert patterns == ["A", "C", "B"]  # priority 10 (A then C by id), then 20 (B)


def test_add_rule_rejects_bad_match_field(store: Store) -> None:
    with pytest.raises(ValueError, match="match_field"):
        add_rule(store, priority=1, match_field="banana", pattern="x",
                 is_regex=False, canonical_category="X")


def test_add_rule_rejects_invalid_regex(store: Store) -> None:
    with pytest.raises(ValueError, match="regex"):
        add_rule(store, priority=1, match_field="payee", pattern="(unclosed",
                 is_regex=True, canonical_category="X")


def test_add_rule_rejects_empty_pattern_or_category(store: Store) -> None:
    with pytest.raises(ValueError):
        add_rule(store, priority=1, match_field="payee", pattern="",
                 is_regex=False, canonical_category="X")
    with pytest.raises(ValueError):
        add_rule(store, priority=1, match_field="payee", pattern="x",
                 is_regex=False, canonical_category="")
```

- [ ] **Step 2: Run to confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.analysis.categorize'`.

- [ ] **Step 3: Implement `src/homefinance/analysis/categorize.py`** (rule CRUD only; the pass + helpers land in Tasks 3-4)

```python
"""Categorization: deterministic rule engine + the idempotent apply pass.

Built across SP3 Tasks 2-4:
- Task 2: rule CRUD (add_rule, list_rules) + validation
- Task 3: apply_categorization (the idempotent pass)
- Task 4: suggest_categories, set_manual_category, list_payees
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from homefinance.db.store import Store

_VALID_MATCH_FIELDS = {"payee", "memo"}


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def add_rule(
    store: Store,
    *,
    priority: int,
    match_field: str,
    pattern: str,
    is_regex: bool,
    canonical_category: str,
    note: str | None = None,
) -> int:
    """Insert a categorization rule. Returns its new id.

    Validates match_field, non-empty pattern/category, and (for regex rules)
    that the pattern compiles.
    """
    if match_field not in _VALID_MATCH_FIELDS:
        raise ValueError(
            f"invalid match_field {match_field!r}; one of {sorted(_VALID_MATCH_FIELDS)}"
        )
    if not pattern:
        raise ValueError("pattern must be non-empty")
    if not canonical_category:
        raise ValueError("canonical_category must be non-empty")
    if is_regex:
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"invalid regex {pattern!r}: {e}") from e

    cur = store.execute(
        "INSERT INTO category_rules (priority, match_field, pattern, is_regex, "
        "canonical_category, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (priority, match_field, pattern, int(is_regex), canonical_category, note, _utcnow()),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def list_rules(store: Store) -> list[dict[str, Any]]:
    """All rules ordered by (priority ASC, id ASC) — i.e. evaluation order."""
    rows = store.execute(
        "SELECT id, priority, match_field, pattern, is_regex, canonical_category, "
        "note, created_at FROM category_rules ORDER BY priority ASC, id ASC"
    ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]  # noqa: SIM118
```

- [ ] **Step 4: Run to confirm pass**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/categorize.py tests/test_categorize.py
git commit -m "feat(analysis): category rule CRUD (add_rule/list_rules) with validation"
```

---

## Task 3: The idempotent `apply_categorization` pass

**Files:**
- Modify: `src/homefinance/analysis/categorize.py` (append)
- Modify: `tests/test_categorize.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_categorize.py`**

```python
from homefinance.analysis.categorize import apply_categorization
from homefinance.sources.statement.ingest import ingest_file, register_account
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync


def _seed_mixed_store(store: Store, tmp_path: Path, tiny_fixtures_dir: Path) -> None:
    """YNAB rows (categorized) + statement rows (uncategorized)."""
    run_sync(YNABAccountSource("budget-tiny", FakeYNABClient(tiny_fixtures_dir), nickname="tiny"), store)
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
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
    ingest_file(store, path=fixture, account_nickname="citi-cc",
                config_dir=cfg_dir, archive_dir=tmp_path / "archive")


def test_apply_derives_ynab_categories_from_names(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    result = apply_categorization(store)
    # YNAB non-split row txn-non-split has category cat-groceries → "Groceries".
    row = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE external_id = 'txn-non-split'"
    ).fetchone()
    assert row["canonical_category"] == "Groceries"
    assert row["category_source"] == "ynab"
    assert result["ynab"] >= 1


def test_apply_fills_statement_rows_from_rules(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(store, priority=10, match_field="payee", pattern="Trader Joe",
             is_regex=False, canonical_category="Groceries")
    apply_categorization(store)
    # The statement row whose payee is "Trader Joe's" gets the rule's category.
    rows = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = \"Trader Joe's\""
    ).fetchall()
    assert rows, "expected at least one statement Trader Joe's row"
    assert all(r["canonical_category"] == "Groceries" for r in rows)
    assert all(r["category_source"] == "rule" for r in rows)


def test_apply_is_idempotent(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(store, priority=10, match_field="payee", pattern="Shell",
             is_regex=False, canonical_category="Gas")
    first = apply_categorization(store)
    second = apply_categorization(store)
    assert first == second


def test_apply_respects_manual_then_reapplies_rules(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    # Manually pin a statement row.
    store.execute(
        "UPDATE transactions SET canonical_category = 'Special', category_source = 'manual' "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Shell'"
    )
    # A rule that would otherwise capture Shell.
    add_rule(store, priority=10, match_field="payee", pattern="Shell",
             is_regex=False, canonical_category="Gas")
    apply_categorization(store)
    row = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Shell'"
    ).fetchone()
    assert row["canonical_category"] == "Special"  # manual stuck
    assert row["category_source"] == "manual"


def test_apply_regex_rule_matches(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(store, priority=10, match_field="payee", pattern=r"^Payment\b",
             is_regex=True, canonical_category="Transfer")
    apply_categorization(store)
    row = store.execute(
        "SELECT canonical_category FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Payment'"
    ).fetchone()
    assert row["canonical_category"] == "Transfer"
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v -k apply`
Expected: `ImportError` on `apply_categorization`.

- [ ] **Step 3: Append `apply_categorization` to `src/homefinance/analysis/categorize.py`**

```python
def _compile_rules(rules: list[dict[str, Any]]) -> list[tuple[str, str, re.Pattern[str] | None, str]]:
    """Pre-compile rules into (match_field, pattern, compiled_or_None, category)."""
    out: list[tuple[str, str, re.Pattern[str] | None, str]] = []
    for r in rules:
        compiled = re.compile(r["pattern"]) if r["is_regex"] else None
        out.append((r["match_field"], r["pattern"], compiled, r["canonical_category"]))
    return out


def _match(value: str | None, pattern: str, compiled: re.Pattern[str] | None) -> bool:
    if value is None:
        return False
    if compiled is not None:
        return compiled.search(value) is not None
    return pattern.lower() in value.lower()


def apply_categorization(store: Store, *, source_id: str | None = None) -> dict[str, int]:
    """Re-derive canonical_category for all non-manual rows; return counts.

    Idempotent and reactive to rule changes:
      1. Reset all non-manual rows to NULL.
      2. YNAB-derive: rows with a category_id get that category's name (source='ynab').
      3. Rule-fill: remaining uncategorized rows are matched against ordered rules
         (source='rule'); unmatched stay NULL.
    Manual rows (category_source='manual') are never touched.

    Counts reflect the final state: {'ynab', 'rule', 'manual', 'uncategorized'}.
    """
    scope = "AND source_id = ?" if source_id else ""
    params: tuple[Any, ...] = (source_id,) if source_id else ()

    compiled = _compile_rules(list_rules(store))

    with store.transaction():
        # 1. Reset non-manual rows.
        store.execute(
            f"UPDATE transactions SET canonical_category = NULL, category_source = NULL "
            f"WHERE deleted = 0 AND COALESCE(category_source, '') != 'manual' {scope}",
            params,
        )
        # 2. YNAB-derive from the category name.
        store.execute(
            f"UPDATE transactions SET category_source = 'ynab', "
            f"canonical_category = (SELECT c.name FROM categories c WHERE c.id = transactions.category_id) "
            f"WHERE deleted = 0 AND category_source IS NULL AND category_id IS NOT NULL {scope}",
            params,
        )
        # 3. Rule-fill the rest.
        uncategorized = store.execute(
            f"SELECT id, payee, memo FROM transactions "
            f"WHERE deleted = 0 AND category_source IS NULL {scope}",
            params,
        ).fetchall()
        for row in uncategorized:
            fields = {"payee": row["payee"], "memo": row["memo"]}
            for match_field, pattern, comp, category in compiled:
                if _match(fields.get(match_field), pattern, comp):
                    store.execute(
                        "UPDATE transactions SET canonical_category = ?, category_source = 'rule' "
                        "WHERE id = ?",
                        (category, row["id"]),
                    )
                    break

    # Counts (post-pass), scoped consistently.
    rows = store.execute(
        f"SELECT COALESCE(category_source, 'uncategorized') AS src, COUNT(*) AS n "
        f"FROM transactions WHERE deleted = 0 {scope} GROUP BY src",
        params,
    ).fetchall()
    counts = {"ynab": 0, "rule": 0, "manual": 0, "uncategorized": 0}
    for r in rows:
        counts[r["src"]] = int(r["n"])
    return counts
```

- [ ] **Step 4: Confirm pass**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v`
Expected: `10 passed` (5 from Task 2 + 5 new).

- [ ] **Step 5: Lint + typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/categorize.py tests/test_categorize.py
git commit -m "feat(analysis): idempotent apply_categorization pass (ynab-derive + rule-fill + manual-sticky)"
```

---

## Task 4: `suggest_categories` + `set_manual_category` + `list_payees`

**Files:**
- Modify: `src/homefinance/analysis/categorize.py` (append)
- Modify: `tests/test_categorize.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_categorize.py`**

```python
from homefinance.analysis.categorize import (
    list_payees,
    set_manual_category,
    suggest_categories,
)


def test_suggest_categories_returns_uncategorized_payees_and_ynab_names(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    apply_categorization(store)  # YNAB rows categorized; statement rows not.
    out = suggest_categories(store)
    payees = {p["payee"] for p in out["uncategorized_payees"]}
    assert "Trader Joe's" in payees  # statement row, no rule yet
    assert "Groceries" in out["ynab_category_names"]  # constrain-to set


def test_set_manual_category_pins_a_row(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    apply_categorization(store)
    txn_id = store.execute(
        "SELECT id FROM transactions WHERE source_id = 'statement:citi-cc' "
        "AND payee = \"Trader Joe's\" LIMIT 1"
    ).fetchone()["id"]
    result = set_manual_category(store, transaction_id=txn_id, canonical_category="Groceries")
    assert result["category_source"] == "manual"
    row = store.execute(
        "SELECT canonical_category, category_source FROM transactions WHERE id = ?",
        (txn_id,),
    ).fetchone()
    assert row["canonical_category"] == "Groceries"
    assert row["category_source"] == "manual"


def test_set_manual_category_unknown_id_raises(store: Store) -> None:
    with pytest.raises(KeyError, match="not found"):
        set_manual_category(store, transaction_id="nope", canonical_category="X")


def test_list_payees_returns_distinct_with_counts(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    payees = list_payees(store)
    names = {p["payee"] for p in payees}
    assert "Trader Joe's" in names
    assert all("txn_count" in p for p in payees)


def test_list_payees_filters_by_substring(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    payees = list_payees(store, name_contains="Trader")
    assert payees and all("Trader" in p["payee"] for p in payees)
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v -k "suggest or manual or payees"`
Expected: `ImportError`.

- [ ] **Step 3: Append to `src/homefinance/analysis/categorize.py`**

```python
def suggest_categories(store: Store, *, limit: int = 50) -> dict[str, Any]:
    """Distinct uncategorized payees (+ a sample row id each) plus the set of
    existing YNAB category names, so a caller (Claude) can propose labels
    constrained to the user's own taxonomy.
    """
    payee_rows = store.execute(
        "SELECT payee, COUNT(*) AS n, MIN(id) AS sample_id FROM transactions "
        "WHERE deleted = 0 AND is_split_parent = 0 AND canonical_category IS NULL "
        "AND payee IS NOT NULL AND payee != '' "
        "GROUP BY payee ORDER BY n DESC LIMIT ?",
        (limit,),
    ).fetchall()
    name_rows = store.execute(
        "SELECT DISTINCT name FROM categories WHERE deleted = 0 ORDER BY name"
    ).fetchall()
    return {
        "uncategorized_payees": [
            {"payee": r["payee"], "txn_count": int(r["n"]), "sample_transaction_id": r["sample_id"]}
            for r in payee_rows
        ],
        "ynab_category_names": [r["name"] for r in name_rows],
    }


def set_manual_category(
    store: Store, *, transaction_id: str, canonical_category: str
) -> dict[str, Any]:
    """Pin a single transaction's canonical_category as a sticky manual edit."""
    if not canonical_category:
        raise ValueError("canonical_category must be non-empty")
    exists = store.execute(
        "SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if exists is None:
        raise KeyError(f"transaction {transaction_id!r} not found")
    with store.transaction():
        store.execute(
            "UPDATE transactions SET canonical_category = ?, category_source = 'manual' "
            "WHERE id = ?",
            (canonical_category, transaction_id),
        )
    return {
        "transaction_id": transaction_id,
        "canonical_category": canonical_category,
        "category_source": "manual",
    }


def list_payees(
    store: Store, *, source_id: str | None = None, name_contains: str | None = None
) -> list[dict[str, Any]]:
    """Distinct payees with transaction counts (Leaves view, confirmed-only)."""
    where = ["deleted = 0", "is_split_parent = 0", "status = 'confirmed'",
             "payee IS NOT NULL", "payee != ''"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if name_contains is not None:
        where.append("payee LIKE ?")
        params.append(f"%{name_contains}%")
    rows = store.execute(
        "SELECT payee, COUNT(*) AS n FROM transactions WHERE "
        + " AND ".join(where)
        + " GROUP BY payee ORDER BY n DESC, payee",
        params,
    ).fetchall()
    return [{"payee": r["payee"], "txn_count": int(r["n"])} for r in rows]
```

- [ ] **Step 4: Confirm pass + full categorize suite**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_categorize.py -v`
Expected: `15 passed`.

- [ ] **Step 5: Lint + typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/categorize.py tests/test_categorize.py
git commit -m "feat(analysis): suggest_categories + set_manual_category + list_payees"
```

---

## Task 5: Cash-flow

**Files:**
- Create: `src/homefinance/analysis/cashflow.py`
- Create: `tests/test_cashflow.py`

- [ ] **Step 1: Write failing tests at `tests/test_cashflow.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homefinance.analysis.cashflow import cash_flow
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "cf.sqlite3"
    migrate(db)
    return Store.open(db)


def _src_and_acct(store: Store) -> None:
    now = datetime.now(timezone.utc).isoformat()
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?,?,?,?,?)",
        ("s:a", "statement", "a", None, now),
    )
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, closed, "
        "deleted, currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, "
        "last_synced_at) VALUES ('s:a:account','s:a','account','A','checking',1,0,0,'USD',"
        "NULL,NULL,NULL,NULL)",
    )


def _txn(store: Store, ext: str, date: str, amount: int, *, transfer: str | None = None) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', 'P', NULL, NULL, NULL, NULL, 1, NULL, "
        "NULL, ?, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL)",
        (f"s:a:{ext}", ext, date, amount, transfer),
    )


def test_cash_flow_inflow_outflow_net_by_month(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", 200000)   # +2000 income
    _txn(store, "t2", "2026-06-05", -45670)   # -456.70 outflow
    _txn(store, "t3", "2026-07-02", -10000)   # next month
    rows = cash_flow(store, group_by="month")
    by_period = {r["period"]: r for r in rows}
    assert by_period["2026-06"]["inflow_minor"] == 200000
    assert by_period["2026-06"]["outflow_minor"] == -45670
    assert by_period["2026-06"]["net_minor"] == 154330
    assert by_period["2026-07"]["net_minor"] == -10000


def test_cash_flow_excludes_transfers(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", -50000)                 # real outflow
    _txn(store, "t2", "2026-06-02", -20000, transfer="s:a:account")  # transfer — excluded
    rows = cash_flow(store, group_by="month")
    assert rows[0]["outflow_minor"] == -50000  # transfer not counted


def test_cash_flow_date_range_filter(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", -100)
    _txn(store, "t2", "2026-07-01", -200)
    rows = cash_flow(store, date_from="2026-07-01", date_to="2026-07-31")
    assert len(rows) == 1
    assert rows[0]["period"] == "2026-07"


def test_cash_flow_empty_store_returns_empty(store: Store) -> None:
    assert cash_flow(store) == []
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_cashflow.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/analysis/cashflow.py`**

```python
"""Cash-flow analysis: inflow / outflow / net per period.

Disciplines (per spec §8.1): Leaves view (is_split_parent = 0), deleted = 0,
status = 'confirmed', and transfers (transfer_account_id IS NOT NULL) are
excluded so internal moves never inflate income or spending.
"""

from __future__ import annotations

from typing import Any, Literal

from homefinance.db.store import Store

Period = Literal["month", "week"]

# SQLite strftime grouping expressions.
_PERIOD_EXPR: dict[str, str] = {
    "month": "substr(date, 1, 7)",                 # YYYY-MM
    "week": "strftime('%Y-W%W', date)",            # ISO-ish year-week
}


def cash_flow(
    store: Store,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: Period = "month",
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Inflow/outflow/net per period (most-recent period first)."""
    expr = _PERIOD_EXPR.get(group_by)
    if expr is None:
        raise ValueError(f"invalid group_by: {group_by!r}")

    where = ["deleted = 0", "is_split_parent = 0", "status = 'confirmed'",
             "transfer_account_id IS NULL"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if date_from is not None:
        where.append("date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("date <= ?")
        params.append(date_to)

    sql = (
        f"SELECT {expr} AS period, "
        "COALESCE(SUM(CASE WHEN amount_minor > 0 THEN amount_minor END), 0) AS inflow_minor, "
        "COALESCE(SUM(CASE WHEN amount_minor < 0 THEN amount_minor END), 0) AS outflow_minor, "
        "COALESCE(SUM(amount_minor), 0) AS net_minor, "
        "COUNT(*) AS count "
        "FROM transactions WHERE " + " AND ".join(where) +
        f" GROUP BY {expr} ORDER BY period DESC"
    )
    return [
        {
            "period": r["period"],
            "inflow_minor": int(r["inflow_minor"]),
            "outflow_minor": int(r["outflow_minor"]),
            "net_minor": int(r["net_minor"]),
            "count": int(r["count"]),
        }
        for r in store.execute(sql, params).fetchall()
    ]
```

- [ ] **Step 4: Confirm pass + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cashflow.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/cashflow.py tests/test_cashflow.py
git commit -m "feat(analysis): cash_flow — inflow/outflow/net per period, transfers excluded"
```
Expected: `4 passed`.

---

## Task 6: Recurring detection + forecast

**Files:**
- Create: `src/homefinance/analysis/recurring.py`
- Create: `tests/test_recurring.py`

- [ ] **Step 1: Write failing tests at `tests/test_recurring.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homefinance.analysis.recurring import detect_recurring
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "rec.sqlite3"
    migrate(db)
    return Store.open(db)


def _seed(store: Store) -> None:
    now = datetime.now(timezone.utc).isoformat()
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES ('s:a','statement','a',NULL,?)",
        (now,),
    )
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, closed, deleted, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, last_synced_at) "
        "VALUES ('s:a:account','s:a','account','A','checking',1,0,0,'USD',NULL,NULL,NULL,NULL)",
    )


def _txn(store: Store, ext: str, date: str, amount: int, payee: str) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', ?, NULL, NULL, NULL, NULL, 1, NULL, NULL, "
        "NULL, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL)",
        (f"s:a:{ext}", ext, date, amount, payee),
    )


def test_detect_recurring_monthly_series(store: Store) -> None:
    _seed(store)
    # A clean monthly subscription, 4 occurrences ~30 days apart.
    for i, d in enumerate(["2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]):
        _txn(store, f"net{i}", d, -1599, "Netflix")
    series = detect_recurring(store, min_occurrences=3)
    netflix = next(s for s in series if s["payee"] == "Netflix")
    assert netflix["occurrences"] == 4
    assert netflix["typical_amount_minor"] == -1599
    assert netflix["cadence"] == "monthly"
    assert netflix["next_expected"] >= "2026-06-25"  # ~one month after last
    assert netflix["confidence"] > 0.5


def test_detect_recurring_ignores_too_few_occurrences(store: Store) -> None:
    _seed(store)
    _txn(store, "a", "2026-05-01", -500, "OneOff")
    _txn(store, "b", "2026-06-01", -500, "OneOff")  # only 2
    series = detect_recurring(store, min_occurrences=3)
    assert all(s["payee"] != "OneOff" for s in series)


def test_detect_recurring_ignores_irregular(store: Store) -> None:
    _seed(store)
    # Same payee+amount but wildly irregular gaps.
    for i, d in enumerate(["2026-01-01", "2026-01-03", "2026-06-01"]):
        _txn(store, f"x{i}", d, -1000, "Random")
    series = detect_recurring(store, min_occurrences=3)
    rec = [s for s in series if s["payee"] == "Random"]
    # Either excluded, or surfaced with low confidence — never a clean cadence.
    assert not rec or rec[0]["confidence"] < 0.5


def test_detect_recurring_empty_store(store: Store) -> None:
    assert detect_recurring(store) == []
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_recurring.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/analysis/recurring.py`**

```python
"""Recurring-charge detection + next-occurrence forecast.

Groups confirmed, non-transfer Leaves transactions by (payee, amount within a
tolerance), then looks for a regular cadence via the median gap between dates.
Pure stdlib arithmetic — no numpy.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from statistics import median
from typing import Any

from homefinance.db.store import Store

# (label, low_days, high_days) — median gap falling in [low, high] gets the label.
_CADENCES: list[tuple[str, int, int]] = [
    ("weekly", 6, 8),
    ("biweekly", 12, 16),
    ("monthly", 27, 33),
    ("quarterly", 85, 95),
    ("annual", 358, 372),
]


def _cadence_label(median_gap_days: float) -> str | None:
    for label, lo, hi in _CADENCES:
        if lo <= median_gap_days <= hi:
            return label
    return None


def _confidence(gaps: list[int], median_gap: float) -> float:
    """Higher when gaps are tight around the median. In [0, 1]."""
    if not gaps or median_gap <= 0:
        return 0.0
    avg_dev = sum(abs(g - median_gap) for g in gaps) / len(gaps)
    regularity = max(0.0, 1.0 - (avg_dev / median_gap))
    count_factor = min(1.0, len(gaps) / 5.0)  # saturates at ~6 occurrences
    return round(regularity * count_factor, 3)


def detect_recurring(
    store: Store,
    *,
    min_occurrences: int = 3,
    amount_tolerance_minor: int = 200,
) -> list[dict[str, Any]]:
    """Return detected recurring series, highest confidence first."""
    rows = store.execute(
        "SELECT payee, amount_minor, date FROM transactions "
        "WHERE deleted = 0 AND is_split_parent = 0 AND status = 'confirmed' "
        "AND transfer_account_id IS NULL AND payee IS NOT NULL AND payee != '' "
        "ORDER BY payee, date"
    ).fetchall()

    # Bucket by payee, then cluster amounts within tolerance.
    by_payee: dict[str, list[tuple[int, str]]] = {}
    for r in rows:
        by_payee.setdefault(r["payee"], []).append((int(r["amount_minor"]), r["date"]))

    series: list[dict[str, Any]] = []
    for payee, txns in by_payee.items():
        # Group by amount cluster: sort by amount, greedily cluster within tolerance.
        txns_sorted = sorted(txns)
        clusters: list[list[tuple[int, str]]] = []
        for amount, d in txns_sorted:
            if clusters and abs(amount - clusters[-1][0][0]) <= amount_tolerance_minor:
                clusters[-1].append((amount, d))
            else:
                clusters.append([(amount, d)])

        for cluster in clusters:
            if len(cluster) < min_occurrences:
                continue
            dates = sorted(_date.fromisoformat(d) for _, d in cluster)
            gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            if not gaps:
                continue
            med = median(gaps)
            conf = _confidence(gaps, med)
            last = dates[-1]
            next_expected = (last + timedelta(days=round(med))).isoformat()
            typical = round(median(a for a, _ in cluster))
            series.append({
                "payee": payee,
                "typical_amount_minor": int(typical),
                "occurrences": len(cluster),
                "median_gap_days": round(med, 1),
                "cadence": _cadence_label(med),
                "first_seen": dates[0].isoformat(),
                "last_seen": last.isoformat(),
                "next_expected": next_expected,
                "confidence": conf,
            })

    series.sort(key=lambda s: s["confidence"], reverse=True)
    return series
```

- [ ] **Step 4: Confirm pass + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_recurring.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/recurring.py tests/test_recurring.py
git commit -m "feat(analysis): detect_recurring — median-gap cadence + next-occurrence forecast"
```
Expected: `4 passed`.

---

## Task 7: Anomaly detection

**Files:**
- Create: `src/homefinance/analysis/anomaly.py`
- Create: `tests/test_anomaly.py`

- [ ] **Step 1: Write failing tests at `tests/test_anomaly.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homefinance.analysis.anomaly import detect_anomalies
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "anom.sqlite3"
    migrate(db)
    return Store.open(db)


def _seed(store: Store) -> None:
    now = datetime.now(timezone.utc).isoformat()
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES ('s:a','statement','a',NULL,?)",
        (now,),
    )
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, closed, deleted, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, last_synced_at) "
        "VALUES ('s:a:account','s:a','account','A','checking',1,0,0,'USD',NULL,NULL,NULL,NULL)",
    )


def _txn(store: Store, ext: str, date: str, amount: int, cat: str) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id, "
        "canonical_category, category_source) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', 'P', NULL, NULL, NULL, NULL, 1, NULL, NULL, "
        "NULL, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL, ?, 'manual')",
        (f"s:a:{ext}", ext, date, amount, cat),
    )


def test_detect_anomalies_flags_category_month_spike(store: Store) -> None:
    _seed(store)
    # Five quiet months ~ -100/mo in Dining, then a -5000 blowout month.
    base_months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    for i, m in enumerate(base_months):
        _txn(store, f"d{i}", f"{m}-15", -10000, "Dining")
    _txn(store, "spike", "2026-06-15", -500000, "Dining")
    flags = detect_anomalies(store, trailing_months=6, z_threshold=2.0)
    dining = [f for f in flags if f["canonical_category"] == "Dining" and f["period"] == "2026-06"]
    assert dining, "expected June Dining spike to be flagged"


def test_detect_anomalies_skips_insufficient_history(store: Store) -> None:
    _seed(store)
    _txn(store, "a", "2026-06-15", -999999, "Sparse")  # only one month of data
    flags = detect_anomalies(store)
    assert all(f["canonical_category"] != "Sparse" for f in flags)


def test_detect_anomalies_empty_store(store: Store) -> None:
    assert detect_anomalies(store) == []
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_anomaly.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/analysis/anomaly.py`**

```python
"""Anomaly detection: per-(canonical_category, month) spend spikes.

For each category, build a monthly spend series, compute the trailing-window
mean and population standard deviation, and flag any month exceeding
mean + z_threshold·σ. Categories with too few months to form a baseline are
skipped (never falsely flagged). Pure stdlib — no numpy.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from homefinance.db.store import Store


def detect_anomalies(
    store: Store,
    *,
    trailing_months: int = 6,
    z_threshold: float = 2.0,
    min_history_months: int = 3,
) -> list[dict[str, Any]]:
    """Flag category-month spend spikes. Most-recent flags first."""
    rows = store.execute(
        "SELECT canonical_category AS cat, substr(date, 1, 7) AS period, "
        "SUM(ABS(amount_minor)) AS spend "
        "FROM transactions "
        "WHERE deleted = 0 AND is_split_parent = 0 AND status = 'confirmed' "
        "AND transfer_account_id IS NULL AND amount_minor < 0 "
        "AND canonical_category IS NOT NULL "
        "GROUP BY cat, period ORDER BY cat, period"
    ).fetchall()

    by_cat: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        by_cat.setdefault(r["cat"], []).append((r["period"], int(r["spend"])))

    flags: list[dict[str, Any]] = []
    for cat, series in by_cat.items():
        if len(series) < min_history_months:
            continue
        # Walk forward; for each month, baseline = up to `trailing_months` prior months.
        for i in range(min_history_months, len(series)):
            window = [spend for _, spend in series[max(0, i - trailing_months):i]]
            if len(window) < min_history_months - 1 or len(window) < 2:
                continue
            mu = mean(window)
            sigma = pstdev(window)
            period, spend = series[i]
            if sigma > 0 and spend > mu + z_threshold * sigma:
                flags.append({
                    "canonical_category": cat,
                    "period": period,
                    "spend_minor": spend,
                    "baseline_mean_minor": round(mu),
                    "baseline_stdev_minor": round(sigma),
                    "z_score": round((spend - mu) / sigma, 2),
                })
    flags.sort(key=lambda f: f["period"], reverse=True)
    return flags
```

- [ ] **Step 4: Confirm pass + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_anomaly.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/analysis/anomaly.py tests/test_anomaly.py
git commit -m "feat(analysis): detect_anomalies — category-month z-score baseline"
```
Expected: `3 passed`.

---

## Task 8: Extend `summarize_spending` with `canonical_category`

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py`
- Modify: `tests/test_mcp_tools.py` (append)

- [ ] **Step 1: Append failing test to `tests/test_mcp_tools.py`**

```python
def test_summarize_spending_by_canonical_category(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    from homefinance.analysis.categorize import apply_categorization

    apply_categorization(synced_store)  # YNAB rows get canonical names
    rows = summarize_spending(synced_store, group_by="canonical_category")
    keys = {r["key"] for r in rows}
    # tiny YNAB fixture has Groceries/Gas categories on its rows
    assert "Groceries" in keys
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v -k canonical_category`
Expected: FAIL — `invalid group_by: 'canonical_category'`.

- [ ] **Step 3: Extend `summarize_spending` in `src/homefinance/mcp_server/tools.py`**

Find the `GroupBy` type alias and the `_GROUP_EXPR` dict. Add `canonical_category`:

```python
GroupBy = Literal["category", "payee", "month", "account", "day_of_week", "canonical_category"]


_GROUP_EXPR: dict[str, str] = {
    "category":     "COALESCE(c.name, '(uncategorized)')",
    "payee":        "COALESCE(t.payee, '(no payee)')",
    "month":        "substr(t.date, 1, 7)",
    "account":      "a.name",
    "day_of_week":  "CAST(strftime('%w', t.date) AS INTEGER)",
    "canonical_category": "COALESCE(t.canonical_category, '(uncategorized)')",
}
```

(The existing function already builds the SQL from `_GROUP_EXPR[group_by]` and joins `categories c` / `accounts a`, so no other change is needed — `t.canonical_category` is a column on the `transactions t` alias.)

- [ ] **Step 4: Confirm pass + full MCP suite**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v`
Expected: all pass (existing + 1 new).

- [ ] **Step 5: Lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/mcp_server/tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): summarize_spending gains group_by='canonical_category'"
```

---

## Task 9: Wire the 7 new MCP tools

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py` (append thin wrappers around the analysis library)
- Modify: `src/homefinance/mcp_server/__main__.py` (`@mcp.tool()` wrappers)
- Modify: `tests/test_mcp_tools.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`**

```python
from homefinance.mcp_server.tools import (
    add_category_rule as mcp_add_category_rule,
    apply_categorization as mcp_apply_categorization,
    cash_flow as mcp_cash_flow,
    detect_anomalies as mcp_detect_anomalies,
    detect_recurring as mcp_detect_recurring,
    list_category_rules as mcp_list_category_rules,
    list_payees as mcp_list_payees,
    set_transaction_category as mcp_set_transaction_category,
    suggest_categories as mcp_suggest_categories,
)


def test_mcp_add_and_list_category_rules(synced_store: Store) -> None:
    rid = mcp_add_category_rule(
        synced_store, priority=10, match_field="payee", pattern="Shell",
        is_regex=False, canonical_category="Gas",
    )
    assert rid >= 1
    rules = mcp_list_category_rules(synced_store)
    assert any(r["pattern"] == "Shell" for r in rules)


def test_mcp_apply_categorization_counts(synced_store: Store) -> None:
    result = mcp_apply_categorization(synced_store)
    assert set(result) >= {"ynab", "rule", "manual", "uncategorized"}


def test_mcp_suggest_and_set_and_list_payees(synced_store: Store) -> None:
    mcp_apply_categorization(synced_store)
    out = mcp_suggest_categories(synced_store)
    assert "ynab_category_names" in out
    payees = mcp_list_payees(synced_store)
    assert isinstance(payees, list)


def test_mcp_cash_flow_recurring_anomaly_callable(synced_store: Store) -> None:
    assert isinstance(mcp_cash_flow(synced_store), list)
    assert isinstance(mcp_detect_recurring(synced_store), list)
    assert isinstance(mcp_detect_anomalies(synced_store), list)


def test_mcp_set_transaction_category(synced_store: Store) -> None:
    txn_id = synced_store.execute(
        "SELECT id FROM transactions LIMIT 1"
    ).fetchone()["id"]
    result = mcp_set_transaction_category(
        synced_store, transaction_id=txn_id, canonical_category="Groceries"
    )
    assert result["category_source"] == "manual"
```

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v -k "mcp_add or mcp_apply or mcp_suggest or mcp_cash or mcp_set"`
Expected: `ImportError`.

- [ ] **Step 3: Append to `src/homefinance/mcp_server/tools.py`**

```python
from homefinance.analysis.anomaly import detect_anomalies as _detect_anomalies_lib
from homefinance.analysis.cashflow import cash_flow as _cash_flow_lib
from homefinance.analysis.categorize import (
    add_rule as _add_rule_lib,
    apply_categorization as _apply_categorization_lib,
    list_payees as _list_payees_lib,
    list_rules as _list_rules_lib,
    set_manual_category as _set_manual_category_lib,
    suggest_categories as _suggest_categories_lib,
)
from homefinance.analysis.recurring import detect_recurring as _detect_recurring_lib


def add_category_rule(
    store: Store,
    *,
    priority: int,
    match_field: str,
    pattern: str,
    is_regex: bool = False,
    canonical_category: str,
    note: str | None = None,
) -> int:
    return _add_rule_lib(
        store, priority=priority, match_field=match_field, pattern=pattern,
        is_regex=is_regex, canonical_category=canonical_category, note=note,
    )


def list_category_rules(store: Store) -> list[dict[str, Any]]:
    return _list_rules_lib(store)


def apply_categorization(store: Store, *, source_id: str | None = None) -> dict[str, int]:
    return _apply_categorization_lib(store, source_id=source_id)


def suggest_categories(store: Store, *, limit: int = 50) -> dict[str, Any]:
    return _suggest_categories_lib(store, limit=limit)


def set_transaction_category(
    store: Store, *, transaction_id: str, canonical_category: str
) -> dict[str, Any]:
    return _set_manual_category_lib(
        store, transaction_id=transaction_id, canonical_category=canonical_category
    )


def list_payees(
    store: Store, *, source_id: str | None = None, name_contains: str | None = None
) -> list[dict[str, Any]]:
    return _list_payees_lib(store, source_id=source_id, name_contains=name_contains)


def cash_flow(
    store: Store,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str = "month",
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    return _cash_flow_lib(
        store, date_from=date_from, date_to=date_to,
        group_by=group_by, source_id=source_id,  # type: ignore[arg-type]
    )


def detect_recurring(
    store: Store, *, min_occurrences: int = 3, amount_tolerance_minor: int = 200
) -> list[dict[str, Any]]:
    return _detect_recurring_lib(
        store, min_occurrences=min_occurrences, amount_tolerance_minor=amount_tolerance_minor
    )


def detect_anomalies(
    store: Store, *, trailing_months: int = 6, z_threshold: float = 2.0
) -> list[dict[str, Any]]:
    return _detect_anomalies_lib(
        store, trailing_months=trailing_months, z_threshold=z_threshold
    )
```

- [ ] **Step 4: Append `@mcp.tool()` wrappers to `src/homefinance/mcp_server/__main__.py`**

```python
@mcp.tool()
def add_category_rule(
    priority: int,
    match_field: str,
    pattern: str,
    canonical_category: str,
    is_regex: bool = False,
    note: str | None = None,
) -> int:
    """Append a categorization rule. match_field is 'payee' or 'memo'."""
    return _tools.add_category_rule(
        _store_cached(), priority=priority, match_field=match_field, pattern=pattern,
        is_regex=is_regex, canonical_category=canonical_category, note=note,
    )


@mcp.tool()
def list_category_rules() -> list[dict]:
    """All categorization rules in evaluation order."""
    return _tools.list_category_rules(_store_cached())


@mcp.tool()
def apply_categorization(source_id: str | None = None) -> dict:
    """Re-derive canonical categories for all non-manual rows. Returns counts."""
    return _tools.apply_categorization(_store_cached(), source_id=source_id)


@mcp.tool()
def suggest_categories(limit: int = 50) -> dict:
    """Uncategorized payees + the YNAB category-name set to constrain suggestions."""
    return _tools.suggest_categories(_store_cached(), limit=limit)


@mcp.tool()
def set_transaction_category(transaction_id: str, canonical_category: str) -> dict:
    """Pin one transaction's canonical_category as a sticky manual edit."""
    return _tools.set_transaction_category(
        _store_cached(), transaction_id=transaction_id, canonical_category=canonical_category
    )


@mcp.tool()
def list_payees(source_id: str | None = None, name_contains: str | None = None) -> list[dict]:
    """Distinct payees with transaction counts."""
    return _tools.list_payees(_store_cached(), source_id=source_id, name_contains=name_contains)


@mcp.tool()
def cash_flow(
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str = "month",
    source_id: str | None = None,
) -> list[dict]:
    """Inflow/outflow/net per period (transfers excluded, confirmed-only)."""
    return _tools.cash_flow(
        _store_cached(), date_from=date_from, date_to=date_to,
        group_by=group_by, source_id=source_id,
    )


@mcp.tool()
def detect_recurring(min_occurrences: int = 3, amount_tolerance_minor: int = 200) -> list[dict]:
    """Detected recurring charges + next-occurrence forecast."""
    return _tools.detect_recurring(
        _store_cached(), min_occurrences=min_occurrences,
        amount_tolerance_minor=amount_tolerance_minor,
    )


@mcp.tool()
def detect_anomalies(trailing_months: int = 6, z_threshold: float = 2.0) -> list[dict]:
    """Category-month spend spikes vs a trailing baseline."""
    return _tools.detect_anomalies(
        _store_cached(), trailing_months=trailing_months, z_threshold=z_threshold
    )
```

- [ ] **Step 5: Confirm pass + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): 7 SP3 analysis tools (categorize/suggest/payees/cash_flow/recurring/anomaly)"
```

---

## Task 10: CLI `categorize` command group

**Files:**
- Modify: `src/homefinance/cli.py`
- Modify: `tests/test_cli.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
def test_categorize_rules_add_and_list(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    add = runner.invoke(app, ["categorize", "rules", "add", "--field", "payee",
                              "--pattern", "Shell", "--category", "Gas"])
    assert add.exit_code == 0, add.stdout
    assert "Added rule" in add.stdout
    listing = runner.invoke(app, ["categorize", "rules", "list"])
    assert listing.exit_code == 0
    assert "Shell" in listing.stdout
    assert "Gas" in listing.stdout


def test_categorize_apply_runs(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny"])  # sync so YNAB rows exist
    monkeypatch.setenv("HOMEFINANCE_YNAB_TOKEN", "T")
    result = runner.invoke(app, ["categorize", "apply"])
    assert result.exit_code == 0, result.stdout
    assert "ynab" in result.stdout.lower() or "categoriz" in result.stdout.lower()


def test_categorize_rules_add_invalid_field_errors(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    result = runner.invoke(app, ["categorize", "rules", "add", "--field", "banana",
                                 "--pattern", "x", "--category", "Y"])
    assert result.exit_code != 0
```

Note: `test_categorize_apply_runs` syncs YNAB (no `--no-sync`); ensure `_patch_client` is active so the fake client is used.

- [ ] **Step 2: Confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v -k categorize`
Expected: `No such command 'categorize'`.

- [ ] **Step 3: Add the `categorize` group to `src/homefinance/cli.py`** (append near the other sub-typers)

```python
from homefinance.analysis.categorize import (
    add_rule as _add_rule,
    apply_categorization as _apply_categorization,
    list_rules as _list_rules,
)


categorize_app = typer.Typer(help="Categorize transactions with rules.")
app.add_typer(categorize_app, name="categorize")

rules_app = typer.Typer(help="Manage categorization rules.")
categorize_app.add_typer(rules_app, name="rules")


@categorize_app.command("apply")
def categorize_apply(
    source: str | None = typer.Option(None, "--source"),
) -> None:
    """Re-derive canonical categories for all non-manual rows."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)
    counts = _apply_categorization(store, source_id=source)
    table = Table(title="Categorization")
    table.add_column("source")
    table.add_column("rows", justify="right")
    for key in ("ynab", "rule", "manual", "uncategorized"):
        table.add_row(key, str(counts[key]))
    console.print(table)


@rules_app.command("add")
def categorize_rules_add(
    field: str = typer.Option(..., "--field", help="payee | memo"),
    pattern: str = typer.Option(..., "--pattern"),
    category: str = typer.Option(..., "--category"),
    regex: bool = typer.Option(False, "--regex"),
    priority: int = typer.Option(100, "--priority"),
) -> None:
    """Add a categorization rule."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)
    try:
        rid = _add_rule(store, priority=priority, match_field=field, pattern=pattern,
                        is_regex=regex, canonical_category=category)
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Added rule[/] #{rid}: {field} ~ {pattern!r} → {category}")


@rules_app.command("list")
def categorize_rules_list() -> None:
    """List categorization rules in evaluation order."""
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print("[yellow]No database yet.[/]")
        return
    store = Store.open(cfg.db_path)
    rows = _list_rules(store)
    if not rows:
        console.print("[yellow]No rules defined.[/]")
        return
    table = Table(title="Categorization Rules")
    table.add_column("id", justify="right")
    table.add_column("priority", justify="right")
    table.add_column("field")
    table.add_column("pattern")
    table.add_column("regex")
    table.add_column("category")
    for r in rows:
        table.add_row(str(r["id"]), str(r["priority"]), r["match_field"],
                      r["pattern"], "yes" if r["is_regex"] else "no", r["canonical_category"])
    console.print(table)
```

- [ ] **Step 4: Confirm pass + full CLI suite + lint + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): categorize apply + rules add/list command group"
```

---

## Task 11: `homefinance-categorize` skill

**Files:**
- Create: `plugin/skills/homefinance-categorize/SKILL.md`

- [ ] **Step 1: Create `plugin/skills/homefinance-categorize/SKILL.md`**

```markdown
---
name: homefinance-categorize
description: Use when the user wants to categorize transactions, asks why statement spending shows as "(uncategorized)", wants to build or review categorization rules, or asks Claude to suggest categories for unknown payees. Drives the hybrid rule + suggestion loop.
---

# homefinance — Categorize transactions

You help the user assign a canonical category to every transaction so cross-source spending analysis works. The canonical vocabulary **mirrors their YNAB category names**.

## How categorization works

- YNAB rows are already categorized; the system derives their `canonical_category` from the YNAB category name automatically.
- Statement-ingested rows start uncategorized. They get a category from **ordered rules** (deterministic) or a **manual assignment** (sticky).
- You assist only the **long tail** — payees no rule matches yet. You never touch amounts.

## The loop

1. **Run `apply_categorization`.** Report the counts (ynab / rule / manual / uncategorized).
2. If `uncategorized > 0`, call **`suggest_categories`**. It returns the uncategorized payees (with counts) and the user's existing YNAB category names.
3. **Propose a category for each payee — constrained to the YNAB category names** the tool returned. Only invent a new name if nothing fits, and say so explicitly.
4. For each, ask the user to choose. Then either:
   - **Promote to a rule** (preferred for recurring payees): `add_category_rule(priority, match_field='payee', pattern=<stable substring>, canonical_category=<choice>)`. Rules make future imports self-categorize.
   - **Pin one row** (for true one-offs): `set_transaction_category(transaction_id, canonical_category)`.
5. **Re-run `apply_categorization`** so new rules take effect, and report the improved counts.

## Rules

- **Suggest category labels only — never amounts.** Money is never inferred here.
- **Always get the user's confirmation** before writing a rule or a manual category.
- Prefer **rules over manual** for anything that will recur — coverage then compounds and the system converges to fully deterministic.
- Keep rule patterns **stable and specific** (a distinctive substring of the payee), so they don't over-match.
- Manual assignments are sticky: re-running `apply_categorization` never overwrites them.

## After categorization improves

Point the user at `/homefinance:analyze` (cash flow, trends, recurring, anomalies) or `summarize_spending(group_by='canonical_category')`.
```

- [ ] **Step 2: Verify frontmatter parses**

```bash
~/.virtualenvs/homeFinance/bin/python -c "
import re, pathlib
t = pathlib.Path('plugin/skills/homefinance-categorize/SKILL.md').read_text()
m = re.match(r'^---\n(.*?)\n---', t, re.DOTALL); assert m
assert 'name: homefinance-categorize' in m.group(1)
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/homefinance-categorize/SKILL.md
git commit -m "feat(plugin): homefinance-categorize skill (rule + suggestion loop)"
```

---

## Task 12: `homefinance-analyze` skill + `homefinance-explore` edit

**Files:**
- Create: `plugin/skills/homefinance-analyze/SKILL.md`
- Modify: `plugin/skills/homefinance-explore/SKILL.md`

- [ ] **Step 1: Create `plugin/skills/homefinance-analyze/SKILL.md`**

```markdown
---
name: homefinance-analyze
description: Use when the user asks about cash flow, income vs spending, spending trends over time, recurring charges or subscriptions, upcoming bills, or unusual/anomalous spending. Covers the SP3 analytics tools.
---

# homefinance — Analyze spending & cash flow

You answer analytical questions over the user's categorized transaction store.

## Tools

- `cash_flow(date_from?, date_to?, group_by='month'|'week', source_id?)` — inflow / outflow / net per period. **Transfers are excluded** (internal moves don't count as income or spending). Confirmed-only.
- `summarize_spending(group_by='canonical_category', …)` — spending by your unified category vocabulary across YNAB + statements. Prefer `canonical_category` over the per-source `category` for cross-source views.
- `detect_recurring(min_occurrences?, amount_tolerance_minor?)` — recurring charges with a typical amount, cadence (weekly/monthly/…), last-seen, **next-expected** date, and a confidence score.
- `detect_anomalies(trailing_months?, z_threshold?)` — category-month spend spikes vs a trailing baseline, with z-scores.

## How to answer well

- **Money is signed integer cents.** Convert to dollars (`/100`, two decimals) only in your prose, never in tool arguments.
- For "how am I doing?" → `cash_flow(group_by='month')`; report net per month and the trend.
- For "where does my money go?" → `summarize_spending(group_by='canonical_category')` over the period.
- For "what subscriptions am I paying?" → `detect_recurring`; lead with the highest-confidence series and the next-expected dates.
- For "anything unusual?" → `detect_anomalies`; explain each flag in plain terms (category X was N× its usual month).
- If results look thin, check whether categorization has been run — suggest `/homefinance:categorize`. Uncategorized spend shows up under `(uncategorized)`.
- Never include `pending_review` (unconfirmed statement) rows — the tools already exclude them.

## Honesty

If a question needs something these tools don't compute (budget targets, projections beyond a recurring forecast, retirement planning), say so — those are out of scope for SP3 (retirement is SP4).
```

- [ ] **Step 2: Edit `plugin/skills/homefinance-explore/SKILL.md`** — append to its "Rules" bullet list (after the existing pending-batch bullets from SP2):

```markdown
- For category questions, prefer **`summarize_spending(group_by='canonical_category')`** — it unifies YNAB and statement categories. If statement spend is large and shows under `(uncategorized)`, suggest `/homefinance:categorize` first.
- For cash flow, trends, recurring charges, or anomalies, hand off to **`/homefinance:analyze`** rather than answering from raw `query_transactions` output.
```

- [ ] **Step 3: Verify frontmatter + commit**

```bash
~/.virtualenvs/homeFinance/bin/python -c "
import re, pathlib
t = pathlib.Path('plugin/skills/homefinance-analyze/SKILL.md').read_text()
m = re.match(r'^---\n(.*?)\n---', t, re.DOTALL); assert m
assert 'name: homefinance-analyze' in m.group(1)
print('OK')
"
git add plugin/skills/homefinance-analyze/SKILL.md plugin/skills/homefinance-explore/SKILL.md
git commit -m "feat(plugin): homefinance-analyze skill + explore edits for SP3"
```

---

## Task 13: Docs — README / quickstart / architecture / CHANGELOG + final verification

**Files:**
- Modify: `README.md`, `docs/quickstart.md`, `docs/architecture.md`, `CHANGELOG.md`

- [ ] **Step 1: Update `README.md`** — in the "What it does" bullet list, add (preserving existing bullets):

```markdown
- **Analyzes** spending: hybrid categorization (rules + Claude-assisted long tail) into a unified taxonomy, cash-flow (income vs outflow, transfers excluded), recurring-charge detection with next-bill forecasts, and category anomaly detection.
- 19 read/analysis MCP tools and four skills (`homefinance-setup`, `homefinance-explore`, `homefinance-import-statement`, `homefinance-categorize`, `homefinance-analyze`).
```

And update the program-status line to note SP3 is implemented.

- [ ] **Step 2: Append a section to `docs/quickstart.md`** after the "Importing a statement" section:

```markdown
## Categorizing & analyzing

YNAB transactions arrive categorized; statement-imported ones don't. Unify them once, then analyze.

```bash
# Add a rule, then apply (re-runnable any time)
homefinance categorize rules add --field payee --pattern "TRADER JOE" --category Groceries
homefinance categorize apply
```

From Claude Code, the `/homefinance:categorize` skill drives a faster loop: it surfaces uncategorized payees and proposes categories (constrained to your YNAB names) for you to confirm or promote into rules.

Then ask analytical questions via `/homefinance:analyze`:

> How did my cash flow look over the last 6 months?
> What subscriptions am I paying, and what's due next?
> Any unusual spending last month?
```

- [ ] **Step 3: Extend `docs/architecture.md`** — under "Layout", note the now-populated `analysis/` package:

```markdown
analysis/                # SP3 analytics (pure, deterministic — no numpy/pandas)
├── categorize.py    # rule engine + idempotent apply pass + suggestion helpers
├── cashflow.py      # inflow/outflow/net per period (transfers excluded)
├── recurring.py     # median-gap cadence detection + next-occurrence forecast
└── anomaly.py       # category-month z-score baseline
```

And add a short section:

```markdown
## Categorization & the canonical taxonomy (SP3)

The canonical category vocabulary *is* the set of YNAB category names. `apply_categorization` is idempotent: it derives YNAB rows' categories from their names, fills statement rows from ordered rules, and never clobbers manual assignments (`category_source='manual'`). Analytics group by `canonical_category` for cross-source views. Claude assists only the unmatched long tail at the skill layer — every runtime money path stays deterministic.
```

- [ ] **Step 4: Update `CHANGELOG.md`** — under `[Unreleased] / ### Added`:

```markdown
- SP3 analytics: hybrid categorization (deterministic ordered rule engine + Claude-assisted long-tail suggestions promoted into rules) into a canonical "mirror-YNAB" taxonomy; `cash_flow`, `detect_recurring` (with next-bill forecast), and `detect_anomalies`; 7 new MCP tools (incl. `list_payees`) plus `summarize_spending(group_by='canonical_category')`; a `categorize` CLI group; and two skills (`homefinance-categorize`, `homefinance-analyze`). Migration 0003 adds the `category_rules` table and `transactions.canonical_category` / `category_source`. No new third-party dependencies.
```

- [ ] **Step 5: Full verification**

```bash
~/.virtualenvs/homeFinance/bin/pytest --cov=homefinance --cov-report=term --cov-fail-under=80
~/.virtualenvs/homeFinance/bin/ruff check .
~/.virtualenvs/homeFinance/bin/ruff format --check .
~/.virtualenvs/homeFinance/bin/mypy
```
Expected: all clean, coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/quickstart.md docs/architecture.md CHANGELOG.md
git commit -m "docs: SP3 categorization + analytics in README/quickstart/architecture/changelog"
```

---

## Closing — what SP3 delivers

After Task 13: a deterministic analytics layer over the SP1+SP2 store — hybrid categorization into a canonical mirror-YNAB taxonomy, cash flow (transfers excluded), recurring/bill forecasting, and anomaly detection. 7 new MCP tools (19 total) + `summarize_spending(group_by='canonical_category')`, a `categorize` CLI group, and two new skills. One additive migration; no new dependencies; no LLM in any tested code path.

## Plan self-review

| Spec section | Implemented in |
|---|---|
| §3 C-11 (never overwrite YNAB categories) | Task 3 (manual/ynab precedence; rules only fill NULLs) |
| §3 C-12 (deterministic; LLM only long tail) | Tasks 5-7 deterministic; Claude only in Task 11 skill |
| §3 C-13 (idempotent, manual-respecting) | Task 3 (reset-then-derive; manual sticky) |
| §4.1 canonical mirror-YNAB layer | Task 3 (derive from category name) |
| §4.2 hybrid categorization | Tasks 2-4 (rules) + Task 11 (suggestion loop) |
| §4.3 deterministic analytics tools | Tasks 5, 6, 7 |
| §6 migration 0003 | Task 1 |
| §6.1 apply pass logic | Task 3 |
| §7.1 seven new MCP tools | Tasks 8 (summarize) + 9 (the 7) |
| §7.2 categorize CLI | Task 10 |
| §7.3 skills | Tasks 11, 12 |
| §8.1 cash-flow defs (transfers excluded) | Task 5 |
| §8.2 recurring algorithm | Task 6 |
| §8.3 anomaly method | Task 7 |
| §9 error model + 3-tier tests | Tasks 2-10 (validation + tiers) |

Types/signatures verified consistent across tasks: `apply_categorization(store, *, source_id=None) -> dict[str,int]`, `add_rule(...) -> int`, `cash_flow(...) -> list[dict]`, etc., are referenced identically by the MCP wrappers (Task 9) and CLI (Task 10). No placeholders remain.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-15-sp3-analysis.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review, fast iteration.

**2. Inline Execution** — batch tasks here with checkpoints.

Defaulting to subagent-driven (as with SP1/SP2) unless you say otherwise.

