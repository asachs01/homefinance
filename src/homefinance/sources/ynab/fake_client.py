"""A fake YNAB client backed by JSON fixtures.

Conforms to the same surface as `YNABClient` (only the methods used by sync),
so the sync engine can be exercised end-to-end without ever hitting YNAB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class FakeYNABClient:
    """Loads `*.json` fixtures from a directory and returns parsed responses.

    The `cursor` argument selects between two transaction fixture files:
    `transactions.json` for None (full pull) and `transactions_delta.json`
    when a cursor is provided.
    """

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = Path(fixtures_dir)

    def _load(self, name: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self._dir / name).read_text())
        return data

    # Same signature subset as YNABClient.

    def get_user(self) -> UserResponse:
        return UserResponse.model_validate(self._load("user.json"))

    def get_budgets(self) -> BudgetsResponse:
        return BudgetsResponse.model_validate(self._load("budgets.json"))

    def get_accounts(self, budget_id: str, cursor: int | None = None) -> AccountsResponse:
        return AccountsResponse.model_validate(self._load("accounts.json"))

    def get_categories(self, budget_id: str, cursor: int | None = None) -> CategoriesResponse:
        return CategoriesResponse.model_validate(self._load("categories.json"))

    def get_payees(self, budget_id: str, cursor: int | None = None) -> PayeesResponse:
        return PayeesResponse.model_validate(self._load("payees.json"))

    def get_transactions(self, budget_id: str, cursor: int | None = None) -> TransactionsResponse:
        name = "transactions_delta.json" if cursor is not None else "transactions.json"
        return TransactionsResponse.model_validate(self._load(name))
