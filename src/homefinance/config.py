"""Configuration loading: TOML file + environment-variable overrides.

Resolution order for each value:
1. Environment variable (HOMEFINANCE_*)
2. TOML file at HOMEFINANCE_CONFIG (or the XDG/dotfile default)
3. Built-in default
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class YNABBudget(BaseModel):
    """One YNAB budget tracked by this install."""

    model_config = ConfigDict(extra="forbid")

    budget_id: str
    nickname: str | None = None


class YNABConfig(BaseModel):
    """The `[ynab]` section of `config.toml`."""

    model_config = ConfigDict(extra="forbid")

    token: SecretStr | None = None
    budgets: list[YNABBudget] = Field(default_factory=list)


class Config(BaseModel):
    """Effective configuration after resolving env + file."""

    model_config = ConfigDict(extra="forbid")

    config_path: Path
    db_path: Path
    ynab: YNABConfig = Field(default_factory=YNABConfig)

    @property
    def ynab_token(self) -> SecretStr | None:
        """Env beats file. None if neither is set."""
        env = os.environ.get("HOMEFINANCE_YNAB_TOKEN")
        if env:
            return SecretStr(env)
        return self.ynab.token


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "homefinance" / "config.toml"
    return Path.home() / ".homefinance" / "config.toml"


def default_db_path() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "homefinance" / "db.sqlite3"
    return Path.home() / ".homefinance" / "db.sqlite3"


def load_config() -> Config:
    """Resolve config from env + TOML file, returning an effective Config."""
    config_path = Path(os.environ.get("HOMEFINANCE_CONFIG") or default_config_path())
    db_path = Path(os.environ.get("HOMEFINANCE_DB") or default_db_path())

    file_data: dict[str, Any] = {}
    if config_path.exists():
        file_data = tomllib.loads(config_path.read_text())

    ynab = YNABConfig(**file_data.get("ynab", {}))
    return Config(config_path=config_path, db_path=db_path, ynab=ynab)
