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
        (
            priority,
            match_field,
            pattern,
            int(is_regex),
            canonical_category,
            note,
            _utcnow(),
        ),
    )
    return int(cur.lastrowid)  # type: ignore[arg-type]


def list_rules(store: Store) -> list[dict[str, Any]]:
    """All rules ordered by (priority ASC, id ASC) — i.e. evaluation order."""
    rows = store.execute(
        "SELECT id, priority, match_field, pattern, is_regex, canonical_category, "
        "note, created_at FROM category_rules ORDER BY priority ASC, id ASC"
    ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]  # noqa: SIM118


def _compile_rules(
    rules: list[dict[str, Any]],
) -> list[tuple[str, str, re.Pattern[str] | None, str]]:
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
