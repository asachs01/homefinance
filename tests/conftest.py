"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tiny_fixtures_dir() -> Path:
    return FIXTURES / "ynab" / "tiny"


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
