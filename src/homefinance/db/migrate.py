"""Run schema migrations against the local SQLite DB.

Migrations live in `src/homefinance/db/migrations/` as plain SQL files
following yoyo-migrations' naming convention. We delegate to yoyo for
discovery, locking, and bookkeeping (it creates `_yoyo_*` tables to track
applied migrations, which makes runs idempotent).
"""

from __future__ import annotations

from pathlib import Path

from yoyo import get_backend, read_migrations


def migrations_dir() -> Path:
    """Absolute path to the bundled migrations directory."""
    return Path(__file__).resolve().parent / "migrations"


def migrate(db_path: Path) -> None:
    """Apply all pending migrations to the SQLite DB at `db_path`.

    Creates the parent directory if it does not yet exist. Safe to call
    repeatedly; yoyo records applied migrations and skips them.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backend = get_backend(f"sqlite:///{db_path}")
    migrations = read_migrations(str(migrations_dir()))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
