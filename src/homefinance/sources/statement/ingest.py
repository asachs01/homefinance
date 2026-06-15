"""Statement ingest orchestrator and its helpers.

This module is built up across Tasks 10-12 of the SP2 plan:
- Task 10: small helpers + register/resolve account + BatchPreview shape
- Task 11: ``ingest_file()`` — parse + reconcile + atomic stage
- Task 12: ``confirm_batch()``, ``reject_batch()``, ``list_batches()``
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from homefinance.db import _upsert
from homefinance.db.store import Store
from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.archive import archive_file
from homefinance.sources.statement.parsers import find_parser
from homefinance.sources.statement.parsers.base import (
    AccountNotConfigured,
    FileAlreadyIngested,
    ResolvedAccount,
)
from homefinance.sources.statement.templates import load_template

# ---------------------------------------------------------------------------
# Errors specific to this layer


class AccountAlreadyRegistered(Exception):
    code = "account_already_registered"


# ---------------------------------------------------------------------------
# BatchPreview — what ingest_file() returns to its caller


@dataclass(frozen=True, slots=True)
class TxnPreview:
    date: str
    amount_minor: int
    payee: str | None
    memo: str | None


@dataclass(frozen=True, slots=True)
class BatchPreview:
    batch_id: int
    source_id: str
    txn_count: int
    reconciliation_status: str  # 'ok' | 'drift' | 'n/a'
    drift_minor: int | None
    statement_period_start: str | None
    statement_period_end: str | None
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    file_path_archive: str | None
    first_transactions: tuple[TxnPreview, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def compute_file_hash(path: Path) -> str:
    """SHA-256 of the file content, hex-encoded."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def row_external_id(
    account_id: str,
    date: str,
    amount_minor: int,
    payee: str | None,
    memo: str | None,
) -> str:
    """Synthetic 16-hex-char external_id for a parsed statement row."""
    payload = f"{account_id}|{date}|{amount_minor}|{payee or ''}|{memo or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def reconcile(
    *, opening: int | None, closing: int | None, txn_total: int
) -> tuple[str, int | None]:
    """Return (status, drift) where status is one of {'ok','drift','n/a'} and
    drift is None when status is 'ok' or 'n/a'."""
    if opening is None or closing is None:
        return "n/a", None
    expected = closing - opening
    drift = txn_total - expected
    if drift == 0:
        return "ok", None
    return "drift", drift


# ---------------------------------------------------------------------------
# Account registration


_VALID_TYPES = {
    "checking",
    "savings",
    "credit_card",
    "investment",
    "loan",
    "cash",
    "other",
}


def register_account(
    store: Store,
    *,
    nickname: str,
    type: str,
    currency: str = "USD",
    display_name: str | None = None,
) -> ResolvedAccount:
    """Create a new statement-fed source + canonical account in one atomic txn.

    Raises ``AccountAlreadyRegistered`` if a source with this nickname exists.
    """
    if type not in _VALID_TYPES:
        raise ValueError(f"invalid type {type!r}; one of {sorted(_VALID_TYPES)}")
    source_id = f"statement:{nickname}"
    account_id = f"{source_id}:account"
    name = display_name or nickname

    existing = store.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone()
    if existing:
        raise AccountAlreadyRegistered(f"source {source_id!r} already exists")

    now = _utcnow()
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            (source_id, "statement", name, None, now),
        )
        store.execute(
            "INSERT INTO accounts (id, source_id, external_id, name, type, "
            "on_budget, closed, deleted, currency, cleared_balance_minor, "
            "uncleared_balance_minor, balance_as_of, last_synced_at) "
            "VALUES (?, ?, ?, ?, ?, 1, 0, 0, ?, NULL, NULL, NULL, NULL)",
            (account_id, source_id, "account", name, type, currency),
        )

    return ResolvedAccount(
        source_id=source_id,
        account_id=account_id,
        nickname=nickname,
        type=type,
        currency=currency,
    )


def resolve_account(store: Store, nickname: str) -> ResolvedAccount:
    """Look up a previously-registered statement-fed account by nickname."""
    source_id = f"statement:{nickname}"
    row = store.execute(
        "SELECT a.id AS account_id, a.type, a.currency "
        "FROM accounts a WHERE a.source_id = ? AND a.external_id = 'account'",
        (source_id,),
    ).fetchone()
    if not row:
        raise AccountNotConfigured(
            f"no account {nickname!r} configured. Run "
            f"`homefinance accounts add --nickname {nickname} --type checking` first."
        )
    return ResolvedAccount(
        source_id=source_id,
        account_id=row["account_id"],
        nickname=nickname,
        type=row["type"],
        currency=row["currency"],
    )


# ---------------------------------------------------------------------------
# The orchestrator


