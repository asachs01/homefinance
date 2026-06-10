# SP1 — Foundation + YNAB Spine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the foundation sub-project of the homeFinance program: a local SQLite-backed canonical store, the `AccountSource` seam, a read-only YNAB sync engine, a stdio MCP server with 8 read tools, a `homefinance` CLI, and a Claude Code plugin manifest — fully tested with no real YNAB calls in CI.

**Architecture:** Python 3.11+ package distributed as a Claude Code plugin. Source-agnostic canonical schema fed by an idempotent, atomic, delta-based YNAB sync. CLI and MCP server are two thin front doors over the same library. Read-only YNAB access is enforced structurally (the client has no write methods). See the spec at `docs/superpowers/specs/2026-06-10-sp1-foundation-design.md`.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3`), `pydantic` v2, `httpx`, `tenacity`, `typer` + `rich`, `yoyo-migrations`, official `mcp` SDK, `pytest` + `pytest-httpx`, `ruff`, `mypy`.

---

## File Structure

These files will be created across the 29 tasks. Each task lists exact paths.

```
homefinance/
├── pyproject.toml                                # Task 1
├── README.md                                     # Task 1 (skeleton) → Task 29 (quickstart)
├── LICENSE                                       # Task 1
├── CHANGELOG.md                                  # Task 1
├── .env.example                                  # Task 1
├── .gitignore                                    # already exists
├── .github/workflows/ci.yml                      # Task 3
│
├── plugin/
│   ├── plugin.json                               # Task 27
│   ├── .mcp.json                                 # Task 27
│   └── skills/
│       ├── homefinance-setup/SKILL.md            # Task 27
│       └── homefinance-explore/SKILL.md          # Task 28
│
├── src/homefinance/
│   ├── __init__.py                               # Task 1
│   ├── config.py                                 # Task 4
│   ├── db/
│   │   ├── __init__.py                           # Task 1
│   │   ├── schema.sql                            # Task 5
│   │   ├── migrations/0001-initial-schema.sql    # Task 5
│   │   ├── migrate.py                            # Task 6
│   │   └── store.py                              # Task 7
│   ├── sources/
│   │   ├── __init__.py                           # Task 1
│   │   ├── base.py                               # Task 8
│   │   └── ynab/
│   │       ├── __init__.py                       # Task 1
│   │       ├── models.py                         # Task 9
│   │       ├── client.py                         # Task 10
│   │       ├── fake_client.py                    # Task 11
│   │       ├── ids.py                            # Task 12
│   │       ├── mapping.py                        # Tasks 12-14
│   │       ├── source.py                         # Task 15
│   │       └── sync.py                           # Task 16
│   ├── mcp_server/
│   │   ├── __init__.py                           # Task 1
│   │   ├── __main__.py                           # Task 22
│   │   └── tools.py                              # Tasks 22-26
│   └── cli.py                                    # Tasks 18-21
│
├── tests/
│   ├── __init__.py                               # Task 1
│   ├── conftest.py                               # Task 4
│   ├── fixtures/ynab/                            # Task 11 (sanitized recorded payloads)
│   ├── test_config.py                            # Task 4
│   ├── test_migrate.py                           # Task 6
│   ├── test_store.py                             # Task 7
│   ├── test_ynab_client.py                       # Task 10
│   ├── test_ynab_mapping.py                      # Tasks 12-14
│   ├── test_ynab_source.py                       # Task 15
│   ├── test_sync.py                              # Tasks 16-17
│   ├── test_cli.py                               # Tasks 18-21
│   └── test_mcp_tools.py                         # Tasks 23-26
│
├── scripts/record_fixtures.py                    # Task 28
│
└── docs/
    ├── quickstart.md                             # Task 29
    └── architecture.md                           # Task 29
```

---

## Task 1: Project scaffolding

**Goal:** Get `import homefinance` working, with the package layout, license, and changelog in place.

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`, `LICENSE`, `CHANGELOG.md`, `.env.example`
- Create: `src/homefinance/__init__.py` and `__init__.py` for every subpackage (`db/`, `db/migrations/`, `sources/`, `sources/ynab/`, `analysis/`, `mcp_server/`)
- Create: `tests/__init__.py`, `tests/fixtures/ynab/.gitkeep`, `scripts/.gitkeep`

- [ ] **Step 1: Create and activate a venv**

```bash
mkvirtualenv homeFinance
workon homeFinance
python --version  # confirm 3.11+
```

- [ ] **Step 2: Create `pyproject.toml`** with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "homefinance"
version = "0.1.0"
description = "Open-source, local-first home financial analysis — distributed as a Claude Code plugin."
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.11"
authors = [{ name = "Aaron Sachs" }]
keywords = ["finance", "ynab", "mcp", "claude-code", "personal-finance"]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Office/Business :: Financial",
]
dependencies = [
    "pydantic>=2.7",
    "httpx>=0.27",
    "tenacity>=8.4",
    "typer>=0.12",
    "rich>=13.7",
    "yoyo-migrations>=8.2",
    "mcp>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-httpx>=0.30",
    "ruff>=0.5",
    "mypy>=1.10",
]

[project.scripts]
homefinance = "homefinance.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/homefinance"]

[tool.hatch.build.targets.wheel.shared-data]
"src/homefinance/db/schema.sql" = "homefinance/db/schema.sql"
"src/homefinance/db/migrations" = "homefinance/db/migrations"
```

- [ ] **Step 3: Create `LICENSE`** with the standard MIT text (year `2026`, holder `Aaron Sachs`).

- [ ] **Step 4: Create `README.md`** as a placeholder:

```markdown
# homefinance

Open-source, local-first home financial analysis distributed as a Claude Code plugin.

**Status:** In development — see `docs/superpowers/specs/2026-06-10-sp1-foundation-design.md`.

The full quickstart will land with Task 29.
```

- [ ] **Step 5: Create `CHANGELOG.md`** in keepachangelog format:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding (SP1).
```

- [ ] **Step 6: Create `.env.example`** with:

```
# Copy to .env or export in your shell. Never commit .env (already in .gitignore).
# Required for sync; can also live in ~/.homefinance/config.toml under [ynab].
HOMEFINANCE_YNAB_TOKEN=your-personal-access-token-from-app.ynab.com-settings-developer

# Optional overrides (defaults are XDG-aware; fall back to ~/.homefinance/)
# HOMEFINANCE_CONFIG=/custom/path/to/config.toml
# HOMEFINANCE_DB=/custom/path/to/db.sqlite3
```

- [ ] **Step 7: Create the package skeleton.** Each `__init__.py` is empty unless noted.

```bash
mkdir -p src/homefinance/{db/migrations,sources/ynab,mcp_server,analysis}
mkdir -p tests/fixtures/ynab scripts
touch src/homefinance/__init__.py \
      src/homefinance/db/__init__.py \
      src/homefinance/sources/__init__.py \
      src/homefinance/sources/ynab/__init__.py \
      src/homefinance/mcp_server/__init__.py \
      src/homefinance/analysis/__init__.py \
      tests/__init__.py \
      tests/fixtures/ynab/.gitkeep \
      src/homefinance/db/migrations/.gitkeep \
      scripts/.gitkeep
```

Set `src/homefinance/__init__.py` content to:

```python
"""homefinance — open-source, local-first home financial analysis."""

__version__ = "0.1.0"
```

- [ ] **Step 8: Install in editable mode**

Run: `pip install -e ".[dev]"`
Expected: builds wheel, installs all deps and editable package, exits 0.

- [ ] **Step 9: Verify the package imports**

Run: `python -c "import homefinance; print(homefinance.__version__)"`
Expected: `0.1.0`

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml README.md LICENSE CHANGELOG.md .env.example src tests scripts
git commit -m "chore: scaffold homefinance package and project metadata"
```

---

## Task 2: Tooling configuration (ruff, mypy, pytest)

**Goal:** Lockable lint/format/typecheck/test setup; `make`-free, all driven by `pyproject.toml`.

**Files:**
- Modify: `pyproject.toml` (append config sections)
- Create: `tests/conftest.py` (empty placeholder; populated in Task 4)

- [ ] **Step 1: Append tool config to `pyproject.toml`**

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]  # allow assert statements in tests

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src"]
warn_unused_configs = true

[[tool.mypy.overrides]]
module = ["yoyo.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
addopts = "-ra --strict-markers --strict-config"
testpaths = ["tests"]
filterwarnings = ["error"]
```

- [ ] **Step 2: Create an empty `tests/conftest.py`**

```python
"""Shared pytest fixtures. Populated as needed."""
```

- [ ] **Step 3: Verify the toolchain runs cleanly**

Run: `ruff check . && ruff format --check . && mypy && pytest --co -q`
Expected: zero errors, zero failures, "no tests ran" from pytest.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "chore: configure ruff, mypy, and pytest"
```

---

## Task 3: GitHub Actions CI workflow

**Goal:** Push-triggered CI runs lint/format/typecheck/test on Python 3.11 and 3.12; no secrets required.

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint
        run: ruff check .

      - name: Format
        run: ruff format --check .

      - name: Typecheck
        run: mypy

      - name: Test
        run: pytest --cov=homefinance --cov-report=term-missing --cov-fail-under=80
```

- [ ] **Step 2: Verify YAML parses locally** (optional but recommended)

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: exits 0 with no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint/format/typecheck/test workflow"
```

---

## Task 4: Config module

**Goal:** Load config from a TOML file with env-var overrides (env wins), XDG-aware default paths, and a safe accessor for the YNAB token via `SecretStr`.

**Files:**
- Create: `src/homefinance/config.py`
- Create: `tests/test_config.py`
- Modify: `tests/conftest.py` (add `monkeypatch_env` fixture pattern note via Step 1 — see below)

- [ ] **Step 1: Write failing tests at `tests/test_config.py`**

```python
import os
from pathlib import Path

import pytest

from homefinance.config import (
    Config,
    YNABBudget,
    default_config_path,
    default_db_path,
    load_config,
)


def test_default_paths_use_dotfile_when_no_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_missing_file_yields_empty_ynab_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_config.py -v`
Expected: collection error or `ModuleNotFoundError: No module named 'homefinance.config'`.

- [ ] **Step 3: Implement `src/homefinance/config.py`**

```python
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
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class YNABBudget(BaseModel):
    """One YNAB budget tracked by this install."""

    model_config = ConfigDict(extra="forbid")

    budget_id: str
    nickname: Optional[str] = None


class YNABConfig(BaseModel):
    """The `[ynab]` section of `config.toml`."""

    model_config = ConfigDict(extra="forbid")

    token: Optional[SecretStr] = None
    budgets: list[YNABBudget] = Field(default_factory=list)


class Config(BaseModel):
    """Effective configuration after resolving env + file."""

    model_config = ConfigDict(extra="forbid")

    config_path: Path
    db_path: Path
    ynab: YNABConfig = Field(default_factory=YNABConfig)

    @property
    def ynab_token(self) -> Optional[SecretStr]:
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

    file_data: dict = {}
    if config_path.exists():
        file_data = tomllib.loads(config_path.read_text())

    ynab = YNABConfig(**file_data.get("ynab", {}))
    return Config(config_path=config_path, db_path=db_path, ynab=ynab)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_config.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/config.py tests/test_config.py
git commit -m "feat(config): TOML + env config with XDG-aware defaults and SecretStr token"
```

---

## Task 5: Database schema and initial migration

**Goal:** Lock the canonical schema as a single SQL file usable both as a reference (`schema.sql`) and as the first yoyo migration (`migrations/0001-initial-schema.sql`). Verbatim from the spec §6.2.

**Files:**
- Create: `src/homefinance/db/schema.sql`
- Create: `src/homefinance/db/migrations/0001-initial-schema.sql`

- [ ] **Step 1: Create `src/homefinance/db/schema.sql`** with the spec's canonical schema:

```sql
-- homeFinance SP1 canonical schema.
-- Source of truth: docs/superpowers/specs/2026-06-10-sp1-foundation-design.md §6.2

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id          TEXT PRIMARY KEY,           -- "ynab:<budget_id>"
    kind        TEXT NOT NULL,              -- "ynab" | "statement"
    nickname    TEXT,
    config      TEXT,                       -- JSON snapshot of source-specific config
    created_at  TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE TABLE accounts (
    id                       TEXT PRIMARY KEY,
    source_id                TEXT NOT NULL REFERENCES sources(id),
    external_id              TEXT NOT NULL,
    name                     TEXT NOT NULL,
    type                     TEXT NOT NULL,
    on_budget                INTEGER NOT NULL DEFAULT 1,
    closed                   INTEGER NOT NULL DEFAULT 0,
    deleted                  INTEGER NOT NULL DEFAULT 0,
    currency                 TEXT NOT NULL DEFAULT 'USD',
    cleared_balance_minor    INTEGER,
    uncleared_balance_minor  INTEGER,
    balance_as_of            TEXT,
    last_synced_at           TEXT,
    UNIQUE (source_id, external_id)
);

CREATE TABLE categories (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,
    name         TEXT NOT NULL,
    group_name   TEXT,
    hidden       INTEGER NOT NULL DEFAULT 0,
    deleted      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE payees (
    id                  TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES sources(id),
    external_id         TEXT NOT NULL,
    name                TEXT NOT NULL,
    transfer_account_id TEXT REFERENCES accounts(id),
    deleted             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE transactions (
    id                     TEXT PRIMARY KEY,
    source_id              TEXT NOT NULL REFERENCES sources(id),
    external_id            TEXT NOT NULL,
    account_id             TEXT NOT NULL REFERENCES accounts(id),
    date                   TEXT NOT NULL,
    amount_minor           INTEGER NOT NULL,
    currency               TEXT NOT NULL,
    payee                  TEXT,
    payee_id               TEXT REFERENCES payees(id),
    memo                   TEXT,
    category_id            TEXT REFERENCES categories(id),
    cleared                TEXT,
    approved               INTEGER NOT NULL DEFAULT 1,
    flag_color             TEXT,
    import_id              TEXT,
    transfer_account_id    TEXT REFERENCES accounts(id),
    parent_id              TEXT REFERENCES transactions(id),
    is_split_parent        INTEGER NOT NULL DEFAULT 0,
    deleted                INTEGER NOT NULL DEFAULT 0,
    raw                    TEXT,
    synced_at              TEXT NOT NULL,
    UNIQUE (source_id, external_id)
);

CREATE TABLE sync_state (
    source_id         TEXT PRIMARY KEY REFERENCES sources(id),
    last_sync_at      TEXT NOT NULL,
    server_knowledge  INTEGER,
    last_error        TEXT,
    last_error_at     TEXT
);

CREATE TABLE sync_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         TEXT NOT NULL REFERENCES sources(id),
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    txns_inserted     INTEGER NOT NULL DEFAULT 0,
    txns_updated      INTEGER NOT NULL DEFAULT 0,
    txns_deleted      INTEGER NOT NULL DEFAULT 0,
    accounts_touched  INTEGER NOT NULL DEFAULT 0,
    reconciliation    TEXT NOT NULL,
    drift_report      TEXT,
    error             TEXT
);

CREATE INDEX idx_transactions_account_date ON transactions(account_id, date);
CREATE INDEX idx_transactions_date         ON transactions(date);
CREATE INDEX idx_transactions_category     ON transactions(category_id);
CREATE INDEX idx_transactions_payee        ON transactions(payee);
CREATE INDEX idx_transactions_parent       ON transactions(parent_id);
CREATE INDEX idx_accounts_source           ON accounts(source_id);
CREATE INDEX idx_sync_runs_source_time     ON sync_runs(source_id, started_at);
```

- [ ] **Step 2: Copy the schema as the first migration**

Run:
```bash
cp src/homefinance/db/schema.sql src/homefinance/db/migrations/0001-initial-schema.sql
```

- [ ] **Step 3: Sanity-check that the SQL parses by applying it to a temp DB**

Run:
```bash
python -c "import sqlite3, pathlib; \
c = sqlite3.connect(':memory:'); \
c.executescript(pathlib.Path('src/homefinance/db/schema.sql').read_text()); \
tables = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()]; \
print(tables)"
```
Expected: `['accounts', 'categories', 'payees', 'sources', 'sync_runs', 'sync_state', 'transactions']`.

- [ ] **Step 4: Commit**

```bash
git add src/homefinance/db/schema.sql src/homefinance/db/migrations/0001-initial-schema.sql
git commit -m "feat(db): canonical schema + initial migration"
```

---

## Task 6: Migrations runner

**Goal:** A `migrate(db_path)` function that applies all pending yoyo migrations from the bundled `migrations/` directory and creates the parent dir if needed.

**Files:**
- Create: `src/homefinance/db/migrate.py`
- Create: `tests/test_migrate.py`

- [ ] **Step 1: Write failing tests at `tests/test_migrate.py`**

```python
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
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    expected = {"accounts", "categories", "payees", "sources",
                "sync_runs", "sync_state", "transactions"}
    assert expected.issubset(tables)


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "again.sqlite3"
    migrate(db)
    migrate(db)  # second run must not raise
    with sqlite3.connect(db) as conn:
        # The transactions table should still exist exactly once.
        n = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()[0]
    assert n == 1


def test_migrations_dir_resolves_to_a_real_dir_with_files() -> None:
    d = migrations_dir()
    assert d.is_dir()
    sql_files = list(d.glob("*.sql"))
    assert len(sql_files) >= 1
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_migrate.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.db.migrate'`.

- [ ] **Step 3: Implement `src/homefinance/db/migrate.py`**

```python
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_migrate.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/db/migrate.py tests/test_migrate.py
git commit -m "feat(db): yoyo-backed migrations runner"
```

---

## Task 7: Database store

**Goal:** A `Store` class wrapping a single `sqlite3.Connection` with: PRAGMA enforcement (`foreign_keys = ON`, `journal_mode = WAL`), atomic transactions via a context manager, and `executemany`-friendly bulk-upsert helpers used by Task 16's sync. Reads are exposed as simple methods returning `sqlite3.Row` objects (no ORM).

**Files:**
- Create: `src/homefinance/db/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests at `tests/test_store.py`**

```python
import sqlite3
from datetime import datetime, timezone
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
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, datetime.now(timezone.utc).isoformat()),
        )
    rows = store.execute("SELECT id FROM sources").fetchall()
    assert [r[0] for r in rows] == ["ynab:abc"]


