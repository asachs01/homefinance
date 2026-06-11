"""``YNABAccountSource`` — implements ``AccountSource`` for YNAB.

Wraps a YNAB client (real or fake) plus the mapping functions. The protocol
contract is "validate before use; pull a delta given a cursor"; everything
else is the orchestrator's job.
"""

from __future__ import annotations

from typing import Literal, Protocol

from homefinance.sources.base import SyncDelta
from homefinance.sources.ynab.ids import source_id_for
from homefinance.sources.ynab.mapping import (
    map_account,
    map_categories,
    map_payee,
    map_transaction,
)
from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class _ClientLike(Protocol):
    """The subset of YNAB client methods the source needs."""

    def get_user(self) -> UserResponse: ...
    def get_budgets(self) -> BudgetsResponse: ...
    def get_accounts(self, budget_id: str, cursor: int | None = None) -> AccountsResponse: ...
    def get_categories(
        self, budget_id: str, cursor: int | None = None
    ) -> CategoriesResponse: ...
    def get_payees(self, budget_id: str, cursor: int | None = None) -> PayeesResponse: ...
    def get_transactions(
        self, budget_id: str, cursor: int | None = None
    ) -> TransactionsResponse: ...


class YNABAccountSource:
    """One configured YNAB budget surfaced as an ``AccountSource``."""

    kind: Literal["ynab"] = "ynab"

    def __init__(
        self,
        budget_id: str,
        client: _ClientLike,
        nickname: str | None = None,
        currency: str = "USD",
    ) -> None:
        self.budget_id = budget_id
        self.source_id = source_id_for(budget_id)
        self.nickname = nickname
        self._client = client
        self._currency = currency

    def validate(self) -> None:
        """Fail fast on bad token: ``get_user`` raises ``YNABAuthError`` on 401."""
        self._client.get_user()

    def pull(self, cursor: int | None) -> SyncDelta:
        accts = self._client.get_accounts(self.budget_id, cursor=cursor)
        cats = self._client.get_categories(self.budget_id, cursor=cursor)
        payees = self._client.get_payees(self.budget_id, cursor=cursor)
        txns = self._client.get_transactions(self.budget_id, cursor=cursor)

        # The new cursor is the highest server_knowledge advertised across the
        # four endpoints — each tracks its own watermark, but a single integer
        # is enough to ask "give me everything that changed since".
        knowledges = [
            v
            for v in (
                accts.data.server_knowledge,
                cats.data.server_knowledge,
                payees.data.server_knowledge,
                txns.data.server_knowledge,
            )
            if v is not None
        ]
        new_cursor: int | None = max(knowledges) if knowledges else None

        return SyncDelta(
            accounts=tuple(
                map_account(a, currency=self._currency) for a in accts.data.accounts
            ),
            categories=tuple(map_categories(cats)),
            payees=tuple(map_payee(p) for p in payees.data.payees),
            transactions=tuple(
                map_transaction(t, currency=self._currency) for t in txns.data.transactions
            ),
            new_cursor=new_cursor,
        )
