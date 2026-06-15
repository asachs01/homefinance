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
            "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, "2026-06-10T00:00:00+00:00"),
        )
        conn.commit()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "ynab:abc" in result.stdout
    assert "personal" in result.stdout


from homefinance.sources.ynab.fake_client import FakeYNABClient  # noqa: E402


def _patch_client(monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path) -> None:
    monkeypatch.setattr("homefinance.cli._make_client", lambda token: FakeYNABClient(fixtures_dir))


def test_init_writes_config_and_migrates_db(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    result = runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    assert result.exit_code == 0, result.stdout
    cfg = (env / "config.toml").read_text()
    assert 'budget_id = "budget-tiny"' in cfg
    assert 'nickname = "tiny"' in cfg
    assert (env / "db.sqlite3").exists()


def test_init_writes_config_with_owner_only_permissions(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    result = runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    assert result.exit_code == 0, result.stdout
    cfg_path = env / "config.toml"
    mode = cfg_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
    parent_mode = cfg_path.parent.stat().st_mode & 0o777
    assert parent_mode == 0o700, f"expected 0o700 on parent, got {oct(parent_mode)}"


def test_init_tightens_permissions_on_preexisting_loose_config(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    """Upgrade case: a config.toml left behind at 0o644 by a prior install (or
    by a user editing it manually) must be tightened to 0o600 on rewrite —
    O_CREAT's mode arg is a no-op when the file already exists, so the explicit
    chmod is what guarantees this."""
    import os as _os

    _patch_client(monkeypatch, tiny_fixtures_dir)
    cfg_path = env / "config.toml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("# pre-existing loose config\n")
    _os.chmod(cfg_path, 0o644)
    assert (cfg_path.stat().st_mode & 0o777) == 0o644  # sanity

    result = runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    assert result.exit_code == 0, result.stdout
    assert (cfg_path.stat().st_mode & 0o777) == 0o600, (
        f"upgrade did not tighten; got {oct(cfg_path.stat().st_mode & 0o777)}"
    )


def test_init_runs_first_sync_unless_no_sync(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    result = runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny"],
    )
    assert result.exit_code == 0, result.stdout
    assert "3 new" in result.stdout or "synced" in result.stdout.lower()

    import sqlite3

    with sqlite3.connect(env / "db.sqlite3") as conn:
        n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert n >= 3  # parent split counts; children add more


def test_sync_processes_all_configured_budgets(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    monkeypatch.setenv("HOMEFINANCE_YNAB_TOKEN", "T")
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0, result.stdout
    assert "tiny" in result.stdout
    assert "reconciliation" in result.stdout


def test_sync_fails_clearly_without_token(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    # No HOMEFINANCE_YNAB_TOKEN, no token in file
    result = runner.invoke(app, ["sync"])
    assert result.exit_code != 0
    assert "token" in result.stdout.lower() or "token" in (result.stderr or "").lower()


def test_sync_with_source_flag_targets_one(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    monkeypatch.setenv("HOMEFINANCE_YNAB_TOKEN", "T")
    result = runner.invoke(app, ["sync", "--source", "ynab:budget-tiny"])
    assert result.exit_code == 0, result.stdout


def test_ynab_add_budget_appends_to_config(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    result = runner.invoke(
        app, ["ynab", "add-budget", "--budget-id", "budget-second", "--nickname", "second"]
    )
    assert result.exit_code == 0, result.stdout
    cfg = (env / "config.toml").read_text()
    assert 'budget_id = "budget-tiny"' in cfg
    assert 'budget_id = "budget-second"' in cfg
    assert 'nickname = "second"' in cfg


def test_ynab_remove_budget_drops_entry(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    runner.invoke(
        app, ["ynab", "add-budget", "--budget-id", "budget-second", "--nickname", "second"]
    )
    result = runner.invoke(app, ["ynab", "remove-budget", "--budget-id", "budget-tiny"])
    assert result.exit_code == 0, result.stdout
    cfg = (env / "config.toml").read_text()
    assert 'budget_id = "budget-tiny"' not in cfg
    assert 'budget_id = "budget-second"' in cfg


def test_ynab_remove_unknown_budget_errors(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    result = runner.invoke(app, ["ynab", "remove-budget", "--budget-id", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower() or "not found" in (result.stderr or "").lower()


def test_accounts_add_creates_source_row(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    result = runner.invoke(
        app,
        [
            "accounts",
            "add",
            "--nickname",
            "citi-cc",
            "--type",
            "credit_card",
            "--currency",
            "USD",
            "--display-name",
            "Citi Credit Card",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Added" in result.stdout
    assert "statement:citi-cc" in result.stdout

    import sqlite3

    with sqlite3.connect(env / "db.sqlite3") as conn:
        srcs = {r[0] for r in conn.execute("SELECT id FROM sources").fetchall()}
        accts = {r[0] for r in conn.execute("SELECT id FROM accounts").fetchall()}
    assert "statement:citi-cc" in srcs
    assert "statement:citi-cc:account" in accts


def test_accounts_add_invalid_type_errors(
    env: Path, monkeypatch: pytest.MonkeyPatch, tiny_fixtures_dir: Path
) -> None:
    _patch_client(monkeypatch, tiny_fixtures_dir)
    runner.invoke(
        app,
        ["init", "--token", "T", "--budget", "budget-tiny", "--nickname", "tiny", "--no-sync"],
    )
    result = runner.invoke(
        app, ["accounts", "add", "--nickname", "x", "--type", "banana"]
    )
    assert result.exit_code != 0
