"""Record sanitized YNAB API responses for use as test fixtures.

Usage:
    HOMEFINANCE_YNAB_TOKEN=... python scripts/record_fixtures.py \
        --budget-id <budget> --out tests/fixtures/ynab/recorded

What it does:
    Calls every endpoint the sync engine uses and writes the responses to
    JSON files. *Sanitizes* identifying information - names, memos, IDs
    become deterministic placeholders - while keeping amounts and structure
    so the fixtures realistically exercise mapping + sync.

Always review the output before committing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from homefinance.sources.ynab.client import YNABClient


def _renumber(
    seq: list[dict[str, Any]], id_key: str, prefix: str, mapping: dict[str, str]
) -> None:
    for i, item in enumerate(seq, start=1):
        real_id = item[id_key]
        if real_id not in mapping:
            mapping[real_id] = f"{prefix}-{i}"
        item[id_key] = mapping[real_id]


def _scrub_strings(obj: Any, mapping: dict[str, str], string_fields: set[str]) -> Any:
    """Replace identifying strings; pass through IDs already in the mapping."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, str) and v in mapping:
                out[k] = mapping[v]
            elif isinstance(v, str) and k in string_fields and v:
                out[k] = f"[scrubbed {k}]"
            else:
                out[k] = _scrub_strings(v, mapping, string_fields)
        return out
    if isinstance(obj, list):
        return [_scrub_strings(v, mapping, string_fields) for v in obj]
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    token = os.environ.get("HOMEFINANCE_YNAB_TOKEN")
    if not token:
        print("error: HOMEFINANCE_YNAB_TOKEN is required", file=sys.stderr)
        return 2

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    client = YNABClient(token=token)

    user = client.get_user().model_dump()
    budgets = client.get_budgets().model_dump()
    accounts = client.get_accounts(args.budget_id).model_dump()
    categories = client.get_categories(args.budget_id).model_dump()
    payees = client.get_payees(args.budget_id).model_dump()
    transactions = client.get_transactions(args.budget_id).model_dump()

    # Build an ID remapping across all entities and apply scrubbing.
    id_mapping: dict[str, str] = {}
    _renumber(accounts["data"]["accounts"], "id", "acct", id_mapping)
    for grp in categories["data"]["category_groups"]:
        _renumber([grp], "id", "grp", id_mapping)
        _renumber(grp["categories"], "id", "cat", id_mapping)
    _renumber(payees["data"]["payees"], "id", "payee", id_mapping)
    _renumber(transactions["data"]["transactions"], "id", "txn", id_mapping)
    for txn in transactions["data"]["transactions"]:
        _renumber(txn.get("subtransactions", []), "id", "sub", id_mapping)

    string_fields = {"name", "memo", "payee_name", "category_group_name"}

    sanitized = {
        "user.json": _scrub_strings(user, id_mapping, string_fields),
        "budgets.json": _scrub_strings(budgets, id_mapping, string_fields),
        "accounts.json": _scrub_strings(accounts, id_mapping, string_fields),
        "categories.json": _scrub_strings(categories, id_mapping, string_fields),
        "payees.json": _scrub_strings(payees, id_mapping, string_fields),
        "transactions.json": _scrub_strings(transactions, id_mapping, string_fields),
    }

    for name, payload in sanitized.items():
        (out / name).write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"wrote {out / name}")

    print("\nREVIEW the output before committing - automated scrubbing is not perfect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
