from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.base import AccountSource, SyncDelta
from homefinance.sources.statement.ingest import register_account
from homefinance.sources.statement.parsers.base import AccountNotConfigured
from homefinance.sources.statement.source import StatementAccountSource


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "ss.sqlite3"
    migrate(db)
    return Store.open(db)


def test_satisfies_account_source_protocol(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    assert isinstance(src, AccountSource)
    assert src.source_id == "statement:citi-cc"
    assert src.kind == "statement"
    assert src.nickname == "citi-cc"


def test_validate_passes_for_registered_account(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    src.validate()


def test_validate_raises_for_unregistered_account(store: Store) -> None:
    src = StatementAccountSource(store=store, nickname="nope")
    with pytest.raises(AccountNotConfigured):
        src.validate()


def test_pull_returns_empty_sync_delta(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    src = StatementAccountSource(store=store, nickname="citi-cc")
    delta = src.pull(cursor=None)
    assert isinstance(delta, SyncDelta)
    assert delta.accounts == ()
    assert delta.transactions == ()
    assert delta.new_cursor is None
