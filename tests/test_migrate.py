import sqlite3
from pathlib import Path

from homefinance.db.migrate import migrate, migrations_dir


def test_migrate_creates_schema_on_fresh_db(tmp_path: Path) -> None:
    db = tmp_path / "subdir" / "fresh.sqlite3"  # parent doesn't exist
    migrate(db)
    assert db.exists()
    with sqlite3.connect(db) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    expected = {
        "accounts",
        "categories",
        "payees",
        "sources",
        "sync_runs",
        "sync_state",
        "transactions",
    }
    assert expected.issubset(tables)


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "again.sqlite3"
    migrate(db)
    migrate(db)  # second run must not raise
    with sqlite3.connect(db) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()[0]
    assert n == 1


def test_migrations_dir_resolves_to_a_real_dir_with_files() -> None:
    d = migrations_dir()
    assert d.is_dir()
    sql_files = list(d.glob("*.sql"))
    assert len(sql_files) >= 1
