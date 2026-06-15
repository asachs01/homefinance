from pathlib import Path

import pytest

from homefinance.analysis.categorize import add_rule, list_rules
from homefinance.db.migrate import migrate
from homefinance.db.store import Store


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
