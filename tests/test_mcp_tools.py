from pathlib import Path

import pytest

from homefinance.db.store import Store
from homefinance.mcp_server.tools import (
    get_account,
    list_accounts,
    list_categories,
    list_sources,
    query_transactions,
    summarize_spending,
)
from homefinance.sources.ynab.fake_client import FakeYNABClient
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync


@pytest.fixture
def synced_store(store: Store, tiny_fixtures_dir: Path) -> Store:
    src = YNABAccountSource("budget-tiny", FakeYNABClient(tiny_fixtures_dir), nickname="tiny")
    run_sync(src, store)
    return store


def test_list_sources_returns_registered_budgets(synced_store: Store) -> None:
    rows = list_sources(synced_store)
    assert len(rows) == 1
    r = rows[0]
    assert r["source_id"] == "ynab:budget-tiny"
    assert r["kind"] == "ynab"
    assert r["nickname"] == "tiny"
    assert r["last_sync_at"] is not None
    assert r["last_reconciliation"] in ("ok", "drift")


def test_list_accounts_returns_all_when_no_filter(synced_store: Store) -> None:
    rows = list_accounts(synced_store)
    assert {r["external_id"] for r in rows} == {"acct-checking", "acct-credit"}
    checking = next(r for r in rows if r["external_id"] == "acct-checking")
    assert checking["cleared_balance_minor"] == 123456


def test_list_accounts_filters_by_source(synced_store: Store) -> None:
    rows = list_accounts(synced_store, source_id="ynab:nope")
    assert rows == []


def test_list_accounts_hides_closed_by_default(synced_store: Store) -> None:
    synced_store.execute("UPDATE accounts SET closed = 1 WHERE external_id = ?", ("acct-credit",))
    rows = list_accounts(synced_store)
    assert {r["external_id"] for r in rows} == {"acct-checking"}
    rows_all = list_accounts(synced_store, include_closed=True)
    assert {r["external_id"] for r in rows_all} == {"acct-checking", "acct-credit"}


def test_get_account_includes_latest_reconciliation(synced_store: Store) -> None:
    r = get_account(synced_store, account_id="ynab:budget-tiny:acct-checking")
    assert r["name"] == "Checking"
    assert "reconciliation" in r


def test_get_account_raises_for_unknown(synced_store: Store) -> None:
    with pytest.raises(KeyError, match="not found"):
        get_account(synced_store, account_id="ynab:budget-tiny:nope")


def test_list_categories_filters_hidden(synced_store: Store) -> None:
    synced_store.execute("UPDATE categories SET hidden = 1 WHERE external_id = ?", ("cat-dining",))
    visible = {c["external_id"] for c in list_categories(synced_store)}
    assert "cat-dining" not in visible
    all_cats = {c["external_id"] for c in list_categories(synced_store, include_hidden=True)}
    assert "cat-dining" in all_cats


def test_query_transactions_leaves_default_excludes_split_parent(synced_store: Store) -> None:
    rows = query_transactions(synced_store)
    ext_ids = {r["external_id"] for r in rows}
    # Leaves view: parents excluded, children included.
    assert "txn-split" not in ext_ids
    assert any(":sub:" in eid for eid in ext_ids)
    # Sum over leaves should match sum over tops.
    leaves_total = sum(r["amount_minor"] for r in rows)
    tops_total = sum(r["amount_minor"] for r in query_transactions(synced_store, mode="tops"))
    assert leaves_total == tops_total


def test_query_transactions_tops_includes_split_parent_not_children(synced_store: Store) -> None:
    rows = query_transactions(synced_store, mode="tops")
    ext_ids = {r["external_id"] for r in rows}
    assert "txn-split" in ext_ids
    assert not any(":sub:" in eid for eid in ext_ids)


def test_query_transactions_filters_by_date_range(synced_store: Store) -> None:
    rows = query_transactions(synced_store, date_from="2026-06-02", date_to="2026-06-02")
    dates = {r["date"] for r in rows}
    assert dates == {"2026-06-02"}


