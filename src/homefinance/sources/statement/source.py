"""``StatementAccountSource`` — implements ``AccountSource`` for statement-fed accounts.

Honest divergence from YNAB: statements don't sync from a remote. ``pull()``
returns an empty ``SyncDelta``; the actual write path is ``ingest_file()`` in
``ingest.py``. The Protocol is honored so MCP read tools treat statement
sources uniformly with YNAB sources.
"""

from __future__ import annotations

from typing import Literal

from homefinance.db.store import Store
from homefinance.sources.base import SyncDelta
from homefinance.sources.statement.ingest import resolve_account


class StatementAccountSource:
    """One statement-fed account surfaced as an ``AccountSource``."""

    kind: Literal["statement"] = "statement"

    def __init__(self, *, store: Store, nickname: str) -> None:
        self._store = store
        self.nickname = nickname
        self.source_id = f"statement:{nickname}"

    def validate(self) -> None:
        """Raises ``AccountNotConfigured`` if the nickname isn't registered."""
        resolve_account(self._store, self.nickname)

    def pull(self, cursor: int | None) -> SyncDelta:
        """Statements don't sync from a remote. Return an empty delta."""
        return SyncDelta(
            accounts=(),
            categories=(),
            payees=(),
            transactions=(),
            new_cursor=None,
        )
