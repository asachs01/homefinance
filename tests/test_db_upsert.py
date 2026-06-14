"""Targeted tests for the extracted upsert helpers. End-to-end YNAB sync still
covers their integration; these tests pin the public-shape contract of the
module so the SP2 ingest path can rely on them too.
"""

from dataclasses import replace

from homefinance.db import _upsert
from homefinance.db.store import Store
from homefinance.sources.base import RemoteAccount


def test_module_exports_expected_helpers() -> None:
    for name in (
        "utcnow",
        "upsert_account",
        "upsert_category",
        "upsert_payee",
        "upsert_transaction",
        "insert_subtransaction",
    ):
        assert hasattr(_upsert, name), f"missing {name!r}"


def _seed_source(store: Store, source_id: str = "ynab:b") -> None:
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?, ?, ?, ?, ?)",
        (source_id, "ynab", "test", None, _upsert.utcnow()),
    )


def test_upsert_account_inserts_then_updates(store: Store) -> None:
    a = RemoteAccount(
        external_id="acct-1",
        name="Checking",
        type="checking",
        on_budget=True,
        closed=False,
        deleted=False,
        currency="USD",
        cleared_balance_minor=10000,
        uncleared_balance_minor=0,
        balance_as_of=None,
    )

    with store.transaction():
        _seed_source(store)
        counters = {"accounts_touched": 0}
        _upsert.upsert_account(store, "ynab:b", a, counters)
        assert counters["accounts_touched"] == 1

    row = store.execute("SELECT name, cleared_balance_minor FROM accounts").fetchone()
    assert row["name"] == "Checking"
    assert row["cleared_balance_minor"] == 10000

    # Second call should update, not insert.
    a2 = replace(a, name="Renamed", cleared_balance_minor=20000)
    with store.transaction():
        counters2 = {"accounts_touched": 0}
        _upsert.upsert_account(store, "ynab:b", a2, counters2)
    row = store.execute("SELECT name, cleared_balance_minor FROM accounts").fetchone()
    assert row["name"] == "Renamed"
    assert row["cleared_balance_minor"] == 20000