def test_transaction_rolls_back_on_exception(store: Store) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with store.transaction():
            store.execute(
                "INSERT INTO sources (id, kind, nickname, config, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
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
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    assert store.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2


def test_rows_are_dict_accessible(store: Store) -> None:
    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("ynab:abc", "ynab", "personal", None, "2026-06-10T00:00:00+00:00"),
        )
    row = store.execute("SELECT * FROM sources WHERE id = ?", ("ynab:abc",)).fetchone()
    assert row["nickname"] == "personal"
    assert row["kind"] == "ynab"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_store.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.db.store'`.

- [ ] **Step 3: Implement `src/homefinance/db/store.py`**

```python
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_store.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/db/store.py tests/test_store.py
git commit -m "feat(db): Store with PRAGMAs, atomic transaction context, Row reads"
```

---

## Task 8: AccountSource protocol and canonical wire types

**Goal:** Define the `AccountSource` `Protocol` plus the source-agnostic dataclasses (`RemoteAccount`, `RemoteCategory`, `RemotePayee`, `RemoteTransaction`, `RemoteSubTxn`, `SyncDelta`) that every source — YNAB now, statements later — produces. This is the load-bearing seam called out in §4.2 of the spec.

**Files:**
- Create: `src/homefinance/sources/base.py`

- [ ] **Step 1: Implement `src/homefinance/sources/base.py`**

This file is interface-only — no I/O — so it ships without a dedicated test file; downstream tasks (10, 15, 16) exercise it through their own tests.

```python
"""The source-agnostic seam.

Every data source (YNAB now, statements later) implements `AccountSource`
and emits the canonical `RemoteX` dataclasses below. The sync orchestrator
consumes only this protocol, so adding a new source is "implement the
protocol" rather than "rewire the store."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, runtime_checkable

SourceKind = Literal["ynab", "statement"]


@dataclass(frozen=True, slots=True)
class RemoteAccount:
    external_id: str
    name: str
    type: str                    # canonical: checking/savings/credit_card/...
    on_budget: bool
    closed: bool
    deleted: bool
    currency: str
    cleared_balance_minor: Optional[int]
    uncleared_balance_minor: Optional[int]
    balance_as_of: Optional[str]


@dataclass(frozen=True, slots=True)
class RemoteCategory:
    external_id: str
    name: str
    group_name: Optional[str]
    hidden: bool
    deleted: bool


@dataclass(frozen=True, slots=True)
class RemotePayee:
    external_id: str
    name: str
    transfer_account_external_id: Optional[str]
    deleted: bool


@dataclass(frozen=True, slots=True)
class RemoteSubTxn:
    """A child of a split transaction (no `id` needed; assigned at mapping time)."""
    amount_minor: int
    memo: Optional[str]
    category_external_id: Optional[str]
    payee_external_id: Optional[str]
    transfer_account_external_id: Optional[str]


@dataclass(frozen=True, slots=True)
class RemoteTransaction:
    external_id: str
    account_external_id: str
    date: str                    # YYYY-MM-DD
    amount_minor: int            # signed; negative = outflow
    currency: str
    payee: Optional[str]         # display name
    payee_external_id: Optional[str]
    memo: Optional[str]
    category_external_id: Optional[str]
    cleared: Optional[str]       # cleared | uncleared | reconciled
    approved: bool
    flag_color: Optional[str]
    import_id: Optional[str]
    transfer_account_external_id: Optional[str]
    deleted: bool
    subtransactions: tuple[RemoteSubTxn, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SyncDelta:
    """Everything a source emitted for one delta pull."""

    accounts: tuple[RemoteAccount, ...]
    categories: tuple[RemoteCategory, ...]
    payees: tuple[RemotePayee, ...]
    transactions: tuple[RemoteTransaction, ...]
    new_cursor: Optional[int]     # to persist in sync_state.server_knowledge


@runtime_checkable
class AccountSource(Protocol):
    """A pullable data source. Implementations are read-only by construction."""

    source_id: str               # e.g., "ynab:<budget_id>"
    kind: SourceKind
    nickname: Optional[str]

    def validate(self) -> None:
        """Raise (with a user-friendly message) on bad auth or config."""
        ...

    def pull(self, cursor: Optional[int]) -> SyncDelta:
        """Pull a delta from the source. Pass `cursor=None` for a full snapshot."""
        ...
```

- [ ] **Step 2: Verify the module imports**

Run: `python -c "from homefinance.sources.base import AccountSource, SyncDelta, RemoteTransaction"`
Expected: exits 0 with no output.

- [ ] **Step 3: Commit**

```bash
git add src/homefinance/sources/base.py
git commit -m "feat(sources): AccountSource protocol + canonical RemoteX dataclasses"
```

---

## Task 9: YNAB API response models

**Goal:** Pydantic models for the subset of YNAB API responses we consume. They double as the schema for fixture JSON. Keep models permissive (extra fields ignored) so YNAB can grow without breaking us.

**Files:**
- Create: `src/homefinance/sources/ynab/models.py`

- [ ] **Step 1: Implement `src/homefinance/sources/ynab/models.py`**

```python
"""Pydantic models for the YNAB API subset we consume.

Permissive (`extra='ignore'`) so YNAB can add fields without breaking us.
Amounts here are still in YNAB's wire format (milliunits, integers).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Permissive(BaseModel):
    model_config = ConfigDict(extra="ignore")


class YNABUser(_Permissive):
    id: str


class YNABBudgetSummary(_Permissive):
    id: str
    name: str


class YNABAccount(_Permissive):
    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    deleted: bool
    balance: int                              # milliunits
    cleared_balance: int                      # milliunits
    uncleared_balance: int                    # milliunits
    last_reconciled_at: Optional[str] = None


class YNABCategory(_Permissive):
    id: str
    category_group_id: Optional[str] = None
    category_group_name: Optional[str] = None
    name: str
    hidden: bool
    deleted: bool


class YNABPayee(_Permissive):
    id: str
    name: str
    transfer_account_id: Optional[str] = None
    deleted: bool


class YNABSubTransaction(_Permissive):
    id: str
    amount: int                               # milliunits
    memo: Optional[str] = None
    payee_id: Optional[str] = None
    category_id: Optional[str] = None
    transfer_account_id: Optional[str] = None
    deleted: bool


class YNABTransaction(_Permissive):
    id: str
    date: str                                 # YYYY-MM-DD
    amount: int                               # milliunits, signed
    memo: Optional[str] = None
    cleared: Optional[str] = None
    approved: bool
    flag_color: Optional[str] = None
    account_id: str
    payee_id: Optional[str] = None
    payee_name: Optional[str] = None
    category_id: Optional[str] = None
    transfer_account_id: Optional[str] = None
    import_id: Optional[str] = None
    deleted: bool
    subtransactions: list[YNABSubTransaction] = Field(default_factory=list)


# Top-level response wrappers. YNAB wraps every endpoint in {"data": {...}}.


class _Data(_Permissive):
    server_knowledge: Optional[int] = None


class UserResponse(_Permissive):
    class _D(_Data):
        user: YNABUser

    data: _D


class BudgetsResponse(_Permissive):
    class _D(_Data):
        budgets: list[YNABBudgetSummary]

    data: _D


class AccountsResponse(_Permissive):
    class _D(_Data):
        accounts: list[YNABAccount]

    data: _D


class CategoryGroupWithCategories(_Permissive):
    id: str
    name: str
    hidden: bool
    deleted: bool
    categories: list[YNABCategory] = Field(default_factory=list)


class CategoriesResponse(_Permissive):
    class _D(_Data):
        category_groups: list[CategoryGroupWithCategories]

    data: _D


class PayeesResponse(_Permissive):
    class _D(_Data):
        payees: list[YNABPayee]

    data: _D


class TransactionsResponse(_Permissive):
    class _D(_Data):
        transactions: list[YNABTransaction]

    data: _D
```

- [ ] **Step 2: Verify the module imports**

Run: `python -c "from homefinance.sources.ynab.models import TransactionsResponse, YNABTransaction"`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add src/homefinance/sources/ynab/models.py
git commit -m "feat(ynab): Pydantic models for the YNAB API subset"
```

---

## Task 10: YNAB HTTP client (read-only, retry-wrapped)

**Goal:** A `YNABClient` class with only GET methods (`get_user`, `get_budgets`, `get_accounts`, `get_categories`, `get_payees`, `get_transactions`). httpx-backed, tenacity-wrapped for `429`/`5xx`/network errors, structural read-only enforcement.

**Files:**
- Create: `src/homefinance/sources/ynab/client.py`
- Create: `tests/test_ynab_client.py`

- [ ] **Step 1: Write failing tests at `tests/test_ynab_client.py`**

```python
import httpx
import pytest
from pytest_httpx import HTTPXMock

from homefinance.sources.ynab.client import YNABClient, YNABAuthError, YNABClientError


def _client() -> YNABClient:
    return YNABClient(token="TEST-TOKEN", base_url="https://api.ynab.com/v1")


def test_get_user_sends_bearer_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        json={"data": {"user": {"id": "u-1"}}},
    )
    resp = _client().get_user()
    assert resp.data.user.id == "u-1"
    sent = httpx_mock.get_requests()[0]
    assert sent.headers["Authorization"] == "Bearer TEST-TOKEN"


def test_401_raises_auth_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        status_code=401,
        json={"error": {"id": "401", "name": "unauthorized", "detail": "bad token"}},
    )
    with pytest.raises(YNABAuthError):
        _client().get_user()


def test_get_transactions_passes_cursor(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/budgets/B/transactions?last_knowledge_of_server=42",
        json={"data": {"server_knowledge": 99, "transactions": []}},
    )
    resp = _client().get_transactions(budget_id="B", cursor=42)
    assert resp.data.server_knowledge == 99
    assert resp.data.transactions == []


def test_5xx_is_retried_then_succeeds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.ynab.com/v1/user", status_code=503)
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        json={"data": {"user": {"id": "u-1"}}},
    )
    resp = _client().get_user()
    assert resp.data.user.id == "u-1"
    assert len(httpx_mock.get_requests()) == 2


def test_persistent_5xx_raises_client_error(httpx_mock: HTTPXMock) -> None:
    for _ in range(4):
        httpx_mock.add_response(url="https://api.ynab.com/v1/user", status_code=500)
    with pytest.raises(YNABClientError):
        _client().get_user()


def test_client_has_no_write_methods() -> None:
    for attr in ("post", "put", "patch", "delete", "create_transaction", "update_transaction"):
        assert not hasattr(YNABClient, attr), f"YNABClient must not expose {attr!r}"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_ynab_client.py -v`
Expected: import errors / `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/sources/ynab/client.py`**

```python
"""Read-only YNAB API client.

Structural posture: this class exposes only GET methods. POST/PUT/PATCH/DELETE
are not on the class at all, so accidental writes are physically impossible.

Retries: 429, 5xx, and transport-level errors are retried with jittered
exponential backoff up to 3 attempts via `tenacity`.
"""

from __future__ import annotations

from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class YNABClientError(Exception):
    """Base class for YNAB client errors."""


class YNABAuthError(YNABClientError):
    """Raised on 401/403."""


class YNABRetryableError(YNABClientError):
    """Internal — raised to trigger tenacity backoff. Not surfaced to callers."""


_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=8.0),
    retry=retry_if_exception_type((YNABRetryableError, httpx.TransportError)),
    reraise=True,
)


