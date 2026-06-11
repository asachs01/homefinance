from pathlib import Path

import pytest
from typer.testing import CliRunner

from homefinance.cli import app
from homefinance.db.migrate import migrate

runner = CliRunner()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOMEFINANCE_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("HOMEFINANCE_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.delenv("HOMEFINANCE_YNAB_TOKEN", raising=False)
    return tmp_path


def test_db_path_prints_resolved_db_path(env: Path) -> None:
    result = runner.invoke(app, ["db-path"])
    assert result.exit_code == 0
    assert str(env / "db.sqlite3") in result.stdout


def test_status_explains_when_no_sources_yet(env: Path) -> None:
    migrate(env / "db.sqlite3")
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "No sources configured" in result.stdout
    assert "homefinance init" in result.stdout


def test_status_lists_configured_sources(env: Path) -> None:
    db = env / "db.sqlite3"
    migrate(db)
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, "2026-06-10T00:00:00+00:00"),
        )
        conn.commit()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "ynab:abc" in result.stdout
    assert "personal" in result.stdout
