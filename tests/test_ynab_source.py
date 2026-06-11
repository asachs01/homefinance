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
        "txn-non-split",
        "txn-split",
        "txn-transfer",
    }
    assert delta.new_cursor == 100


def test_pull_with_cursor_returns_delta_set(source: YNABAccountSource) -> None:
    delta = source.pull(cursor=100)
    # tiny fixtures' transactions_delta.json carries the changed txns
    assert {t.external_id for t in delta.transactions} == {"txn-non-split", "txn-transfer"}
    assert delta.new_cursor == 150
