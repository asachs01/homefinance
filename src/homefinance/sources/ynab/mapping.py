"""YNAB → canonical mapping. Pure functions; no I/O.

This is the only place in the codebase that converts YNAB's wire format
(milliunits) to our canonical minor units (cents). Floats never enter the store.
"""

from __future__ import annotations

from homefinance.sources.base import (
    RemoteAccount,
    RemoteCategory,
    RemotePayee,
    RemoteSubTxn,
    RemoteTransaction,
)
from homefinance.sources.ynab.models import (
    CategoriesResponse,
    YNABAccount,
    YNABPayee,
    YNABTransaction,
)


def to_minor_units(milliunits: int) -> int:
    """Convert signed YNAB milliunits to signed minor units (cents).

    Raises ``ValueError`` if the input is not a multiple of 10 — real YNAB
    transactions are always whole cents, so sub-cent values indicate either
    a bug upstream or a corner case we want to surface loudly rather than
    silently round.
    """
    if milliunits % 10 != 0:
        raise ValueError(f"non-cent milliunit value: {milliunits}")
    return milliunits // 10


_ACCOUNT_TYPE_MAP: dict[str, str] = {
    "checking": "checking",
    "savings": "savings",
    "cash": "cash",
    "creditCard": "credit_card",
    "lineOfCredit": "loan",
    "mortgage": "loan",
    "autoLoan": "loan",
    "studentLoan": "loan",
    "personalLoan": "loan",
    "medicalDebt": "loan",
    "otherDebt": "loan",
    "otherAsset": "other",
    "otherLiability": "loan",
}


def _normalize_account_type(ynab_type: str) -> str:
    return _ACCOUNT_TYPE_MAP.get(ynab_type, "other")


def map_account(ya: YNABAccount, currency: str = "USD") -> RemoteAccount:
    """YNAB account → canonical. Currency defaults to USD; SP1 does not yet
    fetch budget-level currency settings (see open question OQ in spec §11)."""
    return RemoteAccount(
        external_id=ya.id,
        name=ya.name,
        type=_normalize_account_type(ya.type),
        on_budget=ya.on_budget,
        closed=ya.closed,
        deleted=ya.deleted,
        currency=currency,
        cleared_balance_minor=to_minor_units(ya.cleared_balance),
        uncleared_balance_minor=to_minor_units(ya.uncleared_balance),
        balance_as_of=ya.last_reconciled_at,
    )


def map_categories(resp: CategoriesResponse) -> list[RemoteCategory]:
    """Flatten YNAB's category groups into a flat list of canonical categories.
    A category inherits ``hidden`` or ``deleted`` from its group."""
    out: list[RemoteCategory] = []
    for grp in resp.data.category_groups:
        for cat in grp.categories:
            out.append(
                RemoteCategory(
                    external_id=cat.id,
                    name=cat.name,
                    group_name=grp.name,
                    hidden=bool(cat.hidden or grp.hidden),
                    deleted=bool(cat.deleted or grp.deleted),
                )
            )
    return out


def map_payee(yp: YNABPayee) -> RemotePayee:
    return RemotePayee(
        external_id=yp.id,
        name=yp.name,
        transfer_account_external_id=yp.transfer_account_id,
        deleted=yp.deleted,
    )


def map_transaction(yt: YNABTransaction, currency: str = "USD") -> RemoteTransaction:
    """YNAB transaction → canonical, with non-deleted subtransactions preserved.

    The ``is_split_parent`` flag on the persisted row is set by the sync
    orchestrator (``len(subtransactions) > 0``) — this function just carries
    the data through.
    """
    subs = tuple(
        RemoteSubTxn(
            amount_minor=to_minor_units(s.amount),
            memo=s.memo,
            category_external_id=s.category_id,
            payee_external_id=s.payee_id,
            transfer_account_external_id=s.transfer_account_id,
        )
        for s in yt.subtransactions
        if not s.deleted
    )
    return RemoteTransaction(
        external_id=yt.id,
        account_external_id=yt.account_id,
        date=yt.date,
        amount_minor=to_minor_units(yt.amount),
        currency=currency,
        payee=yt.payee_name,
        payee_external_id=yt.payee_id,
        memo=yt.memo,
        category_external_id=yt.category_id,
        cleared=yt.cleared,
        approved=yt.approved,
        flag_color=yt.flag_color,
        import_id=yt.import_id,
        transfer_account_external_id=yt.transfer_account_id,
        deleted=yt.deleted,
        subtransactions=subs,
    )
