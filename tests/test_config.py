from pathlib import Path

import pytest

from homefinance.config import (
    Config,
    YNABBudget,
    default_config_path,
    default_db_path,
    load_config,
)


def test_default_paths_use_dotfile_when_no_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".homefinance" / "config.toml"
    assert default_db_path() == tmp_path / ".homefinance" / "db.sqlite3"


def test_default_paths_respect_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    assert default_config_path() == tmp_path / "xdg_cfg" / "homefinance" / "config.toml"
    assert default_db_path() == tmp_path / "xdg_data" / "homefinance" / "db.sqlite3"


def test_load_config_reads_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[[ynab.budgets]]\nbudget_id = "abc"\nnickname = "personal"\n'
        '[[ynab.budgets]]\nbudget_id = "def"\nnickname = "family"\n'
    )
    monkeypatch.setenv("HOMEFINANCE_CONFIG", str(cfg_path))
    monkeypatch.setenv("HOMEFINANCE_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.delenv("HOMEFINANCE_YNAB_TOKEN", raising=False)
    cfg = load_config()
    assert cfg.config_path == cfg_path
    assert cfg.db_path == tmp_path / "db.sqlite3"
    assert cfg.ynab.budgets == [
        YNABBudget(budget_id="abc", nickname="personal"),
        YNABBudget(budget_id="def", nickname="family"),
    ]
    assert cfg.ynab_token is None


def test_env_token_beats_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[ynab]\ntoken = "FILE-TOKEN"\n')
    monkeypatch.setenv("HOMEFINANCE_CONFIG", str(cfg_path))
    monkeypatch.setenv("HOMEFINANCE_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("HOMEFINANCE_YNAB_TOKEN", "ENV-TOKEN")
    cfg = load_config()
    assert cfg.ynab_token is not None
    assert cfg.ynab_token.get_secret_value() == "ENV-TOKEN"


def test_missing_file_yields_empty_ynab_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOMEFINANCE_CONFIG", str(tmp_path / "nope.toml"))
    monkeypatch.setenv("HOMEFINANCE_DB", str(tmp_path / "db.sqlite3"))
    monkeypatch.delenv("HOMEFINANCE_YNAB_TOKEN", raising=False)
    cfg = load_config()
    assert cfg.ynab.budgets == []
    assert cfg.ynab_token is None


def test_config_secret_never_in_repr() -> None:
    cfg = Config(
        config_path=Path("/tmp/c"),
        db_path=Path("/tmp/db"),
        ynab={"token": "SUPER-SECRET"},
    )
    assert "SUPER-SECRET" not in repr(cfg)
    assert "SUPER-SECRET" not in str(cfg.ynab)
