from pathlib import Path

import pytest

from homefinance.analysis.categorize import (
    add_rule,
    apply_categorization,
    list_rules,
)
from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.statement.ingest import ingest_file, register_account
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync


@pytest.fixture
def store(tmp_path: Path) -> Store:
    db = tmp_path / "cat.sqlite3"
    migrate(db)
    return Store.open(db)


def test_add_rule_inserts_and_returns_id(store: Store) -> None:
    rid = add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern="TRADER JOE",
        is_regex=False,
        canonical_category="Groceries",
    )
    assert isinstance(rid, int) and rid >= 1
    rows = list_rules(store)
    assert len(rows) == 1
    assert rows[0]["pattern"] == "TRADER JOE"
    assert rows[0]["canonical_category"] == "Groceries"
    assert rows[0]["match_field"] == "payee"
    assert rows[0]["is_regex"] == 0


def test_list_rules_ordered_by_priority_then_id(store: Store) -> None:
    add_rule(
        store,
        priority=20,
        match_field="payee",
        pattern="B",
        is_regex=False,
        canonical_category="X",
    )
    add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern="A",
        is_regex=False,
        canonical_category="Y",
    )
    add_rule(
        store,
        priority=10,
        match_field="memo",
        pattern="C",
        is_regex=False,
        canonical_category="Z",
    )
    patterns = [r["pattern"] for r in list_rules(store)]
    assert patterns == ["A", "C", "B"]  # priority 10 (A then C by id), then 20 (B)


def test_add_rule_rejects_bad_match_field(store: Store) -> None:
    with pytest.raises(ValueError, match="match_field"):
        add_rule(
            store,
            priority=1,
            match_field="banana",
            pattern="x",
            is_regex=False,
            canonical_category="X",
        )


def test_add_rule_rejects_invalid_regex(store: Store) -> None:
    with pytest.raises(ValueError, match="regex"):
        add_rule(
            store,
            priority=1,
            match_field="payee",
            pattern="(unclosed",
            is_regex=True,
            canonical_category="X",
        )


def test_add_rule_rejects_empty_pattern_or_category(store: Store) -> None:
    with pytest.raises(ValueError):
        add_rule(
            store,
            priority=1,
            match_field="payee",
            pattern="",
            is_regex=False,
            canonical_category="X",
        )
    with pytest.raises(ValueError):
        add_rule(
            store,
            priority=1,
            match_field="payee",
            pattern="x",
            is_regex=False,
            canonical_category="",
        )


def _seed_mixed_store(store: Store, tmp_path: Path, tiny_fixtures_dir: Path) -> None:
    """YNAB rows (categorized) + statement rows (uncategorized)."""
    run_sync(
        YNABAccountSource("budget-tiny", FakeYNABClient(tiny_fixtures_dir), nickname="tiny"),
        store,
    )
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    cfg_dir = tmp_path / "homefinance"
    (cfg_dir / "templates").mkdir(parents=True)
    (cfg_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\n'
        'payee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    ingest_file(
        store,
        path=fixture,
        account_nickname="citi-cc",
        config_dir=cfg_dir,
        archive_dir=tmp_path / "archive",
    )


def test_apply_derives_ynab_categories_from_names(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    result = apply_categorization(store)
    # YNAB non-split row txn-non-split has category cat-groceries → "Groceries".
    row = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE external_id = 'txn-non-split'"
    ).fetchone()
    assert row["canonical_category"] == "Groceries"
    assert row["category_source"] == "ynab"
    assert result["ynab"] >= 1


def test_apply_fills_statement_rows_from_rules(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern="Trader Joe",
        is_regex=False,
        canonical_category="Groceries",
    )
    apply_categorization(store)
    # The statement row whose payee is "Trader Joe's" gets the rule's category.
    rows = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = \"Trader Joe's\""
    ).fetchall()
    assert rows, "expected at least one statement Trader Joe's row"
    assert all(r["canonical_category"] == "Groceries" for r in rows)
    assert all(r["category_source"] == "rule" for r in rows)


def test_apply_is_idempotent(store: Store, tmp_path: Path, tiny_fixtures_dir: Path) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern="Shell",
        is_regex=False,
        canonical_category="Gas",
    )
    first = apply_categorization(store)
    second = apply_categorization(store)
    assert first == second


def test_apply_respects_manual_then_reapplies_rules(
    store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    # Manually pin a statement row.
    store.execute(
        "UPDATE transactions SET canonical_category = 'Special', category_source = 'manual' "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Shell'"
    )
    # A rule that would otherwise capture Shell.
    add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern="Shell",
        is_regex=False,
        canonical_category="Gas",
    )
    apply_categorization(store)
    row = store.execute(
        "SELECT canonical_category, category_source FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Shell'"
    ).fetchone()
    assert row["canonical_category"] == "Special"  # manual stuck
    assert row["category_source"] == "manual"


def test_apply_regex_rule_matches(store: Store, tmp_path: Path, tiny_fixtures_dir: Path) -> None:
    _seed_mixed_store(store, tmp_path, tiny_fixtures_dir)
    add_rule(
        store,
        priority=10,
        match_field="payee",
        pattern=r"^Payment\b",
        is_regex=True,
        canonical_category="Transfer",
    )
    apply_categorization(store)
    row = store.execute(
        "SELECT canonical_category FROM transactions "
        "WHERE source_id = 'statement:citi-cc' AND payee = 'Payment'"
    ).fetchone()
    assert row["canonical_category"] == "Transfer"
