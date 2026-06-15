"""Sync orchestrator.

Operates on any ``AccountSource`` (per spec §4.2). All persistence happens
inside a single SQLite transaction so the store is never left in a
half-applied state: either the cursor advances and rows land, or nothing
moves and the next run retries the same cursor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from homefinance.db import _upsert
from homefinance.db.store import Store
from homefinance.sources.base import AccountSource, RemoteAccount
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


def run_sync(source: AccountSource, store: Store) -> SyncRunResult:
    started_at = _upsert.utcnow()
    source.validate()

    row = store.execute(
        "SELECT server_knowledge FROM sync_state WHERE source_id = ?", (source.source_id,)
    ).fetchone()
    cursor: int | None = row["server_knowledge"] if row else None

    delta = source.pull(cursor)

    counters = _upsert.new_counters()

    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET nickname = excluded.nickname",
            (source.source_id, source.kind, source.nickname, None, _upsert.utcnow()),
        )

        for a in delta.accounts:
            _upsert.upsert_account(store, source.source_id, a, counters)

        for c in delta.categories:
            _upsert.upsert_category(store, source.source_id, c)

        for p in delta.payees:
            _upsert.upsert_payee(store, source.source_id, p)

        for t in delta.transactions:
            _upsert.upsert_transaction(store, source.source_id, t, counters)

        store.execute(
            "INSERT INTO sync_state (source_id, last_sync_at, server_knowledge, "
            "last_error, last_error_at) VALUES (?, ?, ?, NULL, NULL) "
            "ON CONFLICT (source_id) DO UPDATE SET "
            "last_sync_at = excluded.last_sync_at, "
            "server_knowledge = excluded.server_knowledge, "
            "last_error = NULL, last_error_at = NULL",
            (source.source_id, _upsert.utcnow(), delta.new_cursor),
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
                _upsert.utcnow(),
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
