from datetime import UTC, datetime
from pathlib import Path

import pytest

from homefinance.analysis.recurring import detect_recurring
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "rec.sqlite3"
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


def _txn(store: Store, ext: str, date: str, amount: int, payee: str) -> None:
    store.execute(
        "INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, "
        "currency, payee, payee_id, memo, category_id, cleared, approved, flag_color, import_id, "
        "transfer_account_id, parent_id, is_split_parent, deleted, raw, synced_at, status, batch_id) "
        "VALUES (?, 's:a', ?, 's:a:account', ?, ?, 'USD', ?, NULL, NULL, NULL, NULL, 1, NULL, NULL, "
        "NULL, NULL, 0, 0, NULL, '2026-01-01T00:00:00+00:00', 'confirmed', NULL)",
        (f"s:a:{ext}", ext, date, amount, payee),
    )


def test_detect_recurring_monthly_series(store: Store) -> None:
    _seed(store)
    # A clean monthly subscription, 4 occurrences ~30 days apart.
    for i, d in enumerate(["2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]):
        _txn(store, f"net{i}", d, -1599, "Netflix")
    series = detect_recurring(store, min_occurrences=3)
    netflix = next(s for s in series if s["payee"] == "Netflix")
    assert netflix["occurrences"] == 4
    assert netflix["typical_amount_minor"] == -1599
    assert netflix["cadence"] == "monthly"
    assert netflix["next_expected"] >= "2026-06-25"  # ~one month after last
    assert netflix["confidence"] > 0.5


def test_detect_recurring_ignores_too_few_occurrences(store: Store) -> None:
    _seed(store)
    _txn(store, "a", "2026-05-01", -500, "OneOff")
    _txn(store, "b", "2026-06-01", -500, "OneOff")  # only 2
    series = detect_recurring(store, min_occurrences=3)
    assert all(s["payee"] != "OneOff" for s in series)


def test_detect_recurring_ignores_irregular(store: Store) -> None:
    _seed(store)
    # Same payee+amount but wildly irregular gaps.
    for i, d in enumerate(["2026-01-01", "2026-01-03", "2026-06-01"]):
        _txn(store, f"x{i}", d, -1000, "Random")
    series = detect_recurring(store, min_occurrences=3)
    rec = [s for s in series if s["payee"] == "Random"]
    # Either excluded, or surfaced with low confidence — never a clean cadence.
    assert not rec or rec[0]["confidence"] < 0.5


def test_detect_recurring_empty_store(store: Store) -> None:
    assert detect_recurring(store) == []
