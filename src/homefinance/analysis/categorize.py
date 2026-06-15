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
