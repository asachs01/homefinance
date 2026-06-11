from datetime import UTC, datetime
from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "test.sqlite3"
    migrate(db)
    return Store.open(db)


def test_open_enables_foreign_keys_and_wal(store: Store) -> None:
    assert store.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert store.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_transaction_commits_on_success(store: Store) -> None:
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, datetime.now(UTC).isoformat()),
        )
    rows = store.execute("SELECT id FROM sources").fetchall()
    assert [r[0] for r in rows] == ["ynab:abc"]


def test_transaction_rolls_back_on_exception(store: Store) -> None:
    with pytest.raises(RuntimeError, match="boom"), store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            ("ynab:xyz", "ynab", None, None, "2026-06-10T00:00:00+00:00"),
        )
        raise RuntimeError("boom")
    assert store.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_executemany_runs_under_transaction(store: Store) -> None:
    rows = [
        ("ynab:1", "ynab", None, None, "2026-06-10T00:00:00+00:00"),
        ("ynab:2", "ynab", None, None, "2026-06-10T00:00:00+00:00"),
    ]
    with store.transaction():
        store.executemany(
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    assert store.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2


def test_rows_are_dict_accessible(store: Store) -> None:
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, "2026-06-10T00:00:00+00:00"),
        )
    row = store.execute("SELECT * FROM sources WHERE id = ?", ("ynab:abc",)).fetchone()
    assert row["nickname"] == "personal"
    assert row["kind"] == "ynab"
