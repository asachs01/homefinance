"""Pydantic models for the YNAB API subset we consume.

Permissive (`extra='ignore'`) so YNAB can add fields without breaking us.
Amounts here are still in YNAB's wire format (milliunits, integers).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Permissive(BaseModel):
    model_config = ConfigDict(extra="ignore")


class YNABUser(_Permissive):
    id: str


class YNABBudgetSummary(_Permissive):
    id: str
    name: str


class YNABAccount(_Permissive):
    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    deleted: bool
    balance: int                              # milliunits
    cleared_balance: int                      # milliunits
    uncleared_balance: int                    # milliunits
    last_reconciled_at: str | None = None


class YNABCategory(_Permissive):
    id: str
    category_group_id: str | None = None
    category_group_name: str | None = None
    name: str
    hidden: bool
    deleted: bool


class YNABPayee(_Permissive):
    id: str
    name: str
    transfer_account_id: str | None = None
    deleted: bool


class YNABSubTransaction(_Permissive):
    id: str
    amount: int                               # milliunits
    memo: str | None = None
    payee_id: str | None = None
    category_id: str | None = None
    transfer_account_id: str | None = None
    deleted: bool


class YNABTransaction(_Permissive):
    id: str
    date: str                                 # YYYY-MM-DD
    amount: int                               # milliunits, signed
    memo: str | None = None
    cleared: str | None = None
    approved: bool
    flag_color: str | None = None
    account_id: str
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    transfer_account_id: str | None = None
    import_id: str | None = None
    deleted: bool
    subtransactions: list[YNABSubTransaction] = Field(default_factory=list)


# Top-level response wrappers. YNAB wraps every endpoint in {"data": {...}}.


class _Data(_Permissive):
    server_knowledge: int | None = None


class UserResponse(_Permissive):
    class _D(_Data):
        user: YNABUser

    data: _D


class BudgetsResponse(_Permissive):
    class _D(_Data):
        budgets: list[YNABBudgetSummary]

    data: _D


class AccountsResponse(_Permissive):
    class _D(_Data):
        accounts: list[YNABAccount]

    data: _D


class CategoryGroupWithCategories(_Permissive):
    id: str
    name: str
    hidden: bool
    deleted: bool
    categories: list[YNABCategory] = Field(default_factory=list)


class CategoriesResponse(_Permissive):
    class _D(_Data):
        category_groups: list[CategoryGroupWithCategories]

    data: _D


class PayeesResponse(_Permissive):
    class _D(_Data):
        payees: list[YNABPayee]

    data: _D


class TransactionsResponse(_Permissive):
    class _D(_Data):
        transactions: list[YNABTransaction]

    data: _D
