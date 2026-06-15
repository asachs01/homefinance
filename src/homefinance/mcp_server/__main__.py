"""Stdio MCP server for homefinance.

Launch via ``python -m homefinance.mcp_server``. The plugin's ``.mcp.json``
registers this command. State (Store, YNAB client) is lazy-initialized on
first tool call so import is side-effect-free.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from homefinance.config import Config, load_config
from homefinance.db.store import Store

mcp = FastMCP("homefinance")

_cfg: Config | None = None
_store: Store | None = None


def _cfg_cached() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def _store_cached() -> Store:
    global _store
    if _store is None:
        _store = Store.open(_cfg_cached().db_path)
    return _store


# Tools are registered in Tasks 22-25 — each task appends `@mcp.tool()`
# wrappers below that import their implementation from
# `homefinance.mcp_server.tools` and call it with the cached store / config.


from homefinance.mcp_server import tools as _tools  # noqa: E402 — after FastMCP init


@mcp.tool()
def list_sources() -> list[dict]:  # type: ignore[type-arg]
    """Registered budgets with last-sync info."""
    return _tools.list_sources(_store_cached())


@mcp.tool()
def list_accounts(source_id: str | None = None, include_closed: bool = False) -> list[dict]:  # type: ignore[type-arg]
    """Accounts across (or within) budgets; hides closed by default."""
    return _tools.list_accounts(_store_cached(), source_id=source_id, include_closed=include_closed)


@mcp.tool()
def get_account(account_id: str) -> dict:  # type: ignore[type-arg]
    """Single account detail plus the latest reconciliation status."""
    return _tools.get_account(_store_cached(), account_id=account_id)


@mcp.tool()
def list_categories(source_id: str | None = None, include_hidden: bool = False) -> list[dict]:  # type: ignore[type-arg]
    """Categories per source; hides hidden by default."""
    return _tools.list_categories(
        _store_cached(), source_id=source_id, include_hidden=include_hidden
    )


@mcp.tool()
def query_transactions(
    source_id: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category_id: str | None = None,
    payee_contains: str | None = None,
    amount_min_minor: int | None = None,
    amount_max_minor: int | None = None,
    cleared: str | None = None,
    include_deleted: bool = False,
    include_pending: bool = False,
    mode: str = "leaves",
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:  # type: ignore[type-arg]
    """List transactions. ``mode='leaves'`` (default) gives the analysis view;
    ``mode='tops'`` gives the user-facing 'one transaction per split' view.
    ``include_pending=True`` includes statement rows awaiting review."""
    return _tools.query_transactions(
        _store_cached(),
        source_id=source_id,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        payee_contains=payee_contains,
        amount_min_minor=amount_min_minor,
        amount_max_minor=amount_max_minor,
        cleared=cleared,
        include_deleted=include_deleted,
        include_pending=include_pending,
        mode=mode,  # type: ignore[arg-type]
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def summarize_spending(
    source_id: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    payee_contains: str | None = None,
    cleared: str | None = None,
    group_by: str = "category",
) -> list[dict]:  # type: ignore[type-arg]
    """Aggregate spending. ``group_by ∈ {category, canonical_category, payee, month, account, day_of_week}``.

    Prefer ``canonical_category`` for cross-source views (it unifies YNAB + statement categories)."""
    return _tools.summarize_spending(
        _store_cached(),
        source_id=source_id,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        payee_contains=payee_contains,
        cleared=cleared,
        group_by=group_by,  # type: ignore[arg-type]
    )


from typing import cast as _cast  # noqa: E402

from homefinance.sources.base import AccountSource as _AccountSource  # noqa: E402
from homefinance.sources.ynab.client import YNABClient as _YNABClient  # noqa: E402
from homefinance.sources.ynab.source import (  # noqa: E402
    YNABAccountSource as _YNABAccountSource,
)


def _ynab_sources(cfg: Config) -> list[_YNABAccountSource]:
    if cfg.ynab_token is None:
        raise RuntimeError("No YNAB token configured. Set HOMEFINANCE_YNAB_TOKEN or [ynab].token.")
    client = _YNABClient(token=cfg.ynab_token.get_secret_value())
    return [_YNABAccountSource(b.budget_id, client, nickname=b.nickname) for b in cfg.ynab.budgets]


@mcp.tool()
def get_sync_status() -> list[dict]:  # type: ignore[type-arg]
    """Per-source last-sync + drift summary."""
    return _tools.get_sync_status(_store_cached())


@mcp.tool()
def sync_ynab(source_id: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    """Sync one (`source_id` set) or all configured YNAB budgets."""
    cfg = _cfg_cached()
    sources: list[_YNABAccountSource] = _ynab_sources(cfg)
    if source_id is not None:
        sources = [s for s in sources if s.source_id == source_id]
        if not sources:
            raise ValueError(f"source {source_id!r} not configured")
    return _tools.sync_ynab_all(_store_cached(), [_cast(_AccountSource, s) for s in sources])


@mcp.tool()
def ingest_statement(
    path: str,
    account_nickname: str,
    archive: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Parse + stage one statement file. Returns the BatchPreview as a dict."""
    cfg_dir = _cfg_cached().config_path.parent
    return _tools.ingest_statement(
        _store_cached(),
        path=path,
        account_nickname=account_nickname,
        config_dir=str(cfg_dir),
        archive_dir=str(cfg_dir / "archive"),
        archive=archive,
    )


