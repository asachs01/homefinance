from datetime import UTC, datetime
from pathlib import Path

import pytest

from homefinance.analysis.cashflow import cash_flow
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "cf.sqlite3"
    migrate(db)
    return Store.open(db)


def _src_and_acct(store: Store) -> None:
    now = datetime.now(UTC).isoformat()
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES (?,?,?,?,?)",
        ("s:a", "statement", "a", None, now),
    )
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, closed, "
        "deleted, currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, "
        "last_synced_at) VALUES ('s:a:account','s:a','account','A','checking',1,0,0,'USD',"
        "NULL,NULL,NULL,NULL)",
    )


def _txn(store: Store, ext: str, date: str, amount: int, *, transfer: str | None = None) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', 'P', NULL, NULL, NULL, NULL, 1, NULL, "
        "NULL, ?, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL)",
        (f"s:a:{ext}", ext, date, amount, transfer),
    )


def test_cash_flow_inflow_outflow_net_by_month(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", 200000)  # +2000 income
    _txn(store, "t2", "2026-06-05", -45670)  # -456.70 outflow
    _txn(store, "t3", "2026-07-02", -10000)  # next month
    rows = cash_flow(store, group_by="month")
    by_period = {r["period"]: r for r in rows}
    assert by_period["2026-06"]["inflow_minor"] == 200000
    assert by_period["2026-06"]["outflow_minor"] == -45670
    assert by_period["2026-06"]["net_minor"] == 154330
    assert by_period["2026-07"]["net_minor"] == -10000


def test_cash_flow_excludes_transfers(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", -50000)  # real outflow
    _txn(store, "t2", "2026-06-02", -20000, transfer="s:a:account")  # transfer — excluded
    rows = cash_flow(store, group_by="month")
    assert rows[0]["outflow_minor"] == -50000  # transfer not counted


def test_cash_flow_date_range_filter(store: Store) -> None:
    _src_and_acct(store)
    _txn(store, "t1", "2026-06-01", -100)
    _txn(store, "t2", "2026-07-01", -200)
    rows = cash_flow(store, date_from="2026-07-01", date_to="2026-07-31")
    assert len(rows) == 1
    assert rows[0]["period"] == "2026-07"


def test_cash_flow_empty_store_returns_empty(store: Store) -> None:
    assert cash_flow(store) == []