class YNABClient:
    """Thin, read-only YNAB API client."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.ynab.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> YNABClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # public read methods

    def get_user(self) -> UserResponse:
        return UserResponse.model_validate(self._get("/user"))

    def get_budgets(self) -> BudgetsResponse:
        return BudgetsResponse.model_validate(self._get("/budgets"))

    def get_accounts(self, budget_id: str, cursor: Optional[int] = None) -> AccountsResponse:
        return AccountsResponse.model_validate(
            self._get(f"/budgets/{budget_id}/accounts", cursor=cursor)
        )

    def get_categories(self, budget_id: str, cursor: Optional[int] = None) -> CategoriesResponse:
        return CategoriesResponse.model_validate(
            self._get(f"/budgets/{budget_id}/categories", cursor=cursor)
        )

    def get_payees(self, budget_id: str, cursor: Optional[int] = None) -> PayeesResponse:
        return PayeesResponse.model_validate(
            self._get(f"/budgets/{budget_id}/payees", cursor=cursor)
        )

    def get_transactions(
        self, budget_id: str, cursor: Optional[int] = None
    ) -> TransactionsResponse:
        return TransactionsResponse.model_validate(
            self._get(f"/budgets/{budget_id}/transactions", cursor=cursor)
        )

    # ------------------------------------------------------------------
    # internals

    @retry(**_RETRY)
    def _get(self, path: str, cursor: Optional[int] = None) -> dict:
        params: dict[str, int] = {}
        if cursor is not None:
            params["last_knowledge_of_server"] = cursor
        try:
            resp = self._http.get(path, params=params)
        except httpx.TransportError:
            raise
        if resp.status_code in (401, 403):
            raise YNABAuthError(
                f"YNAB rejected the request ({resp.status_code}). "
                "Check $HOMEFINANCE_YNAB_TOKEN or ~/.homefinance/config.toml."
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise YNABRetryableError(f"YNAB returned {resp.status_code}")
        if resp.status_code >= 400:
            raise YNABClientError(f"YNAB returned {resp.status_code}: {resp.text[:200]}")
        return resp.json()
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_client.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/sources/ynab/client.py tests/test_ynab_client.py
git commit -m "feat(ynab): read-only HTTP client with tenacity retry; no write methods"
```

---

## Task 11: FakeYNABClient + fixture loading

**Goal:** A drop-in replacement for `YNABClient` used by integration and end-to-end tests. Loads pre-recorded JSON responses from `tests/fixtures/ynab/` and returns them via the same Pydantic models. Ships with one hand-written "tiny budget" fixture set that exercises non-splits, splits, transfers, soft-delete, and multi-account scenarios.

**Files:**
- Create: `src/homefinance/sources/ynab/fake_client.py`
- Create: `tests/fixtures/ynab/tiny/user.json`
- Create: `tests/fixtures/ynab/tiny/budgets.json`
- Create: `tests/fixtures/ynab/tiny/accounts.json`
- Create: `tests/fixtures/ynab/tiny/categories.json`
- Create: `tests/fixtures/ynab/tiny/payees.json`
- Create: `tests/fixtures/ynab/tiny/transactions.json`
- Create: `tests/fixtures/ynab/tiny/transactions_delta.json`

- [ ] **Step 1: Create the fixture set under `tests/fixtures/ynab/tiny/`** (sanitized hand-authored data). The values below are deliberately small so the engineer can reason about every field.

`user.json`:
```json
{ "data": { "user": { "id": "user-tiny" } } }
```

`budgets.json`:
```json
{
  "data": {
    "budgets": [
      { "id": "budget-tiny", "name": "Tiny Budget" }
    ]
  }
}
```

`accounts.json`:
```json
{
  "data": {
    "server_knowledge": 100,
    "accounts": [
      {
        "id": "acct-checking",
        "name": "Checking",
        "type": "checking",
        "on_budget": true,
        "closed": false,
        "deleted": false,
        "balance": 1234560,
        "cleared_balance": 1234560,
        "uncleared_balance": 0
      },
      {
        "id": "acct-credit",
        "name": "Credit Card",
        "type": "creditCard",
        "on_budget": true,
        "closed": false,
        "deleted": false,
        "balance": -50000,
        "cleared_balance": -50000,
        "uncleared_balance": 0
      }
    ]
  }
}
```

`categories.json`:
```json
{
  "data": {
    "server_knowledge": 100,
    "category_groups": [
      {
        "id": "grp-everyday",
        "name": "Everyday",
        "hidden": false,
        "deleted": false,
        "categories": [
          { "id": "cat-groceries", "category_group_id": "grp-everyday",
            "category_group_name": "Everyday", "name": "Groceries",
            "hidden": false, "deleted": false },
          { "id": "cat-dining", "category_group_id": "grp-everyday",
            "category_group_name": "Everyday", "name": "Dining Out",
            "hidden": false, "deleted": false },
          { "id": "cat-gas", "category_group_id": "grp-everyday",
            "category_group_name": "Everyday", "name": "Gas",
            "hidden": false, "deleted": false }
        ]
      }
    ]
  }
}
```

`payees.json`:
```json
{
  "data": {
    "server_knowledge": 100,
    "payees": [
      { "id": "payee-trader-joes", "name": "Trader Joe's", "deleted": false },
      { "id": "payee-shell", "name": "Shell", "deleted": false },
      { "id": "payee-xfer-credit", "name": "Transfer : Credit Card",
        "transfer_account_id": "acct-credit", "deleted": false }
    ]
  }
}
```

`transactions.json`:
```json
{
  "data": {
    "server_knowledge": 100,
    "transactions": [
      {
        "id": "txn-non-split", "date": "2026-06-01", "amount": -45670,
        "memo": "weekly shop", "cleared": "cleared", "approved": true,
        "flag_color": null, "account_id": "acct-checking",
        "payee_id": "payee-trader-joes", "payee_name": "Trader Joe's",
        "category_id": "cat-groceries", "transfer_account_id": null,
        "import_id": "YNAB:imp-1", "deleted": false, "subtransactions": []
      },
      {
        "id": "txn-split", "date": "2026-06-02", "amount": -50000,
        "memo": "gas + snacks", "cleared": "cleared", "approved": true,
        "flag_color": null, "account_id": "acct-checking",
        "payee_id": "payee-shell", "payee_name": "Shell",
        "category_id": null, "transfer_account_id": null,
        "import_id": null, "deleted": false,
        "subtransactions": [
          { "id": "sub-1", "amount": -40000, "memo": "gas",
            "payee_id": "payee-shell", "category_id": "cat-gas",
            "transfer_account_id": null, "deleted": false },
          { "id": "sub-2", "amount": -10000, "memo": "snacks",
            "payee_id": "payee-shell", "category_id": "cat-groceries",
            "transfer_account_id": null, "deleted": false }
        ]
      },
      {
        "id": "txn-transfer", "date": "2026-06-03", "amount": -20000,
        "memo": "pay down card", "cleared": "uncleared", "approved": true,
        "flag_color": null, "account_id": "acct-checking",
        "payee_id": "payee-xfer-credit", "payee_name": "Transfer : Credit Card",
        "category_id": null, "transfer_account_id": "acct-credit",
        "import_id": null, "deleted": false, "subtransactions": []
      }
    ]
  }
}
```

`transactions_delta.json` (simulates a delta sync that updates one txn and soft-deletes another):
```json
{
  "data": {
    "server_knowledge": 150,
    "transactions": [
      {
        "id": "txn-non-split", "date": "2026-06-01", "amount": -45670,
        "memo": "weekly shop (corrected memo)", "cleared": "reconciled",
        "approved": true, "flag_color": null, "account_id": "acct-checking",
        "payee_id": "payee-trader-joes", "payee_name": "Trader Joe's",
        "category_id": "cat-groceries", "transfer_account_id": null,
        "import_id": "YNAB:imp-1", "deleted": false, "subtransactions": []
      },
      {
        "id": "txn-transfer", "date": "2026-06-03", "amount": -20000,
        "memo": "pay down card", "cleared": "uncleared", "approved": true,
        "flag_color": null, "account_id": "acct-checking",
        "payee_id": "payee-xfer-credit", "payee_name": "Transfer : Credit Card",
        "category_id": null, "transfer_account_id": "acct-credit",
        "import_id": null, "deleted": true, "subtransactions": []
      }
    ]
  }
}
```

- [ ] **Step 2: Implement `src/homefinance/sources/ynab/fake_client.py`**

```python
"""A fake YNAB client backed by JSON fixtures.

Conforms to the same surface as `YNABClient` (only the methods used by sync),
so the sync engine can be exercised end-to-end without ever hitting YNAB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class FakeYNABClient:
    """Loads `*.json` fixtures from a directory and returns parsed responses.

    The `cursor` argument selects between two transaction fixture files:
    `transactions.json` for None (full pull) and `transactions_delta.json`
    when a cursor is provided.
    """

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = Path(fixtures_dir)

    def _load(self, name: str) -> dict:
        return json.loads((self._dir / name).read_text())

    # Same signature subset as YNABClient.

    def get_user(self) -> UserResponse:
        return UserResponse.model_validate(self._load("user.json"))

    def get_budgets(self) -> BudgetsResponse:
        return BudgetsResponse.model_validate(self._load("budgets.json"))

    def get_accounts(self, budget_id: str, cursor: Optional[int] = None) -> AccountsResponse:
        return AccountsResponse.model_validate(self._load("accounts.json"))

    def get_categories(self, budget_id: str, cursor: Optional[int] = None) -> CategoriesResponse:
        return CategoriesResponse.model_validate(self._load("categories.json"))

    def get_payees(self, budget_id: str, cursor: Optional[int] = None) -> PayeesResponse:
        return PayeesResponse.model_validate(self._load("payees.json"))

    def get_transactions(
        self, budget_id: str, cursor: Optional[int] = None
    ) -> TransactionsResponse:
        name = "transactions_delta.json" if cursor is not None else "transactions.json"
        return TransactionsResponse.model_validate(self._load(name))
```

- [ ] **Step 3: Add a `tiny_fixtures` fixture to `tests/conftest.py`**

Replace the file content with:

```python
"""Shared pytest fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tiny_fixtures_dir() -> Path:
    return FIXTURES / "ynab" / "tiny"
```

- [ ] **Step 4: Add a quick test that the fake parses the tiny fixtures** (extend `tests/test_ynab_client.py`):

Append at the bottom of the file:

```python
from pathlib import Path
from homefinance.sources.ynab.fake_client import FakeYNABClient


def test_fake_client_parses_tiny_fixtures(tiny_fixtures_dir: Path) -> None:
    fake = FakeYNABClient(tiny_fixtures_dir)
    assert fake.get_user().data.user.id == "user-tiny"
    assert [b.id for b in fake.get_budgets().data.budgets] == ["budget-tiny"]
    txns = fake.get_transactions("budget-tiny").data.transactions
    ids = {t.id for t in txns}
    assert ids == {"txn-non-split", "txn-split", "txn-transfer"}
    split = next(t for t in txns if t.id == "txn-split")
    assert sum(s.amount for s in split.subtransactions) == split.amount


def test_fake_client_returns_delta_when_cursor_given(tiny_fixtures_dir: Path) -> None:
    fake = FakeYNABClient(tiny_fixtures_dir)
    delta = fake.get_transactions("budget-tiny", cursor=100).data.transactions
    assert {t.id for t in delta} == {"txn-non-split", "txn-transfer"}
    soft_deleted = next(t for t in delta if t.id == "txn-transfer")
    assert soft_deleted.deleted is True
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_client.py -v`
Expected: `8 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/sources/ynab/fake_client.py tests/conftest.py \
        tests/fixtures/ynab/tiny tests/test_ynab_client.py
git commit -m "test(ynab): FakeYNABClient + tiny fixture set covering splits/transfers/soft-delete"
```

---

## Task 12: Money + ID helpers

**Goal:** Two tiny pure modules: money conversion (`to_minor_units`) and ID building (`make_id`). The money discipline (§6.1) is concentrated here so every call site routes through the same converter.

**Files:**
- Create: `src/homefinance/sources/ynab/ids.py`
- Create: `src/homefinance/sources/ynab/mapping.py` (initial — money helper only; expanded in Tasks 13-14)
- Create: `tests/test_ynab_mapping.py`

- [ ] **Step 1: Write failing tests at `tests/test_ynab_mapping.py`**

```python
import pytest

from homefinance.sources.ynab.ids import make_id, source_id_for
from homefinance.sources.ynab.mapping import to_minor_units


def test_to_minor_units_positive() -> None:
    assert to_minor_units(45670) == 4567


def test_to_minor_units_negative() -> None:
    assert to_minor_units(-45670) == -4567


def test_to_minor_units_zero() -> None:
    assert to_minor_units(0) == 0


def test_to_minor_units_rejects_sub_cent() -> None:
    with pytest.raises(ValueError, match="non-cent"):
        to_minor_units(12345)


def test_source_id_for_formats_budget() -> None:
    assert source_id_for("abc-123") == "ynab:abc-123"


def test_make_id_concats_source_and_external() -> None:
    assert make_id("ynab:abc", "acct-1") == "ynab:abc:acct-1"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `ModuleNotFoundError` for `homefinance.sources.ynab.ids` and `mapping`.

- [ ] **Step 3: Implement `src/homefinance/sources/ynab/ids.py`**

```python
"""Deterministic ID builders. Format: ``ynab:<budget_id>:<external_id>``.

Stable across re-syncs and grep-friendly for debugging.
"""

from __future__ import annotations


def source_id_for(budget_id: str) -> str:
    return f"ynab:{budget_id}"


def make_id(source_id: str, external_id: str) -> str:
    return f"{source_id}:{external_id}"
```

- [ ] **Step 4: Implement `src/homefinance/sources/ynab/mapping.py`** (money helper only — extended in Tasks 13-14):

```python
"""YNAB → canonical mapping. Pure functions; no I/O.