@mcp.tool()
def list_batches(
    source_id: str | None = None,
    review_status: str = "pending",
) -> list[dict]:  # type: ignore[type-arg]
    """List statement batches in the local store."""
    return _tools.list_batches(_store_cached(), source_id=source_id, review_status=review_status)


@mcp.tool()
def confirm_batch(batch_id: int) -> dict:  # type: ignore[type-arg]
    """Promote a pending batch's transactions to status='confirmed'."""
    return _tools.confirm_batch(_store_cached(), batch_id=batch_id)


@mcp.tool()
def reject_batch(batch_id: int) -> dict:  # type: ignore[type-arg]
    """Delete a pending batch's staged transactions; preserve the batch row."""
    return _tools.reject_batch(_store_cached(), batch_id=batch_id)


@mcp.tool()
def add_category_rule(
    priority: int,
    match_field: str,
    pattern: str,
    canonical_category: str,
    is_regex: bool = False,
    note: str | None = None,
) -> int:
    """Append a categorization rule. match_field is 'payee' or 'memo'."""
    return _tools.add_category_rule(
        _store_cached(),
        priority=priority,
        match_field=match_field,
        pattern=pattern,
        is_regex=is_regex,
        canonical_category=canonical_category,
        note=note,
    )


@mcp.tool()
def list_category_rules() -> list[dict]:  # type: ignore[type-arg]
    """All categorization rules in evaluation order."""
    return _tools.list_category_rules(_store_cached())


@mcp.tool()
def apply_categorization(source_id: str | None = None) -> dict:  # type: ignore[type-arg]
    """Re-derive canonical categories for all non-manual rows. Returns counts."""
    return _tools.apply_categorization(_store_cached(), source_id=source_id)


@mcp.tool()
def suggest_categories(limit: int = 50) -> dict:  # type: ignore[type-arg]
    """Uncategorized payees + the YNAB category-name set to constrain suggestions."""
    return _tools.suggest_categories(_store_cached(), limit=limit)


@mcp.tool()
def set_transaction_category(transaction_id: str, canonical_category: str) -> dict:  # type: ignore[type-arg]
    """Pin one transaction's canonical_category as a sticky manual edit."""
    return _tools.set_transaction_category(
        _store_cached(),
        transaction_id=transaction_id,
        canonical_category=canonical_category,
    )


@mcp.tool()
def list_payees(source_id: str | None = None, name_contains: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    """Distinct payees with transaction counts."""
    return _tools.list_payees(_store_cached(), source_id=source_id, name_contains=name_contains)


@mcp.tool()
def cash_flow(
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str = "month",
    source_id: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Inflow/outflow/net per period (transfers excluded, confirmed-only)."""
    return _tools.cash_flow(
        _store_cached(),
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        source_id=source_id,
    )


@mcp.tool()
def detect_recurring(min_occurrences: int = 3, amount_tolerance_minor: int = 200) -> list[dict]:  # type: ignore[type-arg]
    """Detected recurring charges + next-occurrence forecast."""
    return _tools.detect_recurring(
        _store_cached(),
        min_occurrences=min_occurrences,
        amount_tolerance_minor=amount_tolerance_minor,
    )


@mcp.tool()
def detect_anomalies(trailing_months: int = 6, z_threshold: float = 2.0) -> list[dict]:  # type: ignore[type-arg]
    """Category-month spend spikes vs a trailing baseline."""
    return _tools.detect_anomalies(
        _store_cached(), trailing_months=trailing_months, z_threshold=z_threshold
    )


@mcp.tool()
def contribution_limits(tax_year: int) -> dict:  # type: ignore[type-arg]
    """IRS contribution limits for a tax year (IRA / Roth bands / HSA) with source + disclaimer."""
    return _tools.contribution_limits(tax_year=tax_year)


@mcp.tool()
def roth_eligibility(tax_year: int, filing_status: str, magi_minor: int, age: int = 40) -> dict:  # type: ignore[type-arg]
    """Roth IRA MAGI phase-out status + reduced contribution limit for a tax year."""
    return _tools.roth_eligibility(
        tax_year=tax_year, filing_status=filing_status, magi_minor=magi_minor, age=age
    )


@mcp.tool()
def retirement_summary(
    tax_year: int,
    magi_override_minor: int | None = None,
    age_override: int | None = None,
) -> dict:  # type: ignore[type-arg]
    """Per-account contribution headroom + opportunities, read from the [retirement] config."""
    cfg = _cfg_cached()
    raw = None
    if cfg.config_path.exists():
        import tomllib

        raw = tomllib.loads(cfg.config_path.read_text()).get("retirement")
    return _tools.retirement_summary(
        tax_year=tax_year,
        retirement_cfg=raw,
        magi_override_minor=magi_override_minor,
        age_override=age_override,
    )


if __name__ == "__main__":  # pragma: no cover
    mcp.run()
