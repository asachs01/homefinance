"""Shared upsert helpers used by every AccountSource adapter.

These were originally implemented inside ``sources/ynab/sync.py`` for SP1.
SP2 extracts them so the statement ingest path uses identical SQL discipline —
single atomic transaction, ``(source_id, external_id)`` UNIQUE upserts,
integer-money only. No behavior change vs the SP1 originals.
"""

from __future__ import annotations

from datetime import UTC, datetime

from homefinance.db.store import Store
from homefinance.sources.base import (
    RemoteAccount,
    RemoteCategory,
    RemotePayee,
    RemoteSubTxn,
    RemoteTransaction,
)
from homefinance.sources.ynab.ids import make_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def new_counters() -> dict[str, int]:
    """Pre-seeded counter dict for the upsert helpers below.

    ``upsert_transaction`` / ``upsert_account`` / ``insert_subtransaction`` all
    do ``counters[name] += 1`` (not ``counters.get(name, 0) + 1``), so callers
    must seed the four keys or get a ``KeyError``. Use this factory at every
    call site so adding a fifth counter is a one-place change.
    """
    return {"inserted": 0, "updated": 0, "deleted": 0, "accounts_touched": 0}


def upsert_account(
    store: Store, source_id: str, a: RemoteAccount, counters: dict[str, int]
) -> None:
    acct_id = make_id(source_id, a.external_id)
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, "
        "closed, deleted, currency, cleared_balance_minor, uncleared_balance_minor, "
        "balance_as_of, last_synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, type = excluded.type, on_budget = excluded.on_budget, "
        "closed = excluded.closed, deleted = excluded.deleted, "
        "currency = excluded.currency, "
        "cleared_balance_minor = excluded.cleared_balance_minor, "
        "uncleared_balance_minor = excluded.uncleared_balance_minor, "
        "balance_as_of = excluded.balance_as_of, "
        "last_synced_at = excluded.last_synced_at",
        (
            acct_id,
            source_id,
            a.external_id,
            a.name,
            a.type,
            int(a.on_budget),
            int(a.closed),
            int(a.deleted),
            a.currency,
            a.cleared_balance_minor,
            a.uncleared_balance_minor,
            a.balance_as_of,
            utcnow(),
        ),
    )
    counters["accounts_touched"] += 1


def upsert_category(store: Store, source_id: str, c: RemoteCategory) -> None:
    cat_id = make_id(source_id, c.external_id)
    store.execute(
        "INSERT INTO categories (id, source_id, external_id, name, group_name, "
        "hidden, deleted) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, group_name = excluded.group_name, "
        "hidden = excluded.hidden, deleted = excluded.deleted",
        (cat_id, source_id, c.external_id, c.name, c.group_name, int(c.hidden), int(c.deleted)),
    )


def upsert_payee(store: Store, source_id: str, p: RemotePayee) -> None:
    payee_id = make_id(source_id, p.external_id)
    transfer_acct_id = (
        make_id(source_id, p.transfer_account_external_id)
        if p.transfer_account_external_id
        else None
    )
    store.execute(
        "INSERT INTO payees (id, source_id, external_id, name, transfer_account_id, "
        "deleted) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, transfer_account_id = excluded.transfer_account_id, "
        "deleted = excluded.deleted",
        (payee_id, source_id, p.external_id, p.name, transfer_acct_id, int(p.deleted)),
    )


def upsert_transaction(
    store: Store,
    source_id: str,
    t: RemoteTransaction,
    counters: dict[str, int],
    *,
    status: str = "confirmed",
    batch_id: int | None = None,
) -> None:
    """Insert or update one transaction row.

    The SP2 ingest path passes ``status='pending_review'`` and a ``batch_id``
    so staged rows are excluded from default analytics until confirmed.
    The YNAB path leaves the defaults (status='confirmed', batch_id NULL).
    """
    txn_id = make_id(source_id, t.external_id)
    acct_id = make_id(source_id, t.account_external_id)
    category_id = make_id(source_id, t.category_external_id) if t.category_external_id else None
    payee_id = make_id(source_id, t.payee_external_id) if t.payee_external_id else None
    transfer_acct_id = (
        make_id(source_id, t.transfer_account_external_id)
        if t.transfer_account_external_id
        else None
    )
    is_split_parent = 1 if t.subtransactions else 0

    existed = (
        store.execute("SELECT 1 FROM transactions WHERE id = ?", (txn_id,)).fetchone() is not None
    )

    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "date = excluded.date, amount_minor = excluded.amount_minor, "
        "payee = excluded.payee, payee_id = excluded.payee_id, memo = excluded.memo, "
        "category_id = excluded.category_id, cleared = excluded.cleared, "
        "approved = excluded.approved, flag_color = excluded.flag_color, "
        "transfer_account_id = excluded.transfer_account_id, "
        "is_split_parent = excluded.is_split_parent, deleted = excluded.deleted, "
        "raw = excluded.raw, synced_at = excluded.synced_at, "
        "status = excluded.status, batch_id = excluded.batch_id",
        (
            txn_id,
            source_id,
            t.external_id,
            acct_id,
            t.date,
            t.amount_minor,
            t.currency,
            t.payee,
            payee_id,
            t.memo,
            category_id,
            t.cleared,
            int(t.approved),
            t.flag_color,
            t.import_id,
            transfer_acct_id,
            is_split_parent,
            int(t.deleted),
            None,
            utcnow(),
            status,
            batch_id,
        ),
    )

    if t.deleted:
        counters["deleted"] += 1
    elif existed:
        counters["updated"] += 1
    else:
        counters["inserted"] += 1

    if t.subtransactions:
        # Rewrite children atomically: delete then re-insert so the latest
        # split shape always reflects YNAB's truth.
        store.execute("DELETE FROM transactions WHERE parent_id = ?", (txn_id,))
        for i, sub in enumerate(t.subtransactions):
            insert_subtransaction(
                store,
                source_id,
                txn_id,
                acct_id,
                t,
                sub,
                i,
                status=status,
                batch_id=batch_id,
            )


def insert_subtransaction(
    store: Store,
    source_id: str,
    parent_id: str,
    acct_id: str,
    parent: RemoteTransaction,
    sub: RemoteSubTxn,
    index: int,
    *,
    status: str = "confirmed",
    batch_id: int | None = None,
) -> None:
    sub_external = f"{parent.external_id}:sub:{index}"
    sub_id = make_id(source_id, sub_external)
    category_id = make_id(source_id, sub.category_external_id) if sub.category_external_id else None
    payee_id = make_id(source_id, sub.payee_external_id) if sub.payee_external_id else None
    transfer_acct_id = (
        make_id(source_id, sub.transfer_account_external_id)
        if sub.transfer_account_external_id
        else None
    )
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?)",
        (
            sub_id,
            source_id,
            sub_external,
            acct_id,
            parent.date,
            sub.amount_minor,
            parent.currency,
            parent.payee,
            payee_id,
            sub.memo,
            category_id,
            parent.cleared,
            int(parent.approved),
            parent.flag_color,
            parent.import_id,
            transfer_acct_id,
            parent_id,
            utcnow(),
            status,
            batch_id,
        ),
    )
