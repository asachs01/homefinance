from datetime import UTC, datetime
from pathlib import Path

import pytest

from homefinance.analysis.anomaly import detect_anomalies
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "anom.sqlite3"
    migrate(db)
    return Store.open(db)


def _seed(store: Store) -> None:
    now = datetime.now(UTC).isoformat()
    store.execute(
        "INSERT INTO sources (id, kind, nickname, config, created_at) VALUES ('s:a','statement','a',NULL,?)",
        (now,),
    )
    store.execute(
        "INSERT INTO accounts (id, source_id, external_id, name, type, on_budget, closed, deleted, "
        "currency, cleared_balance_minor, uncleared_balance_minor, balance_as_of, last_synced_at) "
        "VALUES ('s:a:account','s:a','account','A','checking',1,0,0,'USD',NULL,NULL,NULL,NULL)",
    )


def _txn(store: Store, ext: str, date: str, amount: int, cat: str) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id, "
        "canonical_category, category_source) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', 'P', NULL, NULL, NULL, NULL, 1, NULL, NULL, "
        "NULL, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL, ?, 'manual')",
        (f"s:a:{ext}", ext, date, amount, cat),
    )


def test_detect_anomalies_flags_category_month_spike(store: Store) -> None:
    _seed(store)
    # Five quiet months with realistic month-to-month variance (~ -100/mo),
    # then a -5000 blowout. Non-identical so the baseline stdev is non-zero.
    quiet = {
        "2026-01": -9000,
        "2026-02": -11000,
        "2026-03": -10000,
        "2026-04": -9500,
        "2026-05": -10500,
    }
    for i, (m, amt) in enumerate(quiet.items()):
        _txn(store, f"d{i}", f"{m}-15", amt, "Dining")
    _txn(store, "spike", "2026-06-15", -500000, "Dining")
    flags = detect_anomalies(store, trailing_months=6, z_threshold=2.0)
    dining = [f for f in flags if f["canonical_category"] == "Dining" and f["period"] == "2026-06"]
    assert dining, "expected June Dining spike to be flagged"


def test_detect_anomalies_skips_insufficient_history(store: Store) -> None:
    _seed(store)
    _txn(store, "a", "2026-06-15", -999999, "Sparse")  # only one month of data
    flags = detect_anomalies(store)
    assert all(f["canonical_category"] != "Sparse" for f in flags)


def test_detect_anomalies_empty_store(store: Store) -> None:
    assert detect_anomalies(store) == []
