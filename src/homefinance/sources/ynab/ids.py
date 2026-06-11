"""Deterministic ID builders. Format: ``ynab:<budget_id>:<external_id>``.

Stable across re-syncs and grep-friendly for debugging.
"""

from __future__ import annotations


def source_id_for(budget_id: str) -> str:
    return f"ynab:{budget_id}"


def make_id(source_id: str, external_id: str) -> str:
    return f"{source_id}:{external_id}"
