"""SQLite store: thin wrapper over `sqlite3.Connection` with explicit
PRAGMAs, an atomic-transaction context manager, and `sqlite3.Row`-based reads.

No ORM. All SQL is hand-written and lives close to its callers (mostly in
`sources/ynab/sync.py` and `mcp_server/tools.py`).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection, Cursor, Row, connect
from typing import Any


class Store:
    """A connected SQLite store. Construct via `Store.open(path)`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> Store:
        conn = connect(db_path, isolation_level=None)  # autocommit; we manage txns
        conn.row_factory = Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Cursor:
        return self._conn.executemany(sql, seq_of_params)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run a block atomically; rolls back on exception."""
        self._conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
