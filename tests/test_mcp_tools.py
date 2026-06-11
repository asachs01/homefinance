from pathlib import Path

import pytest

from homefinance.db.store import Store
from homefinance.mcp_server.tools import (
    get_account,
    list_accounts,
    list_categories,
    list_sources,
)
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource
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
    synced_store.execute("UPDATE accounts SET closed = 1 WHERE external_id = ?", ("acct-credit",))
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
    synced_store.execute("UPDATE categories SET hidden = 1 WHERE external_id = ?", ("cat-dining",))
    visible = {c["external_id"] for c in list_categories(synced_store)}
    assert "cat-dining" not in visible
    all_cats = {c["external_id"] for c in list_categories(synced_store, include_hidden=True)}
    assert "cat-dining" in all_cats
