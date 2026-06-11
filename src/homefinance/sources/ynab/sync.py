"""Sync orchestrator.

Operates on any ``AccountSource`` (per spec §4.2). All persistence happens
inside a single SQLite transaction so the store is never left in a
half-applied state: either the cursor advances and rows land, or nothing
moves and the next run retries the same cursor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homefinance.db.store import Store
from homefinance.sources.base import (
    AccountSource,
    RemoteAccount,
    RemoteCategory,
    RemotePayee,
    RemoteSubTxn,
    RemoteTransaction,
)
from homefinance.sources.ynab.ids import make_id


@dataclass(frozen=True, slots=True)
class SyncRunResult:
    source_id: str
    status: str  # "success" | "partial" | "failed"
    txns_inserted: int
    txns_updated: int
    txns_deleted: int
    accounts_touched: int
    reconciliation: str  # "ok" | "drift" | "n/a"
    drift_report: str | None  # JSON string when reconciliation='drift'


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def run_sync(source: AccountSource, store: Store) -> SyncRunResult:
    started_at = _utcnow()
    source.validate()

    row = store.execute(
        "SELECT server_knowledge FROM sync_state WHERE source_id = ?", (source.source_id,)
    ).fetchone()
    cursor: int | None = row["server_knowledge"] if row else None

    delta = source.pull(cursor)

    counters: dict[str, int] = {
        "inserted": 0,
        "updated": 0,
        "deleted": 0,
        "accounts_touched": 0,
    }

    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET nickname = excluded.nickname",
            (source.source_id, source.kind, source.nickname, None, _utcnow()),
        )

        for a in delta.accounts:
            _upsert_account(store, source.source_id, a, counters)

        for c in delta.categories:
            _upsert_category(store, source.source_id, c)

        for p in delta.payees:
            _upsert_payee(store, source.source_id, p)

        for t in delta.transactions:
            _upsert_transaction(store, source.source_id, t, counters)

        store.execute(
            "INSERT INTO sync_state (source_id, last_sync_at, server_knowledge, "
            "last_error, last_error_at) VALUES (?, ?, ?, NULL, NULL) "
            "ON CONFLICT (source_id) DO UPDATE SET "
            "last_sync_at = excluded.last_sync_at, "
            "server_knowledge = excluded.server_knowledge, "
            "last_error = NULL, last_error_at = NULL",
            (source.source_id, _utcnow(), delta.new_cursor),
        )

        recon_status, drift_report = _reconcile(store, source.source_id, delta.accounts)

        store.execute(
            "INSERT INTO sync_runs (source_id, started_at, finished_at, status, "
            "txns_inserted, txns_updated, txns_deleted, accounts_touched, "
            "reconciliation, drift_report) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source.source_id,
                started_at,
                _utcnow(),
                "success",
                counters["inserted"],
                counters["updated"],
                counters["deleted"],
                counters["accounts_touched"],
                recon_status,
                drift_report,
            ),
        )

    return SyncRunResult(
        source_id=source.source_id,
        status="success",
        txns_inserted=counters["inserted"],
        txns_updated=counters["updated"],
        txns_deleted=counters["deleted"],
        accounts_touched=counters["accounts_touched"],
        reconciliation=recon_status,
        drift_report=drift_report,
    )


# ---------------------------------------------------------------------------
# Upserts


def _upsert_account(
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
            _utcnow(),
        ),
    )
    counters["accounts_touched"] += 1


def _upsert_category(store: Store, source_id: str, c: RemoteCategory) -> None:
    cat_id = make_id(source_id, c.external_id)
    store.execute(
        "INSERT INTO categories (id, source_id, external_id, name, group_name, "
        "hidden, deleted) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, group_name = excluded.group_name, "
        "hidden = excluded.hidden, deleted = excluded.deleted",
        (cat_id, source_id, c.external_id, c.name, c.group_name, int(c.hidden), int(c.deleted)),
    )


def _upsert_payee(store: Store, source_id: str, p: RemotePayee) -> None:
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


def _upsert_transaction(
    store: Store, source_id: str, t: RemoteTransaction, counters: dict[str, int]
) -> None:
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
        "is_split_parent, deleted, raw, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "date = excluded.date, amount_minor = excluded.amount_minor, "
        "payee = excluded.payee, payee_id = excluded.payee_id, memo = excluded.memo, "
        "category_id = excluded.category_id, cleared = excluded.cleared, "
        "approved = excluded.approved, flag_color = excluded.flag_color, "
        "transfer_account_id = excluded.transfer_account_id, "
        "is_split_parent = excluded.is_split_parent, deleted = excluded.deleted, "
        "raw = excluded.raw, synced_at = excluded.synced_at",
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
            _utcnow(),
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
            _insert_subtransaction(store, source_id, txn_id, acct_id, t, sub, i)


def _insert_subtransaction(
    store: Store,
    source_id: str,
    parent_id: str,
    acct_id: str,
    parent: RemoteTransaction,
    sub: RemoteSubTxn,
    index: int,
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
        "is_split_parent, deleted, raw, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?)",
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
            _utcnow(),
        ),
    )


# ---------------------------------------------------------------------------
# Reconciliation


def _reconcile(
    store: Store, source_id: str, remote_accounts: tuple[RemoteAccount, ...]
) -> tuple[str, str | None]:
    """Compare per-account computed cleared balance to YNAB's reported value.

    Sums the "Tops" view (parent_id IS NULL AND deleted = 0). Drift never
    fails the sync — see spec §9.3 — it just produces a structured report.
    """
    if not remote_accounts:
        return "n/a", None

    deltas: list[dict[str, Any]] = []
    for a in remote_accounts:
        if a.cleared_balance_minor is None:
            continue
        acct_id = make_id(source_id, a.external_id)
        row = store.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total "
            "FROM transactions "
            "WHERE account_id = ? AND parent_id IS NULL AND deleted = 0",
            (acct_id,),
        ).fetchone()
        computed = int(row["total"])
        reported = int(a.cleared_balance_minor)
        if computed != reported:
            deltas.append(
                {
                    "account_id": acct_id,
                    "computed_minor": computed,
                    "reported_minor": reported,
                    "delta_minor": computed - reported,
                }
            )

    if deltas:
        return "drift", json.dumps({"accounts": deltas})
    return "ok", None
