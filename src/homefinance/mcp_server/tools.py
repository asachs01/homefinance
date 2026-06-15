"""MCP tool implementations as plain functions. The stdio server wraps these
with ``@mcp.tool()`` decorators in ``__main__.py``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from homefinance.db.store import Store
from homefinance.sources.base import AccountSource
from homefinance.sources.statement.ingest import (
    confirm_batch as _confirm_batch_lib,
)
from homefinance.sources.statement.ingest import (
    ingest_file as _ingest_file_lib,
)
from homefinance.sources.statement.ingest import (
    list_batches as _list_batches_lib,
)
from homefinance.sources.statement.ingest import (
    reject_batch as _reject_batch_lib,
)
from homefinance.sources.statement.parsers.base import StatementIngestError
from homefinance.sources.ynab.sync import SyncRunResult, run_sync

Mode = Literal["leaves", "tops"]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}  # noqa: SIM118 — sqlite3.Row needs .keys()


# ---------------------------------------------------------------------------
# Sources


def list_sources(store: Store) -> list[dict[str, Any]]:
    """List registered budgets + last-sync info."""
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_reconciliation "
        "FROM sources s LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Accounts


def list_accounts(
    store: Store, source_id: str | None = None, include_closed: bool = False
) -> list[dict[str, Any]]:
    where: list[str] = ["deleted = 0"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if not include_closed:
        where.append("closed = 0")
    sql = (
        "SELECT id, source_id, external_id, name, type, on_budget, closed, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of "
        "FROM accounts WHERE " + " AND ".join(where) + " ORDER BY name"
    )
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]


def get_account(store: Store, account_id: str) -> dict[str, Any]:
    row = store.execute(
        "SELECT id, source_id, external_id, name, type, on_budget, closed, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, "
        "last_synced_at "
        "FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"account {account_id!r} not found")
    result = _row_to_dict(row)
    recon = store.execute(
        "SELECT reconciliation FROM sync_runs WHERE source_id = ? ORDER BY id DESC LIMIT 1",
        (result["source_id"],),
    ).fetchone()
    result["reconciliation"] = recon["reconciliation"] if recon else None
    return result


# ---------------------------------------------------------------------------
# Categories


def list_categories(
    store: Store, source_id: str | None = None, include_hidden: bool = False
) -> list[dict[str, Any]]:
    where: list[str] = ["deleted = 0"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if not include_hidden:
        where.append("hidden = 0")
    sql = (
        "SELECT id, source_id, external_id, name, group_name "
        "FROM categories WHERE " + " AND ".join(where) + " ORDER BY group_name, name"
    )
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Transactions


def query_transactions(
    store: Store,
    source_id: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category_id: str | None = None,
    payee_contains: str | None = None,
    amount_min_minor: int | None = None,
    amount_max_minor: int | None = None,
    cleared: str | None = None,
    include_deleted: bool = False,
    include_pending: bool = False,
    mode: Mode = "leaves",
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List transactions. ``mode='leaves'`` (default) = non-split rows + split
    children (analysis view, correct category attribution).
    ``mode='tops'`` = non-split rows + split parents (user-facing view).
    Both views sum to the same total — see spec §6.3.

    ``include_pending=False`` (default) hides statement rows still awaiting
    review (status='pending_review'); opt in to see them.
    """
    where: list[str] = []
    params: list[Any] = []

    if mode == "leaves":
        where.append("is_split_parent = 0")
    elif mode == "tops":
        where.append("parent_id IS NULL")
    else:
        raise ValueError(f"invalid mode: {mode!r}")

    if not include_pending:
        where.append("status = 'confirmed'")
    if not include_deleted:
        where.append("deleted = 0")
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if account_id is not None:
        where.append("account_id = ?")
        params.append(account_id)
    if date_from is not None:
        where.append("date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("date <= ?")
        params.append(date_to)
    if category_id is not None:
        where.append("category_id = ?")
        params.append(category_id)
    if payee_contains is not None:
        where.append("payee LIKE ?")
        params.append(f"%{payee_contains}%")
    if amount_min_minor is not None:
        where.append("amount_minor >= ?")
        params.append(amount_min_minor)
    if amount_max_minor is not None:
        where.append("amount_minor <= ?")
        params.append(amount_max_minor)
    if cleared is not None:
        where.append("cleared = ?")
        params.append(cleared)

    sql = (
        "SELECT id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, memo, category_id, cleared, approved, flag_color, "
        "import_id, transfer_account_id, parent_id, is_split_parent, deleted, "
        "status, batch_id "
        "FROM transactions WHERE "
        + " AND ".join(where)
        + " ORDER BY date DESC, id LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Aggregations


GroupBy = Literal["category", "payee", "month", "account", "day_of_week"]


_GROUP_EXPR: dict[str, str] = {
    "category": "COALESCE(c.name, '(uncategorized)')",
    "payee": "COALESCE(t.payee, '(no payee)')",
    "month": "substr(t.date, 1, 7)",
    "account": "a.name",
    "day_of_week": "CAST(strftime('%w', t.date) AS INTEGER)",
}


def summarize_spending(
    store: Store,
    source_id: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    payee_contains: str | None = None,
    cleared: str | None = None,
    group_by: GroupBy = "category",
) -> list[dict[str, Any]]:
    """Aggregate spending. Always operates on the Leaves view (is_split_parent = 0,
    deleted = 0) so totals + category attribution are simultaneously correct.
    """
    expr = _GROUP_EXPR.get(group_by)
    if expr is None:
        raise ValueError(f"invalid group_by: {group_by!r}")

    where: list[str] = ["t.is_split_parent = 0", "t.deleted = 0", "t.status = 'confirmed'"]
    params: list[Any] = []

    if source_id is not None:
        where.append("t.source_id = ?")
        params.append(source_id)
    if account_id is not None:
        where.append("t.account_id = ?")
        params.append(account_id)
    if date_from is not None:
        where.append("t.date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("t.date <= ?")
        params.append(date_to)
    if payee_contains is not None:
        where.append("t.payee LIKE ?")
        params.append(f"%{payee_contains}%")
    if cleared is not None:
        where.append("t.cleared = ?")
        params.append(cleared)

    sql = (
        f"SELECT {expr} AS key, SUM(t.amount_minor) AS total_minor, "
        "COUNT(*) AS count "
        "FROM transactions t "
        "LEFT JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE " + " AND ".join(where) + f" GROUP BY {expr} ORDER BY total_minor"
    )
    return [
        {"key": r["key"], "total_minor": int(r["total_minor"]), "count": int(r["count"])}
        for r in store.execute(sql, params).fetchall()
    ]


# ---------------------------------------------------------------------------
# Sync status + sync runner


def get_sync_status(store: Store) -> list[dict[str, Any]]:
    """Per-source last-sync + drift summary."""
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_reconciliation, "
        "(SELECT drift_report FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_drift_report, "
        "(SELECT COUNT(*) FROM statement_batches "
        "  WHERE source_id = s.id AND review_status = 'pending') "
        "  AS pending_batch_count "
        "FROM sources s LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        drift_count = 0
        if r["last_drift_report"]:
            try:
                drift_count = len(json.loads(r["last_drift_report"]).get("accounts", []))
            except (json.JSONDecodeError, AttributeError, TypeError):
                drift_count = 0
        out.append(
            {
                "source_id": r["source_id"],
                "kind": r["kind"],
                "nickname": r["nickname"],
                "last_sync_at": r["last_sync_at"],
                "server_knowledge": r["server_knowledge"],
                "last_reconciliation": r["last_reconciliation"],
                "drift_account_count": drift_count,
                "pending_batch_count": int(r["pending_batch_count"] or 0),
            }
        )
    return out


def _result_to_dict(r: SyncRunResult) -> dict[str, Any]:
    return {
        "source_id": r.source_id,
        "status": r.status,
        "txns_inserted": r.txns_inserted,
        "txns_updated": r.txns_updated,
        "txns_deleted": r.txns_deleted,
        "accounts_touched": r.accounts_touched,
        "reconciliation": r.reconciliation,
        "drift_report": r.drift_report,
    }


def sync_ynab_all(store: Store, sources: list[AccountSource]) -> list[dict[str, Any]]:
    """Sync each provided AccountSource and return the result rows."""
    return [_result_to_dict(run_sync(s, store)) for s in sources]


def sync_ynab_one(store: Store, source: AccountSource) -> dict[str, Any]:
    return _result_to_dict(run_sync(source, store))


# ---------------------------------------------------------------------------
# Statement ingest


def ingest_statement(
    store: Store,
    *,
    path: str,
    account_nickname: str,
    config_dir: str,
    archive_dir: str,
    archive: bool = True,
) -> dict[str, Any]:
    """Parse + stage a statement file. Returns a BatchPreview dict.

    Does not prompt; the caller (usually Claude) is expected to inspect the
    preview, decide, and call ``confirm_batch`` or ``reject_batch``.
    """
    try:
        preview = _ingest_file_lib(
            store,
            path=Path(path),
            account_nickname=account_nickname,
            config_dir=Path(config_dir),
            archive_dir=Path(archive_dir),
            archive=archive,
        )
    except StatementIngestError as e:
        return {"error": e.code, "message": str(e)}
    return asdict(preview)


def list_batches(
    store: Store,
    *,
    source_id: str | None = None,
    review_status: str | None = "pending",
) -> list[dict[str, Any]]:
    return _list_batches_lib(store, source_id=source_id, review_status=review_status)


def confirm_batch(store: Store, *, batch_id: int) -> dict[str, Any]:
    return _confirm_batch_lib(store, batch_id)


def reject_batch(store: Store, *, batch_id: int) -> dict[str, Any]:
    return _reject_batch_lib(store, batch_id)
