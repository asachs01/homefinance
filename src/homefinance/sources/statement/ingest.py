"""Statement ingest orchestrator and its helpers.

This module is built up across Tasks 10-12 of the SP2 plan:
- Task 10: small helpers + register/resolve account + BatchPreview shape
- Task 11: ``ingest_file()`` — parse + reconcile + atomic stage
- Task 12: ``confirm_batch()``, ``reject_batch()``, ``list_batches()``
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from homefinance.db import _upsert
from homefinance.db.store import Store
from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.archive import archive_file

# Side-effect imports: each parser module self-registers at import time. The
# heavy optional deps (``docling``, ``ofxtools``) are still lazy-imported
# inside the concrete parsers, so loading these modules is cheap.
from homefinance.sources.statement.parsers import csv as _csv_parser  # noqa: F401
from homefinance.sources.statement.parsers import docling_pdf as _docling_parser  # noqa: F401
from homefinance.sources.statement.parsers import find_parser
from homefinance.sources.statement.parsers import ofx as _ofx_parser  # noqa: F401
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

    existing = store.execute(
        "SELECT 1 FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if existing:
        raise AccountAlreadyRegistered(f"source {source_id!r} already exists")

    now = _utcnow()
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
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

    # File-level dedup
    prior = store.execute(
        "SELECT id, review_status FROM statement_batches "
        "WHERE file_hash = ? AND source_id = ?",
        (file_hash, account.source_id),
    ).fetchone()
    if prior:
        if prior["review_status"] in ("pending", "confirmed") and not allow_reingest:
            raise FileAlreadyIngested(
                f"already ingested as batch #{prior['id']} "
                f"(status: {prior['review_status']}). Use --reingest to re-process."
            )
        if allow_reingest:
            store.execute(
                "DELETE FROM statement_batches WHERE id = ?", (prior["id"],)
            )

    parser_cls = find_parser(path)
    template = load_template(account.source_id, config_dir=config_dir)
    parsed = parser_cls.parse(path, account, template)

    # Build synthetic external IDs, suffixing within-batch collisions
    seen: dict[str, int] = {}
    txns_with_ids: list[tuple[str, RemoteTransaction]] = []
    for txn in parsed.transactions:
        base = row_external_id(
            account.account_id, txn.date, txn.amount_minor, txn.payee, txn.memo
        )
        n = seen.get(base, 0)
        external_id = base if n == 0 else f"{base}:{n}"
        seen[base] = n + 1
        txns_with_ids.append((external_id, txn))

    # Reconcile
    txn_total = sum(t.amount_minor for _, t in txns_with_ids)
    recon_status, drift_minor = reconcile(
        opening=parsed.opening_balance_minor,
        closing=parsed.closing_balance_minor,
        txn_total=txn_total,
    )

    # Archive — abort before any DB write if it fails
    archive_path: Path | None = None
    if archive:
        archive_path = archive_file(
            path,
            source_id=account.source_id,
            file_hash=file_hash,
            archive_dir=archive_dir,
        )

    # Atomic stage
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
                str(archive_path) if archive_path else None,
                parsed.source_format,
                parsed.statement_period_start,
                parsed.statement_period_end,
                parsed.opening_balance_minor,
                parsed.closing_balance_minor,
                parsed_at,
                len(txns_with_ids),
                recon_status,
                drift_minor,
            ),
        )
        batch_id = cast(int, cur.lastrowid)

        # CRITICAL: pre-seed the counters dict that _upsert.upsert_transaction
        # mutates via `counters[name] += 1`. The keys MUST exist or we KeyError.
        counters: dict[str, int] = {
            "inserted": 0,
            "updated": 0,
            "deleted": 0,
            "accounts_touched": 0,
        }
        # Stage each transaction as pending_review with batch_id linking back.
        for external_id, txn in txns_with_ids:
            stamped = replace(txn, external_id=external_id, account_external_id="account")
            _upsert.upsert_transaction(
                store,
                account.source_id,
                stamped,
                counters,
                status="pending_review",
                batch_id=batch_id,
            )

    first_n = tuple(
        TxnPreview(date=t.date, amount_minor=t.amount_minor, payee=t.payee, memo=t.memo)
        for _, t in txns_with_ids[:preview_sample_size]
    )
    return BatchPreview(
        batch_id=batch_id,
        source_id=account.source_id,
        txn_count=len(txns_with_ids),
        reconciliation_status=recon_status,
        drift_minor=drift_minor,
        statement_period_start=parsed.statement_period_start,
        statement_period_end=parsed.statement_period_end,
        opening_balance_minor=parsed.opening_balance_minor,
        closing_balance_minor=parsed.closing_balance_minor,
        file_path_archive=str(archive_path) if archive_path else None,
        first_transactions=first_n,
    )
