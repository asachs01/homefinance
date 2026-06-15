from pathlib import Path

import pytest

from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.statement.ingest import (
    AccountAlreadyRegistered,
    BatchPreview,
    compute_file_hash,
    ingest_file,
    reconcile,
    register_account,
    resolve_account,
    row_external_id,
)
from homefinance.sources.statement.parsers.base import (
    AccountNotConfigured,
    FileAlreadyIngested,
)


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


def test_ingest_file_csv_stages_pending_batch(store: Store, tmp_path: Path) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    # Write template to a tmp config dir.
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\n'
        'amount = "Amount"\n'
        'payee = "Description"\n'
        'memo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\n'
        'sign = "natural"\n'
    )

    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    archive_dir = tmp_path / "archive"

    preview = ingest_file(
        store,
        path=fixture,
        account_nickname="citi-cc",
        config_dir=config_dir,
        archive_dir=archive_dir,
    )

    assert isinstance(preview, BatchPreview)
    assert preview.txn_count == 3
    assert preview.source_id == "statement:citi-cc"
    assert preview.reconciliation_status == "n/a"  # CSV has no balances
    assert preview.file_path_archive is not None
    assert Path(preview.file_path_archive).exists()

    # Pending rows in transactions
    rows = store.execute(
        "SELECT status, batch_id FROM transactions WHERE batch_id = ?",
        (preview.batch_id,),
    ).fetchall()
    assert len(rows) == 3
    assert {r["status"] for r in rows} == {"pending_review"}

    # statement_batches row exists with review_status='pending'
    batch = store.execute(
        "SELECT review_status, txn_count, file_hash FROM statement_batches WHERE id = ?",
        (preview.batch_id,),
    ).fetchone()
    assert batch["review_status"] == "pending"
    assert batch["txn_count"] == 3


def test_ingest_file_blocks_re_ingest_of_same_file(store: Store, tmp_path: Path) -> None:
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\namount = "Amount"\npayee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    archive_dir = tmp_path / "archive"

    ingest_file(
        store,
        path=fixture,
        account_nickname="citi-cc",
        config_dir=config_dir,
        archive_dir=archive_dir,
    )

    with pytest.raises(FileAlreadyIngested, match="already ingested"):
        ingest_file(
            store,
            path=fixture,
            account_nickname="citi-cc",
            config_dir=config_dir,
            archive_dir=archive_dir,
        )


def test_ingest_file_reconciles_when_balances_present(store: Store, tmp_path: Path) -> None:
    """Use the Docling cells.json fixture via FakeDoclingPDFParser to exercise
    the balance-known reconciliation path. We pass the fixture path with a
    .json extension; the fake parser is registered ad-hoc for this test."""
    from homefinance.sources.statement.parsers import _REGISTRY, register

    register_account(store, nickname="wells", type="checking", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:wells.toml").write_text(
        'parser = "docling_pdf"\n'
        "[columns]\ndate = 0\npayee = 1\namount = 2\n"
        '[options]\ndate_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    cells = Path(__file__).resolve().parent / "fixtures" / "docling" / "tiny-pdf" / "cells.json"

    original = list(_REGISTRY)
    _REGISTRY.clear()
    register(".json", "homefinance.sources.statement.parsers.docling_pdf:FakeDoclingPDFParser")
    try:
        preview = ingest_file(
            store,
            path=cells,
            account_nickname="wells",
            config_dir=config_dir,
            archive_dir=tmp_path / "archive",
        )
    finally:
        _REGISTRY.clear()
        _REGISTRY.extend(original)

    # cells.json sum is -45.67 + -50.00 + 10.00 = -85.67 = -8567 cents.
    # opening 1234560, closing 1100000, expected delta -134560.
    # drift = -8567 - (-134560) = 125993.
    assert preview.reconciliation_status == "drift"
    assert preview.drift_minor == 125993