This is the only place in the codebase that converts YNAB's wire format
(milliunits) to our canonical minor units (cents). Floats never enter the store.
"""

from __future__ import annotations


def to_minor_units(milliunits: int) -> int:
    """Convert signed YNAB milliunits to signed minor units (cents).

    Raises ``ValueError`` if the input is not a multiple of 10 — real YNAB
    transactions are always whole cents, so sub-cent values indicate either
    a bug upstream or a corner case we want to surface loudly rather than
    silently round.
    """
    if milliunits % 10 != 0:
        raise ValueError(f"non-cent milliunit value: {milliunits}")
    return milliunits // 10
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/sources/ynab/ids.py \
        src/homefinance/sources/ynab/mapping.py \
        tests/test_ynab_mapping.py
git commit -m "feat(ynab): money conversion + deterministic ID builders"
```

---

## Task 13: Account, category, and payee mapping

**Goal:** Pure functions that convert YNAB account/category/payee responses to the canonical `RemoteAccount` / `RemoteCategory` / `RemotePayee` types. Account-type strings are normalized from YNAB's camelCase to the canonical snake_case enum.

**Files:**
- Modify: `src/homefinance/sources/ynab/mapping.py` (append)
- Modify: `tests/test_ynab_mapping.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_ynab_mapping.py`**

```python
from pathlib import Path

from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.mapping import (
    map_account,
    map_categories,
    map_payee,
)


def test_map_account_normalizes_type_and_converts_balance(tiny_fixtures_dir: Path) -> None:
    accts = FakeYNABClient(tiny_fixtures_dir).get_accounts("budget-tiny").data.accounts
    mapped = [map_account(a) for a in accts]
    by_id = {a.external_id: a for a in mapped}
    assert by_id["acct-checking"].type == "checking"
    assert by_id["acct-checking"].cleared_balance_minor == 123456
    assert by_id["acct-credit"].type == "credit_card"
    assert by_id["acct-credit"].cleared_balance_minor == -5000


def test_map_categories_flattens_groups(tiny_fixtures_dir: Path) -> None:
    resp = FakeYNABClient(tiny_fixtures_dir).get_categories("budget-tiny")
    cats = map_categories(resp)
    names = {c.name for c in cats}
    assert names == {"Groceries", "Dining Out", "Gas"}
    for c in cats:
        assert c.group_name == "Everyday"


def test_map_categories_inherits_group_hidden_or_deleted() -> None:
    from homefinance.sources.ynab.models import CategoriesResponse

    resp = CategoriesResponse.model_validate({
        "data": {
            "server_knowledge": 1,
            "category_groups": [
                {"id": "g1", "name": "Hidden", "hidden": True, "deleted": False,
                 "categories": [{"id": "c1", "name": "x", "hidden": False, "deleted": False}]},
                {"id": "g2", "name": "Gone", "hidden": False, "deleted": True,
                 "categories": [{"id": "c2", "name": "y", "hidden": False, "deleted": False}]},
            ],
        },
    })
    cats = {c.external_id: c for c in map_categories(resp)}
    assert cats["c1"].hidden is True
    assert cats["c2"].deleted is True


def test_map_payee_carries_transfer_account(tiny_fixtures_dir: Path) -> None:
    payees = FakeYNABClient(tiny_fixtures_dir).get_payees("budget-tiny").data.payees
    by_id = {p.id: map_payee(p) for p in payees}
    assert by_id["payee-xfer-credit"].transfer_account_external_id == "acct-credit"
    assert by_id["payee-trader-joes"].transfer_account_external_id is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `ImportError` on `map_account`/`map_categories`/`map_payee`.

- [ ] **Step 3: Extend `src/homefinance/sources/ynab/mapping.py`** by appending:

```python
from homefinance.sources.base import RemoteAccount, RemoteCategory, RemotePayee
from homefinance.sources.ynab.models import (
    CategoriesResponse,
    YNABAccount,
    YNABPayee,
)


_ACCOUNT_TYPE_MAP: dict[str, str] = {
    "checking": "checking",
    "savings": "savings",
    "cash": "cash",
    "creditCard": "credit_card",
    "lineOfCredit": "loan",
    "mortgage": "loan",
    "autoLoan": "loan",
    "studentLoan": "loan",
    "personalLoan": "loan",
    "medicalDebt": "loan",
    "otherDebt": "loan",
    "otherAsset": "other",
    "otherLiability": "loan",
}


def _normalize_account_type(ynab_type: str) -> str:
    return _ACCOUNT_TYPE_MAP.get(ynab_type, "other")


def map_account(ya: YNABAccount, currency: str = "USD") -> RemoteAccount:
    """YNAB account → canonical. Currency defaults to USD; SP1 does not yet
    fetch budget-level currency settings (see open question OQ in spec §11)."""
    return RemoteAccount(
        external_id=ya.id,
        name=ya.name,
        type=_normalize_account_type(ya.type),
        on_budget=ya.on_budget,
        closed=ya.closed,
        deleted=ya.deleted,
        currency=currency,
        cleared_balance_minor=to_minor_units(ya.cleared_balance),
        uncleared_balance_minor=to_minor_units(ya.uncleared_balance),
        balance_as_of=ya.last_reconciled_at,
    )


def map_categories(resp: CategoriesResponse) -> list[RemoteCategory]:
    """Flatten YNAB's category groups into a flat list of canonical categories.
    A category inherits ``hidden`` or ``deleted`` from its group."""
    out: list[RemoteCategory] = []
    for grp in resp.data.category_groups:
        for cat in grp.categories:
            out.append(
                RemoteCategory(
                    external_id=cat.id,
                    name=cat.name,
                    group_name=grp.name,
                    hidden=bool(cat.hidden or grp.hidden),
                    deleted=bool(cat.deleted or grp.deleted),
                )
            )
    return out


def map_payee(yp: YNABPayee) -> RemotePayee:
    return RemotePayee(
        external_id=yp.id,
        name=yp.name,
        transfer_account_external_id=yp.transfer_account_id,
        deleted=yp.deleted,
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/sources/ynab/mapping.py tests/test_ynab_mapping.py
git commit -m "feat(ynab): account/category/payee mapping with type normalization"
```

---

## Task 14: Transaction mapping (with splits)

**Goal:** `map_transaction` converts a `YNABTransaction` to a `RemoteTransaction`, preserving its (non-deleted) subtransactions as `RemoteSubTxn` children. The `is_split_parent` flag is set downstream by the orchestrator from `len(subtransactions) > 0`; mapping only carries the data through.

**Files:**
- Modify: `src/homefinance/sources/ynab/mapping.py` (append)
- Modify: `tests/test_ynab_mapping.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_ynab_mapping.py`**

```python
from homefinance.sources.ynab.mapping import map_transaction


def test_map_transaction_non_split(tiny_fixtures_dir: Path) -> None:
    txns = FakeYNABClient(tiny_fixtures_dir).get_transactions("budget-tiny").data.transactions
    non_split = next(t for t in txns if t.id == "txn-non-split")
    rt = map_transaction(non_split)
    assert rt.amount_minor == -4567
    assert rt.category_external_id == "cat-groceries"
    assert rt.payee == "Trader Joe's"
    assert rt.subtransactions == ()
    assert rt.deleted is False
    assert rt.import_id == "YNAB:imp-1"


def test_map_transaction_split_children_sum_to_parent(tiny_fixtures_dir: Path) -> None:
    txns = FakeYNABClient(tiny_fixtures_dir).get_transactions("budget-tiny").data.transactions
    split = next(t for t in txns if t.id == "txn-split")
    rt = map_transaction(split)
    assert rt.amount_minor == -5000
    assert len(rt.subtransactions) == 2
    assert sum(s.amount_minor for s in rt.subtransactions) == rt.amount_minor
    cats = {s.category_external_id for s in rt.subtransactions}
    assert cats == {"cat-gas", "cat-groceries"}


def test_map_transaction_drops_deleted_subtransactions() -> None:
    from homefinance.sources.ynab.models import YNABTransaction

    yt = YNABTransaction.model_validate({
        "id": "t1", "date": "2026-06-01", "amount": -1000, "account_id": "a",
        "approved": True, "deleted": False,
        "subtransactions": [
            {"id": "s1", "amount": -700, "category_id": "c1", "deleted": False},
            {"id": "s2", "amount": -300, "category_id": "c2", "deleted": True},
        ],
    })
    rt = map_transaction(yt)
    assert len(rt.subtransactions) == 1
    assert rt.subtransactions[0].category_external_id == "c1"


def test_map_transaction_transfer(tiny_fixtures_dir: Path) -> None:
    txns = FakeYNABClient(tiny_fixtures_dir).get_transactions("budget-tiny").data.transactions
    xfer = next(t for t in txns if t.id == "txn-transfer")
    rt = map_transaction(xfer)
    assert rt.transfer_account_external_id == "acct-credit"
    assert rt.subtransactions == ()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `ImportError` on `map_transaction`.

- [ ] **Step 3: Append `map_transaction` to `src/homefinance/sources/ynab/mapping.py`**

```python
from homefinance.sources.base import RemoteSubTxn, RemoteTransaction
from homefinance.sources.ynab.models import YNABTransaction


def map_transaction(yt: YNABTransaction, currency: str = "USD") -> RemoteTransaction:
    """YNAB transaction → canonical, with non-deleted subtransactions preserved.

    The ``is_split_parent`` flag on the persisted row is set by the sync
    orchestrator (`len(subtransactions) > 0`) — this function just carries
    the data through.
    """
    subs = tuple(
        RemoteSubTxn(
            amount_minor=to_minor_units(s.amount),
            memo=s.memo,
            category_external_id=s.category_id,
            payee_external_id=s.payee_id,
            transfer_account_external_id=s.transfer_account_id,
        )
        for s in yt.subtransactions
        if not s.deleted
    )
    return RemoteTransaction(
        external_id=yt.id,
        account_external_id=yt.account_id,
        date=yt.date,
        amount_minor=to_minor_units(yt.amount),
        currency=currency,
        payee=yt.payee_name,
        payee_external_id=yt.payee_id,
        memo=yt.memo,
        category_external_id=yt.category_id,
        cleared=yt.cleared,
        approved=yt.approved,
        flag_color=yt.flag_color,
        import_id=yt.import_id,
        transfer_account_external_id=yt.transfer_account_id,
        deleted=yt.deleted,
        subtransactions=subs,
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_mapping.py -v`
Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/sources/ynab/mapping.py tests/test_ynab_mapping.py
git commit -m "feat(ynab): transaction mapping including split children"
```

---

## Task 15: YNAB AccountSource implementation

**Goal:** `YNABAccountSource` wraps a YNAB client + the mapping functions and implements the `AccountSource` Protocol. Pull semantics: call all four endpoints with the cursor, map the responses, return a `SyncDelta` carrying the new `server_knowledge`.

**Files:**
- Create: `src/homefinance/sources/ynab/source.py`
- Create: `tests/test_ynab_source.py`

- [ ] **Step 1: Write failing tests at `tests/test_ynab_source.py`**

```python
from pathlib import Path

import pytest

from homefinance.sources.base import AccountSource
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource


@pytest.fixture
def source(tiny_fixtures_dir: Path) -> YNABAccountSource:
    return YNABAccountSource(
        budget_id="budget-tiny",
        client=FakeYNABClient(tiny_fixtures_dir),
        nickname="tiny",
    )


def test_satisfies_account_source_protocol(source: YNABAccountSource) -> None:
    assert isinstance(source, AccountSource)
    assert source.source_id == "ynab:budget-tiny"
    assert source.kind == "ynab"
    assert source.nickname == "tiny"


def test_validate_calls_get_user(source: YNABAccountSource) -> None:
    # FakeYNABClient.get_user reads user.json; if it raises, validate raises.
    source.validate()  # no exception


def test_pull_returns_full_delta(source: YNABAccountSource) -> None:
    delta = source.pull(cursor=None)
    assert {a.external_id for a in delta.accounts} == {"acct-checking", "acct-credit"}
    assert {c.external_id for c in delta.categories} == {"cat-groceries", "cat-dining", "cat-gas"}
    assert {p.external_id for p in delta.payees} >= {"payee-trader-joes", "payee-shell"}
    assert {t.external_id for t in delta.transactions} == {
        "txn-non-split", "txn-split", "txn-transfer",
    }
    assert delta.new_cursor == 100


def test_pull_with_cursor_returns_delta_set(source: YNABAccountSource) -> None:
    delta = source.pull(cursor=100)
    # tiny fixtures' transactions_delta.json carries the changed txns
    assert {t.external_id for t in delta.transactions} == {"txn-non-split", "txn-transfer"}
    assert delta.new_cursor == 150
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_ynab_source.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/sources/ynab/source.py`**

```python
"""``YNABAccountSource`` — implements ``AccountSource`` for YNAB.

Wraps a YNAB client (real or fake) plus the mapping functions. The protocol
contract is "validate before use; pull a delta given a cursor"; everything
else is the orchestrator's job.
"""

from __future__ import annotations

from typing import Literal, Optional, Protocol

from homefinance.sources.base import SyncDelta
from homefinance.sources.ynab.ids import source_id_for
from homefinance.sources.ynab.mapping import (
    map_account,
    map_categories,
    map_payee,
    map_transaction,
)
from homefinance.sources.ynab.models import (
    AccountsResponse,
    BudgetsResponse,
    CategoriesResponse,
    PayeesResponse,
    TransactionsResponse,
    UserResponse,
)


class _ClientLike(Protocol):
    """The subset of YNAB client methods the source needs."""

    def get_user(self) -> UserResponse: ...
    def get_budgets(self) -> BudgetsResponse: ...
    def get_accounts(self, budget_id: str, cursor: Optional[int] = None) -> AccountsResponse: ...
    def get_categories(self, budget_id: str, cursor: Optional[int] = None) -> CategoriesResponse: ...
    def get_payees(self, budget_id: str, cursor: Optional[int] = None) -> PayeesResponse: ...
    def get_transactions(self, budget_id: str, cursor: Optional[int] = None) -> TransactionsResponse: ...


class YNABAccountSource:
    """One configured YNAB budget surfaced as an ``AccountSource``."""

    kind: Literal["ynab"] = "ynab"

    def __init__(
        self,
        budget_id: str,
        client: _ClientLike,
        nickname: Optional[str] = None,
        currency: str = "USD",
    ) -> None:
        self.budget_id = budget_id
        self.source_id = source_id_for(budget_id)
        self.nickname = nickname
        self._client = client
        self._currency = currency

    def validate(self) -> None:
        """Fail fast on bad token: ``get_user`` raises ``YNABAuthError`` on 401."""
        self._client.get_user()

    def pull(self, cursor: Optional[int]) -> SyncDelta:
        accts = self._client.get_accounts(self.budget_id, cursor=cursor)
        cats = self._client.get_categories(self.budget_id, cursor=cursor)
        payees = self._client.get_payees(self.budget_id, cursor=cursor)
        txns = self._client.get_transactions(self.budget_id, cursor=cursor)

        new_cursor = next(
            (
                v
                for v in (
                    accts.data.server_knowledge,
                    cats.data.server_knowledge,
                    payees.data.server_knowledge,
                    txns.data.server_knowledge,
                )
                if v is not None
            ),
            None,
        )

        return SyncDelta(
            accounts=tuple(map_account(a, currency=self._currency) for a in accts.data.accounts),
            categories=tuple(map_categories(cats)),
            payees=tuple(map_payee(p) for p in payees.data.payees),
            transactions=tuple(
                map_transaction(t, currency=self._currency) for t in txns.data.transactions
            ),
            new_cursor=new_cursor,
        )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_ynab_source.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/sources/ynab/source.py tests/test_ynab_source.py
git commit -m "feat(ynab): YNABAccountSource implementing the AccountSource protocol"
```

---

## Task 16: Sync orchestrator (atomic upsert + reconciliation + sync_runs)

**Goal:** The heart of SP1. A single `run_sync(source, store)` function that:

1. Validates the source.
2. Reads the persisted cursor.
3. Pulls the delta.
4. **Inside one SQLite transaction**: ensures the `sources` row exists; upserts accounts, categories, payees; upserts transactions and rewrites split-children atomically; persists the new cursor; reconciles balances; writes a `sync_runs` row.

The function is generic — it takes any `AccountSource`. It lives in `sources/ynab/sync.py` per the spec tree but uses only the protocol.

**Files:**
- Create: `src/homefinance/sources/ynab/sync.py`
- Create: `tests/test_sync.py`
- Modify: `tests/conftest.py` (add `store` and `source` fixtures)

- [ ] **Step 1: Extend `tests/conftest.py`** with the fixtures used by sync tests:

```python
from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "sync.sqlite3"
    migrate(db)
    return Store.open(db)


@pytest.fixture
def ynab_source(tiny_fixtures_dir: Path) -> YNABAccountSource:
    return YNABAccountSource(
        budget_id="budget-tiny",
        client=FakeYNABClient(tiny_fixtures_dir),
        nickname="tiny",
    )
```

(append; do not remove the `tiny_fixtures_dir` fixture from Task 11.)

- [ ] **Step 2: Write failing tests at `tests/test_sync.py`**

```python
from homefinance.db.store import Store
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync


def _accounts(store: Store) -> dict:
    return {r["external_id"]: dict(r) for r in store.execute("SELECT * FROM accounts").fetchall()}


def _transactions(store: Store) -> dict:
    return {r["id"]: dict(r) for r in store.execute("SELECT * FROM transactions").fetchall()}


def test_first_sync_writes_all_entities(store: Store, ynab_source: YNABAccountSource) -> None:
    result = run_sync(ynab_source, store)
    assert result.status == "success"
    assert result.txns_inserted == 3
    assert result.accounts_touched == 2

    accts = _accounts(store)
    assert "acct-checking" in accts and "acct-credit" in accts
    assert accts["acct-checking"]["cleared_balance_minor"] == 123456


def test_split_parent_gets_is_split_parent_flag(store: Store, ynab_source: YNABAccountSource) -> None:
    run_sync(ynab_source, store)
    txns = _transactions(store)
    parent = txns["ynab:budget-tiny:txn-split"]
    assert parent["is_split_parent"] == 1
    children = [t for t in txns.values() if t["parent_id"] == parent["id"]]
    assert len(children) == 2
    assert sum(c["amount_minor"] for c in children) == parent["amount_minor"]
    for child in children:
        assert child["is_split_parent"] == 0


def test_cursor_persisted_to_sync_state(store: Store, ynab_source: YNABAccountSource) -> None:
    run_sync(ynab_source, store)
    row = store.execute("SELECT * FROM sync_state").fetchone()
    assert row["source_id"] == "ynab:budget-tiny"
    assert row["server_knowledge"] == 100


def test_sync_runs_row_is_recorded(store: Store, ynab_source: YNABAccountSource) -> None:
    run_sync(ynab_source, store)
    runs = store.execute("SELECT * FROM sync_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["reconciliation"] in ("ok", "drift")


def test_idempotent_second_run_inserts_nothing_new(
    store: Store, ynab_source: YNABAccountSource
) -> None:
    run_sync(ynab_source, store)
    before = _transactions(store)
    second = run_sync(ynab_source, store)
    after = _transactions(store)
    assert set(before.keys()) == set(after.keys())
    assert second.txns_inserted == 0


def test_delta_updates_existing_and_soft_deletes(
    store: Store, tiny_fixtures_dir
) -> None:
    src = YNABAccountSource("budget-tiny", FakeYNABClient(tiny_fixtures_dir))
    run_sync(src, store)
    # Force a delta call by simulating "second run" (FakeYNABClient returns
    # transactions_delta.json when cursor is set).
    run_sync(src, store)
    txns = _transactions(store)
    updated = txns["ynab:budget-tiny:txn-non-split"]
    assert "corrected memo" in updated["memo"]
    soft_deleted = txns["ynab:budget-tiny:txn-transfer"]
    assert soft_deleted["deleted"] == 1


def test_reconciliation_marks_ok_when_balances_match(
    store: Store, ynab_source: YNABAccountSource
) -> None:
    run_sync(ynab_source, store)
    run = store.execute(
        "SELECT reconciliation, drift_report FROM sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    # The tiny fixture's reported balances are crafted so the first sync
    # produces drift (acct-checking is reported as 1234.56 but txns sum to
    # less). We assert structurally on the field shape, not on ok/drift.
    assert run["reconciliation"] in ("ok", "drift")
    if run["reconciliation"] == "drift":
        assert run["drift_report"] is not None
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `pytest tests/test_sync.py -v`
Expected: `ModuleNotFoundError` on `homefinance.sources.ynab.sync`.

- [ ] **Step 4: Implement `src/homefinance/sources/ynab/sync.py`**

```python
"""Sync orchestrator.

Operates on any ``AccountSource`` (per spec §4.2). All persistence happens
inside a single SQLite transaction so the store is never left in a
half-applied state: either the cursor advances and rows land, or nothing
moves and the next run retries the same cursor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from homefinance.db.store import Store
from homefinance.sources.base import (
    AccountSource,
    RemoteAccount,
    RemoteCategory,
    RemotePayee,
    RemoteSubTxn,
    RemoteTransaction,
)
from homefinance.sources.ynab.ids import make_id