def test_query_transactions_excludes_deleted_by_default(synced_store: Store) -> None:
    synced_store.execute("UPDATE transactions SET deleted = 1 WHERE external_id = 'txn-non-split'")
    rows = query_transactions(synced_store)
    assert all(r["external_id"] != "txn-non-split" for r in rows)
    rows_all = query_transactions(synced_store, include_deleted=True)
    assert any(r["external_id"] == "txn-non-split" for r in rows_all)


def test_query_transactions_filters_by_amount_range(synced_store: Store) -> None:
    rows = query_transactions(synced_store, amount_max_minor=-3000)
    assert all(r["amount_minor"] <= -3000 for r in rows)


def test_query_transactions_filters_by_payee_substring(synced_store: Store) -> None:
    rows = query_transactions(synced_store, payee_contains="Trader")
    assert all("Trader" in (r["payee"] or "") for r in rows)


def test_query_transactions_limit_and_offset(synced_store: Store) -> None:
    page1 = query_transactions(synced_store, limit=1, offset=0)
    page2 = query_transactions(synced_store, limit=1, offset=1)
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]


def test_summarize_by_category_uses_leaves_view(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="category")
    by_key = {r["key"]: r for r in rows}
    # YNAB milliunits → minor (cents): non-split groceries -4567, split gas
    # -4000, split groceries -1000. Leaves groceries total = -4567 + -1000.
    assert by_key["Groceries"]["total_minor"] == -5567
    assert by_key["Gas"]["total_minor"] == -4000


def test_summarize_by_month(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="month")
    assert any(r["key"] == "2026-06" for r in rows)


def test_summarize_by_account(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="account")
    by_key = {r["key"]: r for r in rows}
    assert "Checking" in by_key
    assert by_key["Checking"]["count"] > 0


def test_summarize_by_payee(synced_store: Store) -> None:
    rows = summarize_spending(synced_store, group_by="payee")
    assert any(r["key"] == "Trader Joe's" for r in rows)


def test_summarize_invalid_group_by_raises(synced_store: Store) -> None:
    with pytest.raises(ValueError):
        summarize_spending(synced_store, group_by="banana")


from homefinance.mcp_server.tools import get_sync_status, sync_ynab_all  # noqa: E402


def test_get_sync_status_returns_per_source_summary(synced_store: Store) -> None:
    rows = get_sync_status(synced_store)
    assert len(rows) == 1
    r = rows[0]
    assert r["source_id"] == "ynab:budget-tiny"
    assert r["last_sync_at"] is not None
    assert r["last_reconciliation"] in ("ok", "drift")
    assert "drift_account_count" in r


def test_sync_ynab_all_runs_for_each_budget(store: Store, tiny_fixtures_dir: Path) -> None:
    fake = FakeYNABClient(tiny_fixtures_dir)
    sources = [YNABAccountSource("budget-tiny", fake, nickname="tiny")]
    results = sync_ynab_all(store, sources)
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["source_id"] == "ynab:budget-tiny"
    assert "reconciliation" in results[0]


from homefinance.sources.statement.ingest import (  # noqa: E402
    confirm_batch,
    ingest_file,
    register_account,
)


def _setup_citi_cc_template(store, tmp_path) -> tuple[Path, Path]:
    """Register a citi-cc account, write its CSV template, and return
    ``(config_dir, fixture_csv)`` for use by an ingest call."""
    register_account(store, nickname="citi-cc", type="credit_card", currency="USD")
    config_dir = tmp_path / "homefinance"
    (config_dir / "templates").mkdir(parents=True)
    (config_dir / "templates" / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n[columns]\n'
        'date = "Transaction Date"\namount = "Amount"\npayee = "Description"\nmemo = "Notes"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\nsign = "natural"\n'
    )
    fixture = Path(__file__).resolve().parent / "fixtures" / "statement" / "tiny.csv"
    return config_dir, fixture