def ingest_file(
    store: Store,
    *,
    path: Path,
    account_nickname: str,
    config_dir: Path,
    archive_dir: Path,
    archive: bool = True,
    allow_reingest: bool = False,
    preview_sample_size: int = 5,
) -> BatchPreview:
    """Parse + reconcile + atomically stage one statement file.

    Pipeline: resolve account → hash → file-level dedup → find parser → load
    template → parse → row-level external IDs → reconcile → archive →
    ATOMIC: insert statement_batches + insert transactions (status='pending_review').
    """
    path = Path(path)
    account = resolve_account(store, account_nickname)
    file_hash = compute_file_hash(path)

    # File-level dedup — fetch prior batch (if any) and act on it.
    prior = store.execute(
        "SELECT id, review_status FROM statement_batches WHERE file_hash = ? AND source_id = ?",
        (file_hash, account.source_id),
    ).fetchone()
    if prior and not allow_reingest and prior["review_status"] in ("pending", "confirmed"):
        raise FileAlreadyIngested(
            f"already ingested as batch #{prior['id']} "
            f"(status: {prior['review_status']}). Use --reingest to re-process."
        )
    if prior and allow_reingest:
        # UNIQUE(file_hash, source_id) would block re-inserting; drop the row.
        store.execute("DELETE FROM statement_batches WHERE id = ?", (prior["id"],))

    parser_cls = find_parser(path)
    template = load_template(account.source_id, config_dir=config_dir)
    parsed = parser_cls.parse(path, account, template)

    # Build stamped transactions in one pass: assign collision-suffixed
    # external IDs and accumulate the signed total used for reconciliation.
    seen: Counter[str] = Counter()
    stamped: list[RemoteTransaction] = []
    txn_total = 0
    for txn in parsed.transactions:
        base = row_external_id(account.account_id, txn.date, txn.amount_minor, txn.payee, txn.memo)
        n = seen[base]
        external_id = base if n == 0 else f"{base}:{n}"
        seen[base] += 1
        stamped.append(replace(txn, external_id=external_id, account_external_id="account"))
        txn_total += txn.amount_minor

    recon_status, drift_minor = reconcile(
        opening=parsed.opening_balance_minor,
        closing=parsed.closing_balance_minor,
        txn_total=txn_total,
    )

    # Archive — abort before any DB write if it fails.
    archive_path: Path | None = (
        archive_file(
            path,
            source_id=account.source_id,
            file_hash=file_hash,
            archive_dir=archive_dir,
        )
        if archive
        else None
    )
    archive_path_str = str(archive_path) if archive_path else None

    # Atomic stage.
    parsed_at = _utcnow()
    with store.transaction():
        cur = store.execute(
            "INSERT INTO statement_batches (source_id, file_hash, file_path_original, "
            "file_path_archive, parser, statement_period_start, statement_period_end, "
            "opening_balance_minor, closing_balance_minor, parsed_at, review_status, "
            "review_resolved_at, txn_count, reconciliation_status, drift_minor, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?, ?, NULL)",
            (
                account.source_id,
                file_hash,
                str(path),
                archive_path_str,
                parsed.source_format,
                parsed.statement_period_start,
                parsed.statement_period_end,
                parsed.opening_balance_minor,
                parsed.closing_balance_minor,
                parsed_at,
                len(stamped),
                recon_status,
                drift_minor,
            ),
        )
        batch_id = cast(int, cur.lastrowid)

        counters = _upsert.new_counters()
        for txn in stamped:
            _upsert.upsert_transaction(
                store,
                account.source_id,
                txn,
                counters,
                status="pending_review",
                batch_id=batch_id,
            )

    first_n = tuple(
        TxnPreview(date=t.date, amount_minor=t.amount_minor, payee=t.payee, memo=t.memo)
        for t in stamped[:preview_sample_size]
    )
    return BatchPreview(
        batch_id=batch_id,
        source_id=account.source_id,
        txn_count=len(stamped),
        reconciliation_status=recon_status,
        drift_minor=drift_minor,
        statement_period_start=parsed.statement_period_start,
        statement_period_end=parsed.statement_period_end,
        opening_balance_minor=parsed.opening_balance_minor,
        closing_balance_minor=parsed.closing_balance_minor,
        file_path_archive=archive_path_str,
        first_transactions=first_n,
    )


# ---------------------------------------------------------------------------
# Batch lifecycle: confirm / reject / list


def confirm_batch(store: Store, batch_id: int) -> dict[str, Any]:
    """Flip a pending batch's transactions to ``status='confirmed'`` atomically."""
    row = store.execute(
        "SELECT review_status FROM statement_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"batch {batch_id} not found")
    if row["review_status"] != "pending":
        raise ValueError(f"batch {batch_id} is not pending (status: {row['review_status']!r})")

    now = _utcnow()
    with store.transaction():
        store.execute(
            "UPDATE transactions SET status = 'confirmed' "
            "WHERE batch_id = ? AND status = 'pending_review'",
            (batch_id,),
        )
        store.execute(
            "UPDATE statement_batches "
            "SET review_status = 'confirmed', review_resolved_at = ? "
            "WHERE id = ?",
            (now, batch_id),
        )
    return {"batch_id": batch_id, "review_status": "confirmed", "review_resolved_at": now}


def reject_batch(store: Store, batch_id: int) -> dict[str, Any]:
    """Delete a pending batch's staged transactions; keep batch row for audit."""
    row = store.execute(
        "SELECT review_status FROM statement_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"batch {batch_id} not found")
    if row["review_status"] != "pending":
        raise ValueError(f"batch {batch_id} is not pending (status: {row['review_status']!r})")

    now = _utcnow()
    with store.transaction():
        store.execute("DELETE FROM transactions WHERE batch_id = ?", (batch_id,))
        store.execute(
            "UPDATE statement_batches "
            "SET review_status = 'rejected', review_resolved_at = ? "
            "WHERE id = ?",
            (now, batch_id),
        )
    return {"batch_id": batch_id, "review_status": "rejected", "review_resolved_at": now}


def list_batches(
    store: Store,
    *,
    source_id: str | None = None,
    review_status: str | None = "pending",
) -> list[dict[str, Any]]:
    """List batches matching the filters (most-recent first)."""
    where: list[str] = []
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if review_status is not None:
        where.append("review_status = ?")
        params.append(review_status)
    sql = (
        "SELECT id, source_id, parser, txn_count, review_status, "
        "reconciliation_status, drift_minor, parsed_at, file_path_original "
        "FROM statement_batches "
    )
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY id DESC"
    return [
        {k: r[k] for k in r.keys()}  # noqa: SIM118 — sqlite3.Row needs .keys()
        for r in store.execute(sql, params).fetchall()
    ]