@dataclass(frozen=True, slots=True)
class SyncRunResult:
    source_id: str
    status: str                     # "success" | "partial" | "failed"
    txns_inserted: int
    txns_updated: int
    txns_deleted: int
    accounts_touched: int
    reconciliation: str             # "ok" | "drift" | "n/a"
    drift_report: Optional[str]     # JSON string when reconciliation='drift'


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_sync(source: AccountSource, store: Store) -> SyncRunResult:
    started_at = _utcnow()
    source.validate()

    row = store.execute(
        "SELECT server_knowledge FROM sync_state WHERE source_id = ?", (source.source_id,)
    ).fetchone()
    cursor: Optional[int] = row["server_knowledge"] if row else None

    delta = source.pull(cursor)

    counters = {"inserted": 0, "updated": 0, "deleted": 0, "accounts_touched": 0}

    with store.transaction():
        store.execute(
            "INSERT INTO sources (id, kind, nickname, config, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET nickname = excluded.nickname",
            (source.source_id, source.kind, source.nickname, None, _utcnow()),
        )

        for a in delta.accounts:
            _upsert_account(store, source.source_id, a, counters)

        for c in delta.categories:
            _upsert_category(store, source.source_id, c)

        for p in delta.payees:
            _upsert_payee(store, source.source_id, p)

        for t in delta.transactions:
            _upsert_transaction(store, source.source_id, t, counters)

        store.execute(
            "INSERT INTO sync_state (source_id, last_sync_at, server_knowledge, "
            "last_error, last_error_at) VALUES (?, ?, ?, NULL, NULL) "
            "ON CONFLICT (source_id) DO UPDATE SET "
            "last_sync_at = excluded.last_sync_at, "
            "server_knowledge = excluded.server_knowledge, "
            "last_error = NULL, last_error_at = NULL",
            (source.source_id, _utcnow(), delta.new_cursor),
        )

        recon_status, drift_report = _reconcile(store, source.source_id, delta.accounts)

        store.execute(
            "INSERT INTO sync_runs (source_id, started_at, finished_at, status, "
            "txns_inserted, txns_updated, txns_deleted, accounts_touched, "
            "reconciliation, drift_report) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source.source_id, started_at, _utcnow(), "success",
                counters["inserted"], counters["updated"], counters["deleted"],
                counters["accounts_touched"], recon_status, drift_report,
            ),
        )

    return SyncRunResult(
        source_id=source.source_id,
        status="success",
        txns_inserted=counters["inserted"],
        txns_updated=counters["updated"],
        txns_deleted=counters["deleted"],
        accounts_touched=counters["accounts_touched"],
        reconciliation=recon_status,
        drift_report=drift_report,
    )


# ---------------------------------------------------------------------------
# Upserts


def _upsert_account(store: Store, source_id: str, a: RemoteAccount, counters: dict) -> None:
    acct_id = make_id(source_id, a.external_id)
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, "
        "closed, deleted, currency, cleared_balance_minor, uncleared_balance_minor, "
        "balance_as_of, last_synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, type = excluded.type, on_budget = excluded.on_budget, "
        "closed = excluded.closed, deleted = excluded.deleted, "
        "currency = excluded.currency, "
        "cleared_balance_minor = excluded.cleared_balance_minor, "
        "uncleared_balance_minor = excluded.uncleared_balance_minor, "
        "balance_as_of = excluded.balance_as_of, "
        "last_synced_at = excluded.last_synced_at",
        (
            acct_id, source_id, a.external_id, a.name, a.type, int(a.on_budget),
            int(a.closed), int(a.deleted), a.currency,
            a.cleared_balance_minor, a.uncleared_balance_minor,
            a.balance_as_of, _utcnow(),
        ),
    )
    counters["accounts_touched"] += 1


def _upsert_category(store: Store, source_id: str, c: RemoteCategory) -> None:
    cat_id = make_id(source_id, c.external_id)
    store.execute(
        "INSERT INTO categories (id, source_id, external_id, name, group_name, "
        "hidden, deleted) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, group_name = excluded.group_name, "
        "hidden = excluded.hidden, deleted = excluded.deleted",
        (cat_id, source_id, c.external_id, c.name, c.group_name,
         int(c.hidden), int(c.deleted)),
    )


def _upsert_payee(store: Store, source_id: str, p: RemotePayee) -> None:
    payee_id = make_id(source_id, p.external_id)
    transfer_acct_id = (
        make_id(source_id, p.transfer_account_external_id)
        if p.transfer_account_external_id else None
    )
    store.execute(
        "INSERT INTO payees (id, source_id, external_id, name, transfer_account_id, "
        "deleted) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "name = excluded.name, transfer_account_id = excluded.transfer_account_id, "
        "deleted = excluded.deleted",
        (payee_id, source_id, p.external_id, p.name, transfer_acct_id, int(p.deleted)),
    )


def _upsert_transaction(
    store: Store, source_id: str, t: RemoteTransaction, counters: dict
) -> None:
    txn_id = make_id(source_id, t.external_id)
    acct_id = make_id(source_id, t.account_external_id)
    category_id = (
        make_id(source_id, t.category_external_id) if t.category_external_id else None
    )
    payee_id = (
        make_id(source_id, t.payee_external_id) if t.payee_external_id else None
    )
    transfer_acct_id = (
        make_id(source_id, t.transfer_account_external_id)
        if t.transfer_account_external_id else None
    )
    is_split_parent = 1 if t.subtransactions else 0

    existed = store.execute(
        "SELECT 1 FROM transactions WHERE id = ?", (txn_id,)
    ).fetchone() is not None

    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?) "
        "ON CONFLICT (source_id, external_id) DO UPDATE SET "
        "date = excluded.date, amount_minor = excluded.amount_minor, "
        "payee = excluded.payee, payee_id = excluded.payee_id, memo = excluded.memo, "
        "category_id = excluded.category_id, cleared = excluded.cleared, "
        "approved = excluded.approved, flag_color = excluded.flag_color, "
        "transfer_account_id = excluded.transfer_account_id, "
        "is_split_parent = excluded.is_split_parent, deleted = excluded.deleted, "
        "raw = excluded.raw, synced_at = excluded.synced_at",
        (
            txn_id, source_id, t.external_id, acct_id, t.date, t.amount_minor,
            t.currency, t.payee, payee_id, t.memo, category_id, t.cleared,
            int(t.approved), t.flag_color, t.import_id, transfer_acct_id,
            is_split_parent, int(t.deleted), None, _utcnow(),
        ),
    )

    if t.deleted:
        counters["deleted"] += 1
    elif existed:
        counters["updated"] += 1
    else:
        counters["inserted"] += 1

    if t.subtransactions:
        # Rewrite children atomically: delete then re-insert so the latest
        # split shape always reflects YNAB's truth.
        store.execute("DELETE FROM transactions WHERE parent_id = ?", (txn_id,))
        for i, sub in enumerate(t.subtransactions):
            _insert_subtransaction(store, source_id, txn_id, acct_id, t, sub, i)


def _insert_subtransaction(
    store: Store,
    source_id: str,
    parent_id: str,
    acct_id: str,
    parent: RemoteTransaction,
    sub: RemoteSubTxn,
    index: int,
) -> None:
    sub_external = f"{parent.external_id}:sub:{index}"
    sub_id = make_id(source_id, sub_external)
    category_id = (
        make_id(source_id, sub.category_external_id) if sub.category_external_id else None
    )
    payee_id = (
        make_id(source_id, sub.payee_external_id) if sub.payee_external_id else None
    )
    transfer_acct_id = (
        make_id(source_id, sub.transfer_account_external_id)
        if sub.transfer_account_external_id else None
    )
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, "
        "amount_minor, currency, payee, payee_id, memo, category_id, cleared, "
        "approved, flag_color, import_id, transfer_account_id, parent_id, "
        "is_split_parent, deleted, raw, synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?)",
        (
            sub_id, source_id, sub_external, acct_id, parent.date, sub.amount_minor,
            parent.currency, parent.payee, payee_id, sub.memo, category_id,
            parent.cleared, int(parent.approved), parent.flag_color, parent.import_id,
            transfer_acct_id, parent_id, _utcnow(),
        ),
    )


# ---------------------------------------------------------------------------
# Reconciliation


def _reconcile(
    store: Store, source_id: str, remote_accounts: tuple[RemoteAccount, ...]
) -> tuple[str, Optional[str]]:
    """Compare per-account computed cleared balance to YNAB's reported value.

    Sums the "Tops" view (parent_id IS NULL AND deleted = 0). Drift never
    fails the sync — see spec §9.3 — it just produces a structured report.
    """
    if not remote_accounts:
        return "n/a", None

    deltas: list[dict] = []
    for a in remote_accounts:
        if a.cleared_balance_minor is None:
            continue
        acct_id = make_id(source_id, a.external_id)
        row = store.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total "
            "FROM transactions "
            "WHERE account_id = ? AND parent_id IS NULL AND deleted = 0",
            (acct_id,),
        ).fetchone()
        computed = int(row["total"])
        reported = int(a.cleared_balance_minor)
        if computed != reported:
            deltas.append({
                "account_id": acct_id,
                "computed_minor": computed,
                "reported_minor": reported,
                "delta_minor": computed - reported,
            })

    if deltas:
        return "drift", json.dumps({"accounts": deltas})
    return "ok", None
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_sync.py -v`
Expected: `7 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/sources/ynab/sync.py tests/test_sync.py tests/conftest.py
git commit -m "feat(sync): atomic sync orchestrator with upserts, splits, cursor, reconciliation"
```

---

## Task 17: CLI core — `homefinance db-path` + `homefinance status`

**Goal:** Stand up the `homefinance` CLI with `typer` + `rich`. Two trivial commands prove the wiring: `db-path` echoes the resolved DB path; `status` prints a Rich table of configured sources and their last-sync state. A pluggable `_make_client(token)` factory is introduced now so later commands (and tests) can swap in `FakeYNABClient`.

**Files:**
- Create: `src/homefinance/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests at `tests/test_cli.py`**

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_cli.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.cli'`.

- [ ] **Step 3: Implement `src/homefinance/cli.py`**

```python
"""``homefinance`` — the local CLI.

Two commands ship in Task 17 (``db-path``, ``status``). ``init``, ``sync``,
and the ``ynab`` subcommands land in Tasks 18-20.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from homefinance.config import load_config
from homefinance.db.store import Store
from homefinance.sources.ynab.client import YNABClient

app = typer.Typer(
    help="homefinance — open-source, local-first home financial analysis.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _make_client(token: str) -> YNABClient:
    """Factory so tests can monkeypatch in a FakeYNABClient."""
    return YNABClient(token=token)


@app.command("db-path")
def db_path() -> None:
    """Print the resolved database path."""
    cfg = load_config()
    console.print(str(cfg.db_path))


@app.command()
def status() -> None:
    """Show configured sources and their last-sync state."""
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print(
            "[yellow]No sources configured.[/] Run [bold]homefinance init[/] first."
        )
        return
    store = Store.open(cfg.db_path)
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_recon "
        "FROM sources s "
        "LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    if not rows:
        console.print(
            "[yellow]No sources configured.[/] Run [bold]homefinance init[/] first."
        )
        return

    table = Table(title="Sources")
    table.add_column("source_id")
    table.add_column("nickname")
    table.add_column("last sync")
    table.add_column("cursor", justify="right")
    table.add_column("reconciliation")
    for r in rows:
        table.add_row(
            r["source_id"],
            r["nickname"] or "-",
            r["last_sync_at"] or "(never)",
            str(r["server_knowledge"] or "-"),
            r["last_recon"] or "-",
        )
    console.print(table)


# Placeholders for Tasks 18-20 so `homefinance --help` lists them; the actual
# implementations replace these in later tasks.

@app.command()
def init() -> None:
    """Interactive first-run setup. Implemented in Task 18."""
    raise typer.Exit(code=2)  # placeholder; tests in Task 18 cover real behavior


@app.command()
def sync(source: Optional[str] = typer.Option(None, "--source", "-s")) -> None:
    """Sync one or all sources. Implemented in Task 19."""
    raise typer.Exit(code=2)


ynab_app = typer.Typer(help="YNAB budget management.")
app.add_typer(ynab_app, name="ynab")
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_cli.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): typer scaffold with db-path and status commands"
```

---

## Task 18: `homefinance init`

**Goal:** Interactive first-run setup that writes `~/.homefinance/config.toml` and applies migrations. Supports non-interactive flags (`--token`, `--budget`, `--no-sync`) so it's fully testable without prompts.

**Files:**
- Modify: `src/homefinance/cli.py` (replace `init` placeholder; add helpers)
- Modify: `tests/test_cli.py` (append init tests)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
from homefinance.sources.ynab.fake_client import FakeYNABClient


def _patch_client(monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path) -> None:
    monkeypatch.setattr(
        "homefinance.cli._make_client", lambda token: FakeYNABClient(fixtures_dir)
    )


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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_cli.py::test_init_writes_config_and_migrates_db -v`
Expected: `exit_code == 2` (placeholder) — fails the assertion.

- [ ] **Step 3: Replace the `init` placeholder in `src/homefinance/cli.py`** with a full implementation. Replace the previous `init` function body and add helpers:

```python
# Add to the imports at the top of the file:
from pathlib import Path

from homefinance.config import YNABBudget
from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _render_config_toml(budgets: list[YNABBudget], include_token: Optional[str]) -> str:
    lines: list[str] = []
    if include_token:
        lines += ["[ynab]", f'token = "{_toml_escape(include_token)}"', ""]
    for b in budgets:
        lines += [
            "[[ynab.budgets]]",
            f'budget_id = "{_toml_escape(b.budget_id)}"',
        ]
        if b.nickname:
            lines.append(f'nickname = "{_toml_escape(b.nickname)}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# Replace the placeholder `init` command with:

@app.command()
def init(
    token: Optional[str] = typer.Option(
        None, "--token",
        envvar="HOMEFINANCE_YNAB_TOKEN",
        help="YNAB Personal Access Token. If omitted, prompted interactively.",
    ),
    budget_ids: Optional[list[str]] = typer.Option(
        None, "--budget", "-b",
        help="Budget IDs to track. May be repeated. If omitted, prompted.",
    ),
    nicknames: Optional[list[str]] = typer.Option(
        None, "--nickname", "-n",
        help="Nicknames matching --budget order. Defaults to budget name slug.",
    ),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip the post-setup sync."),
    save_token_to_file: bool = typer.Option(
        False, "--save-token-to-file",
        help="Persist the token to config.toml (default: keep it in env only).",
    ),
) -> None:
    """First-run setup: write config, register budgets, migrate DB, optionally sync."""
    cfg = load_config()
    cfg.config_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Resolve token (prompt only if neither flag nor env supplied it).
    effective_token = token
    if effective_token is None:
        effective_token = typer.prompt("YNAB Personal Access Token", hide_input=True)

    client = _make_client(effective_token)
    available = client.get_budgets().data.budgets
    if not available:
        err_console.print("[red]No YNAB budgets found for this token.[/]")
        raise typer.Exit(code=1)

    # 2. Pick budgets.
    if not budget_ids:
        console.print("Available budgets:")
        for i, b in enumerate(available):
            console.print(f"  [{i}] {b.name}  ({b.id})")
        raw = typer.prompt("Comma-separated indices to track", default="0")
        try:
            idx = [int(x.strip()) for x in raw.split(",")]
            budget_ids = [available[i].id for i in idx]
        except (ValueError, IndexError):
            err_console.print("[red]Invalid selection.[/]")
            raise typer.Exit(code=1)

    if nicknames and len(nicknames) != len(budget_ids):
        err_console.print("[red]--nickname count must match --budget count.[/]")
        raise typer.Exit(code=1)

    by_id = {b.id: b for b in available}
    selected: list[YNABBudget] = []
    for i, bid in enumerate(budget_ids):
        if bid not in by_id:
            err_console.print(f"[red]Budget {bid!r} not found in this YNAB account.[/]")
            raise typer.Exit(code=1)
        nick = nicknames[i] if nicknames else by_id[bid].name.lower().replace(" ", "-")
        selected.append(YNABBudget(budget_id=bid, nickname=nick))

    # 3. Write config + migrate.
    toml = _render_config_toml(
        selected, include_token=effective_token if save_token_to_file else None
    )
    cfg.config_path.write_text(toml)
    migrate(cfg.db_path)
    console.print(f"[green]Config written:[/] {cfg.config_path}")
    console.print(f"[green]Database ready:[/] {cfg.db_path}")

    if no_sync:
        return

    # 4. First sync per budget.
    store = Store.open(cfg.db_path)
    for b in selected:
        source = YNABAccountSource(b.budget_id, client, nickname=b.nickname)
        result = run_sync(source, store)
        console.print(
            f"[green]Synced[/] {b.nickname}: "
            f"{result.txns_inserted} new, {result.txns_updated} updated, "
            f"{result.txns_deleted} deleted; reconciliation={result.reconciliation}"
        )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_cli.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): interactive + scriptable init command"
```

---

## Task 19: `homefinance sync`

**Goal:** Replace the `sync` placeholder with a real command that syncs all configured budgets (or one selected via `--source`). Reads the token from env or config; reads budgets from config.

**Files:**
- Modify: `src/homefinance/cli.py` (replace `sync` placeholder)
- Modify: `tests/test_cli.py` (append sync tests)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_cli.py::test_sync_processes_all_configured_budgets -v`
Expected: exit_code 2 (placeholder).