def _stage_pending_csv(store, tmp_path, tiny_fixtures_dir):
    """Helper: register an account and stage a pending CSV batch."""
    config_dir, fixture = _setup_citi_cc_template(store, tmp_path)
    return ingest_file(
        store,
        path=fixture,
        account_nickname="citi-cc",
        config_dir=config_dir,
        archive_dir=tmp_path / "archive",
    )


def test_query_transactions_excludes_pending_by_default(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    rows = query_transactions(synced_store)
    # YNAB rows are present; statement pending rows should not be.
    statuses = {r.get("status", "confirmed") for r in rows}
    assert statuses == {"confirmed"} or all(r.get("status") != "pending_review" for r in rows)


def test_query_transactions_includes_pending_when_opted_in(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    confirmed_only = query_transactions(synced_store)
    with_pending = query_transactions(synced_store, include_pending=True)
    assert len(with_pending) > len(confirmed_only)


def test_summarize_spending_always_excludes_pending(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    preview = _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    before_total = sum(
        r["total_minor"] for r in summarize_spending(synced_store, group_by="account")
    )
    confirm_batch(synced_store, preview.batch_id)
    after_total = sum(
        r["total_minor"] for r in summarize_spending(synced_store, group_by="account")
    )
    assert after_total != before_total


def test_get_sync_status_includes_pending_batch_count(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    _stage_pending_csv(synced_store, tmp_path, tiny_fixtures_dir)
    statuses = get_sync_status(synced_store)
    by_id = {s["source_id"]: s for s in statuses}
    assert "pending_batch_count" in by_id["statement:citi-cc"]
    assert by_id["statement:citi-cc"]["pending_batch_count"] == 1


from homefinance.mcp_server.tools import confirm_batch as mcp_confirm_batch  # noqa: E402
from homefinance.mcp_server.tools import ingest_statement as mcp_ingest_statement  # noqa: E402
from homefinance.mcp_server.tools import list_batches as mcp_list_batches  # noqa: E402
from homefinance.mcp_server.tools import reject_batch as mcp_reject_batch  # noqa: E402


def _mcp_ingest_citi_cc(store, tmp_path, *, archive: bool = True) -> dict:
    """Run the citi-cc CSV through ``mcp_ingest_statement`` and return the preview dict."""
    config_dir, fixture = _setup_citi_cc_template(store, tmp_path)
    return mcp_ingest_statement(
        store,
        path=str(fixture),
        account_nickname="citi-cc",
        config_dir=str(config_dir),
        archive_dir=str(tmp_path / "archive"),
        archive=archive,
    )


def test_mcp_ingest_statement_returns_preview_dict(synced_store: Store, tmp_path: Path) -> None:
    result = _mcp_ingest_citi_cc(synced_store, tmp_path)
    assert result["batch_id"] >= 1
    assert result["txn_count"] == 3
    assert "first_transactions" in result


def test_mcp_list_batches(synced_store: Store) -> None:
    rows = mcp_list_batches(synced_store, review_status="pending")
    assert isinstance(rows, list)


def test_mcp_confirm_batch(synced_store: Store, tmp_path: Path) -> None:
    preview = _mcp_ingest_citi_cc(synced_store, tmp_path)
    result = mcp_confirm_batch(synced_store, batch_id=preview["batch_id"])
    assert result["review_status"] == "confirmed"


def test_mcp_reject_batch(synced_store: Store, tmp_path: Path) -> None:
    preview = _mcp_ingest_citi_cc(synced_store, tmp_path)
    result = mcp_reject_batch(synced_store, batch_id=preview["batch_id"])
    assert result["review_status"] == "rejected"


def test_summarize_spending_by_canonical_category(
    synced_store: Store, tmp_path: Path, tiny_fixtures_dir: Path
) -> None:
    from homefinance.analysis.categorize import apply_categorization

    apply_categorization(synced_store)  # YNAB rows get canonical names
    rows = summarize_spending(synced_store, group_by="canonical_category")
    keys = {r["key"] for r in rows}
    # tiny YNAB fixture has Groceries/Gas categories on its rows
    assert "Groceries" in keys
