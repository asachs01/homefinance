from pathlib import Path

import pytest

from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.ids import make_id, source_id_for
from homefinance.sources.ynab.mapping import (
    map_account,
    map_categories,
    map_payee,
    map_transaction,
    to_minor_units,
)


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