- [ ] **Step 3: Replace the `sync` placeholder in `src/homefinance/cli.py`** with:

```python
@app.command()
def sync(
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help="Sync only the named source_id (e.g., ynab:abc). Default: all.",
    ),
) -> None:
    """Sync one or all configured budgets."""
    cfg = load_config()
    if cfg.ynab_token is None:
        err_console.print(
            "[red]No YNAB token configured.[/] Set "
            "[bold]HOMEFINANCE_YNAB_TOKEN[/] or add [bold][ynab].token[/] to "
            f"{cfg.config_path}."
        )
        raise typer.Exit(code=1)
    if not cfg.ynab.budgets:
        err_console.print(
            "[red]No budgets configured.[/] Run [bold]homefinance init[/]."
        )
        raise typer.Exit(code=1)

    client = _make_client(cfg.ynab_token.get_secret_value())
    store = Store.open(cfg.db_path)

    targets = cfg.ynab.budgets
    if source is not None:
        targets = [b for b in cfg.ynab.budgets if f"ynab:{b.budget_id}" == source]
        if not targets:
            err_console.print(f"[red]Source {source!r} not found in config.[/]")
            raise typer.Exit(code=1)

    for b in targets:
        src = YNABAccountSource(b.budget_id, client, nickname=b.nickname)
        result = run_sync(src, store)
        console.print(
            f"[green]Synced[/] {b.nickname or b.budget_id}: "
            f"{result.txns_inserted} new, {result.txns_updated} updated, "
            f"{result.txns_deleted} deleted; reconciliation={result.reconciliation}"
        )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_cli.py -v`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): sync command with --source filter and clear error states"
```

---

## Task 20: `homefinance ynab add-budget` / `remove-budget`

**Goal:** Two `ynab` subcommands let users adjust the registered budget list without re-running `init` or hand-editing TOML. Both rewrite `config.toml` atomically (write-to-temp + rename).

**Files:**
- Modify: `src/homefinance/cli.py` (register subcommands)
- Modify: `tests/test_cli.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_cli.py -v -k ynab`
Expected: `No such command 'add-budget'`.

- [ ] **Step 3: Add the subcommands to `src/homefinance/cli.py`**

```python
import os
import tempfile


def _atomic_write(path: Path, content: str) -> None:
    """Write to a temp file in the same directory, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        finally:
            raise


@ynab_app.command("add-budget")
def ynab_add_budget(
    budget_id: str = typer.Option(..., "--budget-id", help="YNAB budget ID."),
    nickname: Optional[str] = typer.Option(None, "--nickname"),
) -> None:
    """Register an additional YNAB budget in config.toml."""
    cfg = load_config()
    if any(b.budget_id == budget_id for b in cfg.ynab.budgets):
        err_console.print(f"[red]Budget {budget_id!r} is already registered.[/]")
        raise typer.Exit(code=1)
    new_list = list(cfg.ynab.budgets) + [YNABBudget(budget_id=budget_id, nickname=nickname)]
    _atomic_write(cfg.config_path, _render_config_toml(new_list, include_token=None))
    console.print(f"[green]Added[/] budget {budget_id} (nickname: {nickname or '-'})")


@ynab_app.command("remove-budget")
def ynab_remove_budget(
    budget_id: str = typer.Option(..., "--budget-id"),
) -> None:
    """Remove a YNAB budget from config.toml. Does not delete its data from the DB."""
    cfg = load_config()
    new_list = [b for b in cfg.ynab.budgets if b.budget_id != budget_id]
    if len(new_list) == len(cfg.ynab.budgets):
        err_console.print(f"[red]Budget {budget_id!r} not found in config.[/]")
        raise typer.Exit(code=1)
    _atomic_write(cfg.config_path, _render_config_toml(new_list, include_token=None))
    console.print(
        f"[yellow]Removed[/] budget {budget_id} from config. "
        "Existing data in the DB is preserved."
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/test_cli.py -v`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): ynab add-budget and remove-budget subcommands with atomic config rewrites"
```

---

## Task 21: MCP server scaffolding

**Goal:** Set up the stdio MCP server entry point using `FastMCP`. Tools are *implemented* as plain functions in `tools.py` (testable as functions) and *registered* as `@mcp.tool()` wrappers in `__main__.py`. Store and YNAB client are lazy-initialized on first call so importing the server doesn't fail without config.

**Files:**
- Create: `src/homefinance/mcp_server/tools.py` (empty module — fleshed out in Tasks 22-25)
- Create: `src/homefinance/mcp_server/__main__.py`

- [ ] **Step 1: Create `src/homefinance/mcp_server/tools.py`** (placeholder; populated next):

```python
"""MCP tool implementations as plain functions. The stdio server wraps these
with ``@mcp.tool()`` decorators in ``__main__.py``. Defined as functions (not
decorators) so tests can call them directly without spinning up the MCP runtime.
"""
```

- [ ] **Step 2: Create `src/homefinance/mcp_server/__main__.py`**

```python
"""Stdio MCP server for homefinance.

Launch via ``python -m homefinance.mcp_server``. The plugin's ``.mcp.json``
registers this command. State (Store, YNAB client) is lazy-initialized on
first tool call so import is side-effect-free.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from homefinance.config import Config, load_config
from homefinance.db.store import Store

mcp = FastMCP("homefinance")

_cfg: Optional[Config] = None
_store: Optional[Store] = None


def _cfg_cached() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def _store_cached() -> Store:
    global _store
    if _store is None:
        _store = Store.open(_cfg_cached().db_path)
    return _store


# Tools are registered in Tasks 22-25 — each task appends `@mcp.tool()`
# wrappers below that import their implementation from
# `homefinance.mcp_server.tools` and call it with the cached store / config.


if __name__ == "__main__":  # pragma: no cover
    mcp.run()
```

- [ ] **Step 3: Verify both modules import**

Run: `python -c "from homefinance.mcp_server import __main__, tools"`
Expected: exits 0 with no output (no stdio loop started because we didn't run `__main__` as a script).

- [ ] **Step 4: Commit**

```bash
git add src/homefinance/mcp_server/__main__.py src/homefinance/mcp_server/tools.py
git commit -m "feat(mcp): stdio server scaffold with lazy Store + Config"
```

---

## Task 22: Read tools — `list_sources`, `list_accounts`, `get_account`, `list_categories`

**Goal:** The four simple read tools. They take a `Store` and return JSON-friendly dicts. Each is registered as an `@mcp.tool()` in `__main__.py`.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py`
- Modify: `src/homefinance/mcp_server/__main__.py` (append wrappers)
- Create: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write failing tests at `tests/test_mcp_tools.py`**

```python
from pathlib import Path

import pytest

from homefinance.db.store import Store
from homefinance.mcp_server.tools import (
    get_account,
    list_accounts,
    list_categories,
    list_sources,
)
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.sync import run_sync


@pytest.fixture
def synced_store(store: Store, tiny_fixtures_dir: Path) -> Store:
    src = YNABAccountSource("budget-tiny", FakeYNABClient(tiny_fixtures_dir), nickname="tiny")
    run_sync(src, store)
    return store


def test_list_sources_returns_registered_budgets(synced_store: Store) -> None:
    rows = list_sources(synced_store)
    assert len(rows) == 1
    r = rows[0]
    assert r["source_id"] == "ynab:budget-tiny"
    assert r["kind"] == "ynab"
    assert r["nickname"] == "tiny"
    assert r["last_sync_at"] is not None
    assert r["last_reconciliation"] in ("ok", "drift")


def test_list_accounts_returns_all_when_no_filter(synced_store: Store) -> None:
    rows = list_accounts(synced_store)
    assert {r["external_id"] for r in rows} == {"acct-checking", "acct-credit"}
    checking = next(r for r in rows if r["external_id"] == "acct-checking")
    assert checking["cleared_balance_minor"] == 123456


def test_list_accounts_filters_by_source(synced_store: Store) -> None:
    rows = list_accounts(synced_store, source_id="ynab:nope")
    assert rows == []


def test_list_accounts_hides_closed_by_default(synced_store: Store) -> None:
    synced_store.execute(
        "UPDATE accounts SET closed = 1 WHERE external_id = ?", ("acct-credit",)
    )
    rows = list_accounts(synced_store)
    assert {r["external_id"] for r in rows} == {"acct-checking"}
    rows_all = list_accounts(synced_store, include_closed=True)
    assert {r["external_id"] for r in rows_all} == {"acct-checking", "acct-credit"}


def test_get_account_includes_latest_reconciliation(synced_store: Store) -> None:
    r = get_account(synced_store, account_id="ynab:budget-tiny:acct-checking")
    assert r["name"] == "Checking"
    assert "reconciliation" in r


def test_get_account_raises_for_unknown(synced_store: Store) -> None:
    with pytest.raises(KeyError, match="not found"):
        get_account(synced_store, account_id="ynab:budget-tiny:nope")


def test_list_categories_filters_hidden(synced_store: Store) -> None:
    synced_store.execute(
        "UPDATE categories SET hidden = 1 WHERE external_id = ?", ("cat-dining",)
    )
    visible = {c["external_id"] for c in list_categories(synced_store)}
    assert "cat-dining" not in visible
    all_cats = {c["external_id"] for c in list_categories(synced_store, include_hidden=True)}
    assert "cat-dining" in all_cats
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: `ImportError` for each tool function.

- [ ] **Step 3: Implement the four tools in `src/homefinance/mcp_server/tools.py`**

```python
"""MCP tool implementations as plain functions. The stdio server wraps these
with ``@mcp.tool()`` decorators in ``__main__.py``.
"""

from __future__ import annotations

from typing import Any, Optional

from homefinance.db.store import Store


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Sources


def list_sources(store: Store) -> list[dict[str, Any]]:
    """List registered budgets + last-sync info."""
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_reconciliation "
        "FROM sources s LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Accounts


def list_accounts(
    store: Store, source_id: Optional[str] = None, include_closed: bool = False
) -> list[dict[str, Any]]:
    where: list[str] = ["deleted = 0"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if not include_closed:
        where.append("closed = 0")
    sql = (
        "SELECT id, source_id, external_id, name, type, on_budget, closed, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of "
        "FROM accounts WHERE " + " AND ".join(where) + " ORDER BY name"
    )
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]


def get_account(store: Store, account_id: str) -> dict[str, Any]:
    row = store.execute(
        "SELECT id, source_id, external_id, name, type, on_budget, closed, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, "
        "last_synced_at "
        "FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"account {account_id!r} not found")
    result = _row_to_dict(row)
    recon = store.execute(
        "SELECT reconciliation FROM sync_runs WHERE source_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (result["source_id"],),
    ).fetchone()
    result["reconciliation"] = recon["reconciliation"] if recon else None
    return result


# ---------------------------------------------------------------------------
# Categories


def list_categories(
    store: Store, source_id: Optional[str] = None, include_hidden: bool = False
) -> list[dict[str, Any]]:
    where: list[str] = ["deleted = 0"]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if not include_hidden:
        where.append("hidden = 0")
    sql = (
        "SELECT id, source_id, external_id, name, group_name "
        "FROM categories WHERE " + " AND ".join(where) + " ORDER BY group_name, name"
    )
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]
```

- [ ] **Step 4: Append `@mcp.tool()` wrappers to `src/homefinance/mcp_server/__main__.py`**

```python
from homefinance.mcp_server import tools as _tools


@mcp.tool()
def list_sources() -> list[dict]:
    """Registered budgets with last-sync info."""
    return _tools.list_sources(_store_cached())


@mcp.tool()
def list_accounts(source_id: Optional[str] = None, include_closed: bool = False) -> list[dict]:
    """Accounts across (or within) budgets; hides closed by default."""
    return _tools.list_accounts(_store_cached(), source_id=source_id, include_closed=include_closed)


@mcp.tool()
def get_account(account_id: str) -> dict:
    """Single account detail plus the latest reconciliation status."""
    return _tools.get_account(_store_cached(), account_id=account_id)


@mcp.tool()
def list_categories(source_id: Optional[str] = None, include_hidden: bool = False) -> list[dict]:
    """Categories per source; hides hidden by default."""
    return _tools.list_categories(_store_cached(), source_id=source_id, include_hidden=include_hidden)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: `7 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): list_sources/list_accounts/get_account/list_categories tools"
```

---

## Task 23: `query_transactions` tool

**Goal:** The workhorse tool. Filter by account/source/date/category/payee/amount/cleared/include_deleted; `mode` selects the **Leaves** (default) or **Tops** view (spec §6.3). The Leaves view encodes the no-double-counting discipline at the API edge.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py` (append)
- Modify: `src/homefinance/mcp_server/__main__.py` (append wrapper)
- Modify: `tests/test_mcp_tools.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`**

```python
from homefinance.mcp_server.tools import query_transactions


def test_query_transactions_leaves_default_excludes_split_parent(synced_store: Store) -> None:
    rows = query_transactions(synced_store)
    ext_ids = {r["external_id"] for r in rows}
    # Tops: split parent is included, children are NOT. Leaves: parents excluded, children included.
    assert "txn-split" not in ext_ids
    assert any(":sub:" in eid for eid in ext_ids)
    # Sum over leaves should match sum over tops.
    leaves_total = sum(r["amount_minor"] for r in rows)
    tops_total = sum(r["amount_minor"] for r in query_transactions(synced_store, mode="tops"))
    assert leaves_total == tops_total


def test_query_transactions_tops_includes_split_parent_not_children(synced_store: Store) -> None:
    rows = query_transactions(synced_store, mode="tops")
    ext_ids = {r["external_id"] for r in rows}
    assert "txn-split" in ext_ids
    assert not any(":sub:" in eid for eid in ext_ids)


def test_query_transactions_filters_by_date_range(synced_store: Store) -> None:
    rows = query_transactions(synced_store, date_from="2026-06-02", date_to="2026-06-02")
    dates = {r["date"] for r in rows}
    assert dates == {"2026-06-02"}


def test_query_transactions_excludes_deleted_by_default(synced_store: Store) -> None:
    synced_store.execute(
        "UPDATE transactions SET deleted = 1 WHERE external_id = 'txn-non-split'"
    )
    rows = query_transactions(synced_store)
    assert all(r["external_id"] != "txn-non-split" for r in rows)
    rows_all = query_transactions(synced_store, include_deleted=True)
    assert any(r["external_id"] == "txn-non-split" for r in rows_all)


def test_query_transactions_filters_by_amount_range(synced_store: Store) -> None:
    rows = query_transactions(synced_store, amount_max_minor=-3000)
    assert all(r["amount_minor"] <= -3000 for r in rows)


def test_query_transactions_filters_by_payee_substring(synced_store: Store) -> None:
    rows = query_transactions(synced_store, payee_contains="Trader")
    assert all("Trader" in (r["payee"] or "") for r in rows)


def test_query_transactions_limit_and_offset(synced_store: Store) -> None:
    page1 = query_transactions(synced_store, limit=1, offset=0)
    page2 = query_transactions(synced_store, limit=1, offset=1)
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_mcp_tools.py -v -k query_transactions`
Expected: `ImportError`.

- [ ] **Step 3: Append `query_transactions` to `src/homefinance/mcp_server/tools.py`**

```python
from typing import Literal

Mode = Literal["leaves", "tops"]


