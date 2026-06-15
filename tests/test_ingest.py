from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.statement.ingest import (
    AccountAlreadyRegistered,
    compute_file_hash,
    reconcile,
    register_account,
    resolve_account,
    row_external_id,
)
from homefinance.sources.statement.parsers.base import AccountNotConfigured


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "ingest.sqlite3"
    migrate(db)
    return Store.open(db)


def test_register_account_creates_source_and_account_rows(store: Store) -> None:
    register_account(
        store,
        nickname="citi-cc",
        type="credit_card",
        currency="USD",
        display_name="Citi Credit Card",
    )
    src = store.execute("SELECT id, kind, nickname FROM sources").fetchone()
    assert src["id"] == "statement:citi-cc"
    assert src["kind"] == "statement"
    assert src["nickname"] == "Citi Credit Card"

    acct = store.execute(
        "SELECT id, source_id, external_id, name, type FROM accounts"
    ).fetchone()
    assert acct["id"] == "statement:citi-cc:account"
    assert acct["source_id"] == "statement:citi-cc"
    assert acct["external_id"] == "account"
    assert acct["name"] == "Citi Credit Card"
    assert acct["type"] == "credit_card"


def test_register_account_twice_raises(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    with pytest.raises(AccountAlreadyRegistered):
        register_account(store, nickname="citi-cc", type="credit_card", currency="USD")


def test_resolve_account_returns_resolved_account(store: Store) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    ra = resolve_account(store, "citi-cc")
    assert ra.source_id == "statement:citi-cc"
    assert ra.account_id == "statement:citi-cc:account"
    assert ra.type == "credit_card"
    assert ra.currency == "USD"


def test_resolve_account_unknown_nickname_raises(store: Store) -> None:
    with pytest.raises(AccountNotConfigured, match="nope"):
        resolve_account(store, "nope")


def test_compute_file_hash_is_stable(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    a.write_bytes(b"hello world")
    h1 = compute_file_hash(a)
    h2 = compute_file_hash(a)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    b = tmp_path / "b.bin"
    b.write_bytes(b"hello world!")
    assert compute_file_hash(b) != h1


def test_row_external_id_collides_for_identical_rows() -> None:
    a = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", None)
    b = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", None)
    assert a == b
    c = row_external_id("statement:x:account", "2026-06-01", -1000, "Shop", "diff memo")
    assert c != a


def test_reconcile_ok_when_balances_match() -> None:
    status, drift = reconcile(opening=100000, closing=99500, txn_total=-500)
    assert status == "ok"
    assert drift is None


def test_reconcile_drift_when_mismatch() -> None:
    status, drift = reconcile(opening=100000, closing=99500, txn_total=-450)
    assert status == "drift"
    assert drift == 50  # actual(-450) - expected(-500)


def test_reconcile_na_when_balance_missing() -> None:
    status, drift = reconcile(opening=None, closing=99500, txn_total=-500)
    assert status == "n/a"
    assert drift is None
