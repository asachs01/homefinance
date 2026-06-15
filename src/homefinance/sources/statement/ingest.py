"""Statement ingest orchestrator and its helpers.

This module is built up across Tasks 10-12 of the SP2 plan:
- Task 10: small helpers + register/resolve account + BatchPreview shape
- Task 11: ``ingest_file()`` — parse + reconcile + atomic stage
- Task 12: ``confirm_batch()``, ``reject_batch()``, ``list_batches()``
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from homefinance.db.store import Store
from homefinance.sources.statement.parsers.base import (
    AccountNotConfigured,
    ResolvedAccount,
)

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