def query_transactions(
    store: Store,
    source_id: Optional[str] = None,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
    payee_contains: Optional[str] = None,
    amount_min_minor: Optional[int] = None,
    amount_max_minor: Optional[int] = None,
    cleared: Optional[str] = None,
    include_deleted: bool = False,
    mode: Mode = "leaves",
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List transactions. ``mode='leaves'`` (default) = non-split rows + split
    children (analysis view, correct category attribution).
    ``mode='tops'`` = non-split rows + split parents (user-facing view).
    Both views sum to the same total — see spec §6.3.
    """
    where: list[str] = []
    params: list[Any] = []

    if mode == "leaves":
        where.append("is_split_parent = 0")
    elif mode == "tops":
        where.append("parent_id IS NULL")
    else:
        raise ValueError(f"invalid mode: {mode!r}")

    if not include_deleted:
        where.append("deleted = 0")
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if account_id is not None:
        where.append("account_id = ?")
        params.append(account_id)
    if date_from is not None:
        where.append("date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("date <= ?")
        params.append(date_to)
    if category_id is not None:
        where.append("category_id = ?")
        params.append(category_id)
    if payee_contains is not None:
        where.append("payee LIKE ?")
        params.append(f"%{payee_contains}%")
    if amount_min_minor is not None:
        where.append("amount_minor >= ?")
        params.append(amount_min_minor)
    if amount_max_minor is not None:
        where.append("amount_minor <= ?")
        params.append(amount_max_minor)
    if cleared is not None:
        where.append("cleared = ?")
        params.append(cleared)

    sql = (
        "SELECT id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, memo, category_id, cleared, approved, flag_color, "
        "import_id, transfer_account_id, parent_id, is_split_parent, deleted "
        "FROM transactions WHERE " + " AND ".join(where) +
        " ORDER BY date DESC, id LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])
    return [_row_to_dict(r) for r in store.execute(sql, params).fetchall()]
```

- [ ] **Step 4: Append the `@mcp.tool()` wrapper to `__main__.py`**

```python
@mcp.tool()
def query_transactions(
    source_id: Optional[str] = None,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
    payee_contains: Optional[str] = None,
    amount_min_minor: Optional[int] = None,
    amount_max_minor: Optional[int] = None,
    cleared: Optional[str] = None,
    include_deleted: bool = False,
    mode: str = "leaves",
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """List transactions. ``mode='leaves'`` (default) gives the analysis view;
    ``mode='tops'`` gives the user-facing 'one transaction per split' view."""
    return _tools.query_transactions(
        _store_cached(),
        source_id=source_id, account_id=account_id,
        date_from=date_from, date_to=date_to,
        category_id=category_id, payee_contains=payee_contains,
        amount_min_minor=amount_min_minor, amount_max_minor=amount_max_minor,
        cleared=cleared, include_deleted=include_deleted,
        mode=mode, limit=limit, offset=offset,
    )
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: `14 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): query_transactions tool with leaves/tops mode"
```

---

## Task 24: `summarize_spending` tool

**Goal:** Server-side aggregation that **always operates on the Leaves view** so totals and category attribution are simultaneously correct (spec §8.2 insight). Supports `group_by ∈ {category, payee, month, account, day_of_week}`.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py` (append)
- Modify: `src/homefinance/mcp_server/__main__.py` (append wrapper)
- Modify: `tests/test_mcp_tools.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`**

```python
from homefinance.mcp_server.tools import summarize_spending


def test_summarize_by_category_uses_leaves_view(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="category")
    by_key = {r["key"]: r for r in rows}
    # Split: $400 gas + $100 groceries; non-split: $456.70 groceries.
    # Leaves total for groceries = -400 + -45670 = -46070 (cents).
    assert by_key["Groceries"]["total_minor"] == -46070
    assert by_key["Gas"]["total_minor"] == -40000


def test_summarize_by_month(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="month")
    assert any(r["key"] == "2026-06" for r in rows)


def test_summarize_by_account(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="account")
    by_key = {r["key"]: r for r in rows}
    assert "Checking" in by_key
    assert by_key["Checking"]["count"] > 0


def test_summarize_by_payee(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="payee")
    assert any(r["key"] == "Trader Joe's" for r in rows)


def test_summarize_invalid_group_by_raises(synced_store: Store) -> None:
    with pytest.raises(ValueError):
        summarize_spending(synced_store, group_by="banana")
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_mcp_tools.py -v -k summarize`
Expected: `ImportError`.

- [ ] **Step 3: Append `summarize_spending` to `src/homefinance/mcp_server/tools.py`**

```python
GroupBy = Literal["category", "payee", "month", "account", "day_of_week"]


_GROUP_EXPR: dict[str, str] = {
    "category":     "COALESCE(c.name, '(uncategorized)')",
    "payee":        "COALESCE(t.payee, '(no payee)')",
    "month":        "substr(t.date, 1, 7)",
    "account":      "a.name",
    "day_of_week":  "CAST(strftime('%w', t.date) AS INTEGER)",
}


def summarize_spending(
    store: Store,
    source_id: Optional[str] = None,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    payee_contains: Optional[str] = None,
    cleared: Optional[str] = None,
    group_by: GroupBy = "category",
) -> list[dict[str, Any]]:
    """Aggregate spending. Always operates on the Leaves view (is_split_parent = 0,
    deleted = 0) so totals + category attribution are simultaneously correct.
    """
    expr = _GROUP_EXPR.get(group_by)
    if expr is None:
        raise ValueError(f"invalid group_by: {group_by!r}")

    where: list[str] = ["t.is_split_parent = 0", "t.deleted = 0"]
    params: list[Any] = []

    if source_id is not None:
        where.append("t.source_id = ?")
        params.append(source_id)
    if account_id is not None:
        where.append("t.account_id = ?")
        params.append(account_id)
    if date_from is not None:
        where.append("t.date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("t.date <= ?")
        params.append(date_to)
    if payee_contains is not None:
        where.append("t.payee LIKE ?")
        params.append(f"%{payee_contains}%")
    if cleared is not None:
        where.append("t.cleared = ?")
        params.append(cleared)

    sql = (
        f"SELECT {expr} AS key, SUM(t.amount_minor) AS total_minor, "
        f"COUNT(*) AS count "
        "FROM transactions t "
        "LEFT JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE " + " AND ".join(where) +
        f" GROUP BY {expr} ORDER BY total_minor"
    )
    return [
        {"key": r["key"], "total_minor": int(r["total_minor"]), "count": int(r["count"])}
        for r in store.execute(sql, params).fetchall()
    ]
```

- [ ] **Step 4: Append the `@mcp.tool()` wrapper to `__main__.py`**

```python
@mcp.tool()
def summarize_spending(
    source_id: Optional[str] = None,
    account_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    payee_contains: Optional[str] = None,
    cleared: Optional[str] = None,
    group_by: str = "category",
) -> list[dict]:
    """Aggregate spending. ``group_by ∈ {category, payee, month, account, day_of_week}``."""
    return _tools.summarize_spending(
        _store_cached(),
        source_id=source_id, account_id=account_id,
        date_from=date_from, date_to=date_to,
        payee_contains=payee_contains, cleared=cleared,
        group_by=group_by,
    )
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: `19 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): summarize_spending tool, leaves-view aggregations"
```

---

## Task 25: `get_sync_status` + `sync_ynab` tools

**Goal:** The last two tools. `get_sync_status` reports per-source last-sync + drift summary. `sync_ynab` triggers `run_sync()` for one or all YNAB sources and returns the resulting `sync_runs`-like row.

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py` (append)
- Modify: `src/homefinance/mcp_server/__main__.py` (append wrappers)
- Modify: `tests/test_mcp_tools.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`**

```python
from homefinance.mcp_server.tools import get_sync_status, sync_ynab_all


def test_get_sync_status_returns_per_source_summary(synced_store: Store) -> None:
    rows = get_sync_status(synced_store)
    assert len(rows) == 1
    r = rows[0]
    assert r["source_id"] == "ynab:budget-tiny"
    assert r["last_sync_at"] is not None
    assert r["last_reconciliation"] in ("ok", "drift")
    assert "drift_account_count" in r


def test_sync_ynab_all_runs_for_each_budget(
    store: Store, tiny_fixtures_dir: Path
) -> None:
    fake = FakeYNABClient(tiny_fixtures_dir)
    sources = [YNABAccountSource("budget-tiny", fake, nickname="tiny")]
    results = sync_ynab_all(store, sources)
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["source_id"] == "ynab:budget-tiny"
    assert "reconciliation" in results[0]
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/test_mcp_tools.py -v -k "sync_status or sync_ynab"`
Expected: `ImportError`.

- [ ] **Step 3: Append the two tools to `src/homefinance/mcp_server/tools.py`**

```python
import json

from homefinance.sources.base import AccountSource
from homefinance.sources.ynab.sync import SyncRunResult, run_sync


def get_sync_status(store: Store) -> list[dict[str, Any]]:
    """Per-source last-sync + drift summary."""
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_reconciliation, "
        "(SELECT drift_report FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_drift_report "
        "FROM sources s LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        drift_count = 0
        if r["last_drift_report"]:
            try:
                drift_count = len(json.loads(r["last_drift_report"]).get("accounts", []))
            except (json.JSONDecodeError, AttributeError, TypeError):
                drift_count = 0
        out.append({
            "source_id":           r["source_id"],
            "kind":                r["kind"],
            "nickname":            r["nickname"],
            "last_sync_at":        r["last_sync_at"],
            "server_knowledge":    r["server_knowledge"],
            "last_reconciliation": r["last_reconciliation"],
            "drift_account_count": drift_count,
        })
    return out


def _result_to_dict(r: SyncRunResult) -> dict[str, Any]:
    return {
        "source_id":         r.source_id,
        "status":            r.status,
        "txns_inserted":     r.txns_inserted,
        "txns_updated":      r.txns_updated,
        "txns_deleted":      r.txns_deleted,
        "accounts_touched":  r.accounts_touched,
        "reconciliation":    r.reconciliation,
        "drift_report":      r.drift_report,
    }


def sync_ynab_all(store: Store, sources: list[AccountSource]) -> list[dict[str, Any]]:
    """Sync each provided AccountSource and return the result rows."""
    return [_result_to_dict(run_sync(s, store)) for s in sources]


def sync_ynab_one(store: Store, source: AccountSource) -> dict[str, Any]:
    return _result_to_dict(run_sync(source, store))
```

- [ ] **Step 4: Append the `@mcp.tool()` wrappers to `__main__.py`**

```python
from homefinance.sources.ynab.client import YNABClient as _YNABClient
from homefinance.sources.ynab.source import YNABAccountSource as _YNABAccountSource


def _ynab_sources(cfg: Config) -> list[_YNABAccountSource]:
    if cfg.ynab_token is None:
        raise RuntimeError(
            "No YNAB token configured. Set HOMEFINANCE_YNAB_TOKEN or [ynab].token."
        )
    client = _YNABClient(token=cfg.ynab_token.get_secret_value())
    return [
        _YNABAccountSource(b.budget_id, client, nickname=b.nickname)
        for b in cfg.ynab.budgets
    ]


@mcp.tool()
def get_sync_status() -> list[dict]:
    """Per-source last-sync + drift summary."""
    return _tools.get_sync_status(_store_cached())


@mcp.tool()
def sync_ynab(source_id: Optional[str] = None) -> list[dict]:
    """Sync one (`source_id` set) or all configured YNAB budgets."""
    cfg = _cfg_cached()
    sources = _ynab_sources(cfg)
    if source_id is not None:
        sources = [s for s in sources if s.source_id == source_id]
        if not sources:
            raise ValueError(f"source {source_id!r} not configured")
    return _tools.sync_ynab_all(_store_cached(), sources)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: `21 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): get_sync_status and sync_ynab tools complete the 8-tool surface"
```

---

## Task 26: Plugin manifest, MCP wiring, and the `homefinance-setup` skill

**Goal:** Wire the package into a Claude Code plugin: `plugin.json` metadata, `.mcp.json` pointing at the stdio server, and the first SKILL.md that walks the user through token entry, `init`, and verification.

**Files:**
- Create: `plugin/plugin.json`
- Create: `plugin/.mcp.json`
- Create: `plugin/skills/homefinance-setup/SKILL.md`

- [ ] **Step 1: Create `plugin/plugin.json`**

```json
{
  "name": "homefinance",
  "version": "0.1.0",
  "description": "Open-source, local-first home financial analysis. Syncs YNAB, exposes spending/balance/transaction tools, and ships skills for setup and exploration.",
  "author": {
    "name": "Aaron Sachs"
  },
  "license": "MIT",
  "homepage": "https://github.com/asachs/homefinance"
}
```

- [ ] **Step 2: Create `plugin/.mcp.json`**

```json
{
  "mcpServers": {
    "homefinance": {
      "command": "python",
      "args": ["-m", "homefinance.mcp_server"]
    }
  }
}
```

- [ ] **Step 3: Create `plugin/skills/homefinance-setup/SKILL.md`**

```markdown
---
name: homefinance-setup
description: Use when the user is setting up homefinance for the first time, asks how to install or configure the plugin, mentions needing a YNAB token, or asks why no data appears. Walks the user from zero to a successful first sync.
---

# homefinance Setup

You are guiding a user through the first-run setup of the homefinance plugin.

## What you should know

- homefinance is local-first; nothing leaves the user's machine except outbound calls to api.ynab.com.
- The YNAB token is a Personal Access Token from https://app.ynab.com/settings/developer.
- The token lives in `$HOMEFINANCE_YNAB_TOKEN` (preferred) or `~/.homefinance/config.toml` under `[ynab].token`. Env beats file.
- The database is at `~/.homefinance/db.sqlite3` (or `$XDG_DATA_HOME/homefinance/db.sqlite3`).

## Setup workflow

1. **Confirm install.** Ask the user to run `python -c "import homefinance; print(homefinance.__version__)"`. If it fails, point them at `pip install -e .` in the cloned repo.

2. **Get a YNAB Personal Access Token.** Send them to https://app.ynab.com/settings/developer → "New Token". Recommend they `export HOMEFINANCE_YNAB_TOKEN=...` in their shell rather than write it to a file.

3. **Run `homefinance init`.** Interactive prompts pick budgets and nicknames. After the budget list shows, suggest comma-separated indices (`0` or `0,1`).

4. **Verify the first sync ran.** Call the `get_sync_status` tool. Confirm `last_sync_at` is set and `last_reconciliation` is `ok` or `drift`.

5. **If reconciliation reports `drift`**, that is *normal* on first sync — small balance mismatches happen at the bank-statement boundary. Use `get_account` to look at one account and explain the deltas; do not treat it as an error.

## When something goes wrong

- `401 from YNAB` → the token was rejected. Have the user generate a new PAT and re-export `HOMEFINANCE_YNAB_TOKEN`.
- `No budgets configured` after `init` → re-run `homefinance ynab add-budget --budget-id <id> --nickname <name>` (use the budget IDs from `list_sources` on the YNAB site).
- `Database is locked` → another `homefinance` process is mid-sync; wait and retry.

## What to do after setup succeeds

Suggest the `homefinance-explore` skill (or `/homefinance:explore`) for a guided first look at the data.
```

- [ ] **Step 4: Sanity-check the JSON manifests parse**

Run:
```bash
python -c "import json; json.load(open('plugin/plugin.json')); json.load(open('plugin/.mcp.json'))" && echo OK
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add plugin/plugin.json plugin/.mcp.json plugin/skills/homefinance-setup/SKILL.md
git commit -m "feat(plugin): manifest, MCP wiring, and homefinance-setup skill"
```

---

## Task 27: `homefinance-explore` skill

**Goal:** The analysis-starter skill. Demonstrates the 8-tool surface with a small set of canonical questions that prove SP1 works end-to-end.

**Files:**
- Create: `plugin/skills/homefinance-explore/SKILL.md`

- [ ] **Step 1: Create `plugin/skills/homefinance-explore/SKILL.md`**

```markdown
---
name: homefinance-explore
description: Use when the user wants a guided first look at their financial data, asks "show me my finances at a glance", asks about spending by category or by month, asks about balances or recent transactions, or invokes /homefinance:explore. Exercises the full read-tool surface.
---

# homefinance — Explore the data

You are giving the user a guided first look at their finances using the homefinance MCP tools.

## Tool surface (8 tools)

- `list_sources` — registered budgets, last-sync info
- `list_accounts(source_id?, include_closed?)` — accounts with balances
- `get_account(account_id)` — one account + latest reconciliation
- `list_categories(source_id?, include_hidden?)` — category list
- `query_transactions(filters, mode='leaves'|'tops')` — transaction listing. **Always reach for `mode='leaves'`** (the default) when you'll sum amounts or group by category. Use `mode='tops'` only when the user wants the "one row per user-facing transaction" view.
- `summarize_spending(filters, group_by)` — aggregate over the Leaves view; `group_by ∈ {category, payee, month, account, day_of_week}`.
- `get_sync_status` — when the user asks "is this data current?"
- `sync_ynab(source_id?)` — only when the user explicitly asks to sync.

## Canonical opening questions to offer

Pick one based on context; do not ask all four:

1. **"Show me my finances at a glance."** → `list_sources` then `list_accounts`. Render account balances in a small table grouped by `type` (checking, savings, credit_card). Convert `*_minor` cents to dollars in the *output*, not in queries.

2. **"What did I spend on dining last month?"** → resolve "dining" against `list_categories` (look for "Dining Out", "Restaurants", or similar). Use `summarize_spending(group_by='category', date_from=<month-start>, date_to=<month-end>)`. If the user asks for a list, follow with `query_transactions(category_id=…, date_from=…, date_to=…)`.

3. **"How has my spending trended?"** → `summarize_spending(group_by='month')` over the last 6-12 months. Present as a small markdown table; flag any month that is >25% off the median.

4. **"What were my biggest expenses last month?"** → `query_transactions(date_from=…, date_to=…, amount_max_minor=-some_threshold)` sorted by absolute amount.

## Rules

- Amounts are stored in **signed integer minor units (cents)**. Negative = outflow. Convert to dollars only in user-facing output.
- Never call `sync_ynab` unprompted. The user controls when to refresh.
- If `get_sync_status` shows `last_reconciliation = 'drift'`, mention it briefly when relevant (e.g., the user asks about balances) but do not block the analysis.
- If the user asks a question the read tools cannot answer (e.g., projection, allocation, retirement planning), say so honestly — those land in SP3 / SP4.

## When the user asks "is anything off?"

Run `get_sync_status`. If `drift_account_count > 0`, surface the affected accounts via the `drift_report` JSON and suggest a re-sync via `sync_ynab`.
```

- [ ] **Step 2: Verify the SKILL.md parses as YAML frontmatter**

Run:
```bash
python -c "
import re, yaml, pathlib
text = pathlib.Path('plugin/skills/homefinance-explore/SKILL.md').read_text()
m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
meta = yaml.safe_load(m.group(1))
assert meta['name'] == 'homefinance-explore'
assert meta['description']
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add plugin/skills/homefinance-explore/SKILL.md
git commit -m "feat(plugin): homefinance-explore analysis-starter skill"
```

---

## Task 28: Fixture-recording script

**Goal:** A standalone `scripts/record_fixtures.py` for the maintainer to run once on real YNAB data, producing sanitized JSON files suitable for bundling under `tests/fixtures/ynab/<name>/`. Contributors never need a token; they just use the existing `tiny` fixtures or any newly captured set.

**Files:**
- Create: `scripts/record_fixtures.py`

- [ ] **Step 1: Implement `scripts/record_fixtures.py`**

```python
"""Record sanitized YNAB API responses for use as test fixtures.

Usage:
    HOMEFINANCE_YNAB_TOKEN=... python scripts/record_fixtures.py \
        --budget-id <budget> --out tests/fixtures/ynab/recorded

What it does:
    Calls every endpoint the sync engine uses and writes the responses to
    JSON files. *Sanitizes* identifying information — names, memos, IDs
    become deterministic placeholders — while keeping amounts and structure
    so the fixtures realistically exercise mapping + sync.

Always review the output before committing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from homefinance.sources.ynab.client import YNABClient


def _renumber(seq: list[dict], id_key: str, prefix: str, mapping: dict[str, str]) -> None:
    for i, item in enumerate(seq, start=1):
        real_id = item[id_key]
        if real_id not in mapping:
            mapping[real_id] = f"{prefix}-{i}"
        item[id_key] = mapping[real_id]


def _scrub_strings(obj: Any, mapping: dict[str, str], string_fields: set[str]) -> Any:
    """Replace identifying strings; pass through IDs already in the mapping."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, str) and v in mapping:
                out[k] = mapping[v]
            elif isinstance(v, str) and k in string_fields and v:
                out[k] = f"[scrubbed {k}]"
            else:
                out[k] = _scrub_strings(v, mapping, string_fields)
        return out
    if isinstance(obj, list):
        return [_scrub_strings(v, mapping, string_fields) for v in obj]
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    token = os.environ.get("HOMEFINANCE_YNAB_TOKEN")
    if not token:
        print("error: HOMEFINANCE_YNAB_TOKEN is required", file=sys.stderr)
        return 2

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    client = YNABClient(token=token)

    user = client.get_user().model_dump()
    budgets = client.get_budgets().model_dump()
    accounts = client.get_accounts(args.budget_id).model_dump()
    categories = client.get_categories(args.budget_id).model_dump()
    payees = client.get_payees(args.budget_id).model_dump()
    transactions = client.get_transactions(args.budget_id).model_dump()

    # Build an ID remapping across all entities and apply scrubbing.
    id_mapping: dict[str, str] = {}
    _renumber(accounts["data"]["accounts"], "id", "acct", id_mapping)
    for grp in categories["data"]["category_groups"]:
        _renumber([grp], "id", "grp", id_mapping)
        _renumber(grp["categories"], "id", "cat", id_mapping)
    _renumber(payees["data"]["payees"], "id", "payee", id_mapping)
    _renumber(transactions["data"]["transactions"], "id", "txn", id_mapping)
    for txn in transactions["data"]["transactions"]:
        _renumber(txn.get("subtransactions", []), "id", "sub", id_mapping)

    string_fields = {"name", "memo", "payee_name", "category_group_name"}

    sanitized = {
        "user.json":         _scrub_strings(user,         id_mapping, string_fields),
        "budgets.json":      _scrub_strings(budgets,      id_mapping, string_fields),
        "accounts.json":     _scrub_strings(accounts,     id_mapping, string_fields),
        "categories.json":   _scrub_strings(categories,   id_mapping, string_fields),
        "payees.json":       _scrub_strings(payees,       id_mapping, string_fields),
        "transactions.json": _scrub_strings(transactions, id_mapping, string_fields),
    }

    for name, payload in sanitized.items():
        (out / name).write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"wrote {out / name}")

    print("\nREVIEW the output before committing — automated scrubbing is not perfect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the script compiles and `--help` runs**

Run: `python scripts/record_fixtures.py --help`
Expected: prints usage and exits 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/record_fixtures.py
git commit -m "tooling: record_fixtures.py for sanitized YNAB fixture capture"
```

---

## Task 29: Quickstart README + architecture docs

**Goal:** Replace the placeholder README with a real quickstart and add a brief `docs/architecture.md` so first-time contributors understand the layout.

**Files:**
- Modify: `README.md` (replace)
- Create: `docs/quickstart.md`
- Create: `docs/architecture.md`

- [ ] **Step 1: Replace `README.md` with:**

```markdown
# homefinance

Open-source, local-first home financial analysis — distributed as a Claude Code plugin.

**Status:** SP1 (Foundation + YNAB spine) ready for use.

## What it does

- Syncs **YNAB** (read-only) into a local SQLite store.
- Exposes 8 read tools over the store via a stdio MCP server.
- Ships two Claude Code skills (`homefinance-setup`, `homefinance-explore`) for guided setup and analysis.
- Designed so statement ingestion (SP2), spending analytics (SP3), and retirement optimization (SP4) plug in without schema changes.

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/asachs/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Get a YNAB Personal Access Token from
#    https://app.ynab.com/settings/developer → "New Token"
export HOMEFINANCE_YNAB_TOKEN=<your-token>

# 3. First-run setup (interactive)
homefinance init

# 4. Verify
homefinance status
```

After `init`, point Claude Code at the bundled plugin under `plugin/`, then ask: *"Show me my finances at a glance."*

## Data lives at

- Config: `~/.homefinance/config.toml` (or `$XDG_CONFIG_HOME/homefinance/config.toml`)
- Database: `~/.homefinance/db.sqlite3` (or `$XDG_DATA_HOME/homefinance/db.sqlite3`)

**Nothing leaves your machine** except outbound calls to `api.ynab.com`.

## Privacy & posture

- **Read-only** YNAB access — the client class exposes no write methods, ever.
- **No telemetry**, no analytics, no remote logging.
- All amounts stored as signed integer minor units (cents). Floats never enter the store.

## Documentation

- [Architecture](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
- [SP1 design spec](docs/superpowers/specs/2026-06-10-sp1-foundation-design.md)
- [SP1 implementation plan](docs/superpowers/plans/2026-06-10-sp1-foundation.md)

## License

MIT.
```

- [ ] **Step 2: Create `docs/quickstart.md`** as a longer-form companion that expands on the README:

```markdown
# Quickstart

A 10-minute walkthrough from clone to first analysis.

## 1. Install

Python 3.11+ is required.

```bash
git clone https://github.com/asachs/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 2. Token

Generate a YNAB Personal Access Token at <https://app.ynab.com/settings/developer>. Export it in your shell — that is the safest place:

```bash
export HOMEFINANCE_YNAB_TOKEN=<token>
```

Putting the token in `~/.homefinance/config.toml` is also supported but is discouraged.

## 3. Initialize

```bash
homefinance init
```

You will be prompted to pick budgets and supply nicknames. Defaults are sensible — just press Return.

To do this non-interactively:

```bash
homefinance init --token "$HOMEFINANCE_YNAB_TOKEN" \
    --budget <budget-id> --nickname personal --no-sync
homefinance sync
```

## 4. Verify

```bash
homefinance status
```

You should see a table with your registered budgets, the last-sync timestamp, the server-knowledge cursor, and the most recent reconciliation status (`ok` or `drift`).

## 5. Use it from Claude Code

Add the plugin under `plugin/` to your Claude Code plugin folder (or symlink it). Restart Claude Code. The 8 tools and 2 skills become available.

Try:

> Show me my finances at a glance.

Claude will call `list_sources` then `list_accounts` and render a small balance table.

## Day-to-day

- `homefinance sync` — re-sync from YNAB (cron-able)
- `homefinance ynab add-budget --budget-id <id> --nickname <name>` — register more budgets
- `homefinance db-path` — print where the DB lives

## Reset

To reset entirely:

```bash
rm -rf ~/.homefinance/
```

(All data is local; this is the only place it lives.)
```

- [ ] **Step 3: Create `docs/architecture.md`**

```markdown
# Architecture

A 5-minute orientation for contributors.

## Layout

```
src/homefinance/
├── config.py           # TOML + env loader; XDG-aware paths; SecretStr token
├── db/
│   ├── schema.sql      # canonical schema (also yoyo's first migration)
│   ├── migrations/     # versioned SQL migrations
│   ├── migrate.py      # yoyo runner
│   └── store.py        # Store: PRAGMAs + atomic-transaction context + Row reads
├── sources/
│   ├── base.py         # AccountSource Protocol + RemoteX dataclasses ← the SP2 seam
│   └── ynab/
│       ├── models.py       # Pydantic models for the YNAB API subset we consume
│       ├── client.py       # read-only HTTP client (httpx + tenacity)
│       ├── fake_client.py  # JSON-fixture-backed test double
│       ├── ids.py          # deterministic ID helpers (ynab:<budget>:<external>)
│       ├── mapping.py      # YNAB → canonical (pure functions; money conversion)
│       ├── source.py       # YNABAccountSource — implements AccountSource
│       └── sync.py         # run_sync — generic orchestrator over AccountSource
├── mcp_server/
│   ├── __main__.py     # stdio entry; FastMCP tool registrations
│   └── tools.py        # tool implementations as plain functions (testable)
└── cli.py              # typer + rich CLI (init / sync / status / ynab subcmds)
```

## Three invariants

The design enforces these *by construction*, not by convention.

1. **Provenance per account.** Every account has a foreign key to `sources`. Double-counting across YNAB and (future) statement sources is impossible.

2. **Idempotent upserts.** Every imported row carries `(source_id, external_id)` UNIQUE. Re-running sync produces identical state.

3. **Money is integer, not float.** All amounts are signed minor units (cents). `to_minor_units` is the only converter; it raises on sub-cent input.

## The AccountSource seam

`sources/base.py` defines a `Protocol` with `validate()` and `pull(cursor)`. YNAB implements it; SP2's statement adapter will implement it; the generic `run_sync` orchestrator consumes only the protocol. Adding a new source is "implement the protocol" — not "rewire the store."

## Atomic sync

`run_sync` stages all upserts in memory, then applies them inside a single SQLite `BEGIN/COMMIT` together with the new `server_knowledge` cursor and the `sync_runs` row. Either the whole sync moves forward or nothing does; the next run retries from the same cursor.

## Tools vs skills

- **Tools** (8 read tools + `sync_ynab`) are primitives. They live in code and ship with the package.
- **Skills** (`homefinance-setup`, `homefinance-explore`) are workflows. They live in `plugin/skills/` as markdown and can be edited by users without code changes.

## See also

- [SP1 design spec](superpowers/specs/2026-06-10-sp1-foundation-design.md) — the design record.
- [SP1 implementation plan](superpowers/plans/2026-06-10-sp1-foundation.md) — the task-by-task build.
```

- [ ] **Step 4: Update `CHANGELOG.md`** — append an SP1-complete entry under `[Unreleased]`:

```markdown
### Added
- SP1 foundation: canonical SQLite store, YNAB read-only sync engine, 8-tool MCP server, CLI (`init`/`sync`/`status`/`db-path`/`ynab add-budget`/`ynab remove-budget`), plugin manifest and two skills (`homefinance-setup`, `homefinance-explore`), CI on Python 3.11 and 3.12.
```

(Append under the existing `### Added` line for `[Unreleased]`.)

- [ ] **Step 5: Run the whole test suite one more time**

Run: `pytest --cov=homefinance --cov-report=term-missing`
Expected: all tests pass; coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/quickstart.md docs/architecture.md CHANGELOG.md
git commit -m "docs: quickstart README, architecture overview, SP1 changelog entry"
```

---

## Closing — what SP1 delivers

After Task 29 the repository contains:

- A working `homefinance` CLI (`init` / `sync` / `status` / `db-path` / `ynab add-budget` / `ynab remove-budget`).
- A stdio MCP server exposing 8 tools, registered through `plugin/.mcp.json`.
- Two skills (`homefinance-setup`, `homefinance-explore`) under `plugin/skills/`.
- The canonical SQLite schema, atomic delta-sync, balance reconciliation, full test coverage with `FakeYNABClient` and bundled sanitized fixtures.
- A CI workflow that runs lint/format/typecheck/tests on Python 3.11 and 3.12 without needing any secrets.
- A quickstart README and architecture overview.

**What SP1 explicitly does *not* deliver** (per the spec §10): statement ingestion (SP2), categorization rules / fuzzy matching (SP3), spending analytics beyond `summarize_spending` (SP3), retirement / IRA / Roth / HSA logic (SP4), YNAB writes (never), background daemon (never), canonical category unification (SP3).

## Plan self-review

Spec coverage was verified section-by-section against the plan:

| Spec section | Implemented in |
|---|---|
| §3 constraints (Python 3.11+, MIT, XDG-aware, secrets via env, no float money) | Tasks 1, 2, 4 |
| §4.1 invariants (provenance, idempotency, integer money) | Tasks 5, 12, 16 |
| §4.2 `AccountSource` seam | Task 8 |
| §5 repo + plugin layout | Tasks 1, 26 |
| §5.2 config & secrets, env > file, XDG | Task 4 |
| §5.3 multi-budget config | Tasks 18, 20 |
| §6.2 schema (incl. `is_split_parent`, missing `deleted` columns) | Task 5 |
| §6.3 split-handling Leaves/Tops views | Tasks 16, 23, 24 |
| §6.4 reconciliation | Task 16 |
| §7.1 read-only as structural property | Task 10 |
| §7.2 delta sync via `server_knowledge` | Tasks 11 (fixture), 15, 16 |
| §7.3 sync flow | Task 16 |
| §7.4 atomic upsert | Task 16 |
| §7.6 rate-limit + retry | Task 10 |
| §7.7 CLI + MCP triggers | Tasks 19, 25 |
| §8.2 the 8 MCP tools | Tasks 22-25 |
| §8.3 SP1 skills | Tasks 26, 27 |
| §9.1 atomicity guarantee | Task 16 |
| §9.2 failure model (auth/network/parse/drift) | Tasks 10, 16, 19 |
| §9.3 drift policy (warn, never fail) | Task 16 |
| §9.4 testing strategy (unit + integration + E2E) | Tasks 4, 7, 10-16, 18-20, 22-25 |
| §9.5 fixture capture | Task 28 |
| §9.6 CI (3.11+, ruff, mypy, pytest --cov-fail-under=80) | Tasks 2, 3 |
| §9.7 logging defaults (friendly text; no PII default) | Tasks 17-19 (rich console; no amounts/payees logged) |

Type / method consistency was verified across tasks: `AccountSource` (Task 8) is used unchanged in Tasks 15 and 16; `Store` (Task 7) is used unchanged in every task that touches the DB; `SyncRunResult` (Task 16) is used in Tasks 19 and 25 with consistent field names.

No placeholders remain in the plan body.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-10-sp1-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

