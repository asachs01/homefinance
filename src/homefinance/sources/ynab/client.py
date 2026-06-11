"""Read-only YNAB API client.

Structural posture: this class exposes only GET methods. POST/PUT/PATCH/DELETE
are not on the class at all, so accidental writes are physically impossible.

Retries: 429, 5xx, and transport-level errors are retried with jittered
exponential backoff up to 3 attempts via `tenacity`.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class YNABClientError(Exception):
    """Base class for YNAB client errors."""


class YNABAuthError(YNABClientError):
    """Raised on 401/403."""


class YNABRetryableError(YNABClientError):
    """Internal — raised to trigger tenacity backoff. Not surfaced to callers."""


_RETRY: dict[str, Any] = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential_jitter(initial=0.5, max=8.0),
    "retry": retry_if_exception_type((YNABRetryableError, httpx.TransportError)),
    "reraise": True,
}


class YNABClient:
    """Thin, read-only YNAB API client."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.ynab.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> YNABClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # public read methods

    def get_user(self) -> UserResponse:
        return UserResponse.model_validate(self._get("/user"))

    def get_budgets(self) -> BudgetsResponse:
        return BudgetsResponse.model_validate(self._get("/budgets"))

    def get_accounts(self, budget_id: str, cursor: int | None = None) -> AccountsResponse:
        return AccountsResponse.model_validate(
            self._get(f"/budgets/{budget_id}/accounts", cursor=cursor)
        )

    def get_categories(self, budget_id: str, cursor: int | None = None) -> CategoriesResponse:
        return CategoriesResponse.model_validate(
            self._get(f"/budgets/{budget_id}/categories", cursor=cursor)
        )

    def get_payees(self, budget_id: str, cursor: int | None = None) -> PayeesResponse:
        return PayeesResponse.model_validate(
            self._get(f"/budgets/{budget_id}/payees", cursor=cursor)
        )

    def get_transactions(
        self, budget_id: str, cursor: int | None = None
    ) -> TransactionsResponse:
        return TransactionsResponse.model_validate(
            self._get(f"/budgets/{budget_id}/transactions", cursor=cursor)
        )

    # ------------------------------------------------------------------
    # internals

    @retry(**_RETRY)  # type: ignore[untyped-decorator]
    def _get(self, path: str, cursor: int | None = None) -> dict[str, Any]:
        params: dict[str, int] = {}
        if cursor is not None:
            params["last_knowledge_of_server"] = cursor
        resp = self._http.get(path, params=params)
        if resp.status_code in (401, 403):
            raise YNABAuthError(
                f"YNAB rejected the request ({resp.status_code}). "
                "Check $HOMEFINANCE_YNAB_TOKEN or ~/.homefinance/config.toml."
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise YNABRetryableError(f"YNAB returned {resp.status_code}")
        if resp.status_code >= 400:
            raise YNABClientError(f"YNAB returned {resp.status_code}: {resp.text[:200]}")
        data: dict[str, Any] = resp.json()
        return data
