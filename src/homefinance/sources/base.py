"""The source-agnostic seam.

Every data source (YNAB now, statements later) implements `AccountSource`
and emits the canonical `RemoteX` dataclasses below. The sync orchestrator
consumes only this protocol, so adding a new source is "implement the
protocol" rather than "rewire the store."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

SourceKind = Literal["ynab", "statement"]


@dataclass(frozen=True, slots=True)
class RemoteAccount:
    external_id: str
    name: str
    type: str  # canonical: checking/savings/credit_card/...
    on_budget: bool
    closed: bool
    deleted: bool
    currency: str
    cleared_balance_minor: int | None
    uncleared_balance_minor: int | None
    balance_as_of: str | None


@dataclass(frozen=True, slots=True)
class RemoteCategory:
    external_id: str
    name: str
    group_name: str | None
    hidden: bool
    deleted: bool


@dataclass(frozen=True, slots=True)
class RemotePayee:
    external_id: str
    name: str
    transfer_account_external_id: str | None
    deleted: bool


@dataclass(frozen=True, slots=True)
class RemoteSubTxn:
    """A child of a split transaction (no `id` needed; assigned at mapping time)."""

    amount_minor: int
    memo: str | None
    category_external_id: str | None
    payee_external_id: str | None
    transfer_account_external_id: str | None


@dataclass(frozen=True, slots=True)
class RemoteTransaction:
    external_id: str
    account_external_id: str
    date: str  # YYYY-MM-DD
    amount_minor: int  # signed; negative = outflow
    currency: str
    payee: str | None  # display name
    payee_external_id: str | None
    memo: str | None
    category_external_id: str | None
    cleared: str | None  # cleared | uncleared | reconciled
    approved: bool
    flag_color: str | None
    import_id: str | None
    transfer_account_external_id: str | None
    deleted: bool
    subtransactions: tuple[RemoteSubTxn, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SyncDelta:
    """Everything a source emitted for one delta pull."""

    accounts: tuple[RemoteAccount, ...]
    categories: tuple[RemoteCategory, ...]
    payees: tuple[RemotePayee, ...]
    transactions: tuple[RemoteTransaction, ...]
    new_cursor: int | None  # to persist in sync_state.server_knowledge


@runtime_checkable
class AccountSource(Protocol):
    """A pullable data source. Implementations are read-only by construction."""

    source_id: str  # e.g., "ynab:<budget_id>"
    kind: SourceKind
    nickname: str | None

    def validate(self) -> None:
        """Raise (with a user-friendly message) on bad auth or config."""
        ...

    def pull(self, cursor: int | None) -> SyncDelta:
        """Pull a delta from the source. Pass `cursor=None` for a full snapshot."""
        ...
