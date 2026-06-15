"""Cash-flow analysis: inflow / outflow / net per period.

Disciplines (per spec §8.1): Leaves view (is_split_parent = 0), deleted = 0,
status = 'confirmed', and transfers (transfer_account_id IS NOT NULL) are
excluded so internal moves never inflate income or spending.
"""

from __future__ import annotations

from typing import Any, Literal

from homefinance.db.store import Store

Period = Literal["month", "week"]

# SQLite strftime grouping expressions.
_PERIOD_EXPR: dict[str, str] = {
    "month": "substr(date, 1, 7)",  # YYYY-MM
    "week": "strftime('%Y-W%W', date)",  # ISO-ish year-week
}


def cash_flow(
    store: Store,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: Period = "month",
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Inflow/outflow/net per period (most-recent period first)."""
    expr = _PERIOD_EXPR.get(group_by)
    if expr is None:
        raise ValueError(f"invalid group_by: {group_by!r}")

    where = [
        "deleted = 0",
        "is_split_parent = 0",
        "status = 'confirmed'",
        "transfer_account_id IS NULL",
    ]
    params: list[Any] = []
    if source_id is not None:
        where.append("source_id = ?")
        params.append(source_id)
    if date_from is not None:
        where.append("date >= ?")
        params.append(date_from)
    if date_to is not None:
        where.append("date <= ?")
        params.append(date_to)

    sql = (
        f"SELECT {expr} AS period, "
        "COALESCE(SUM(CASE WHEN amount_minor > 0 THEN amount_minor END), 0) AS inflow_minor, "
        "COALESCE(SUM(CASE WHEN amount_minor < 0 THEN amount_minor END), 0) AS outflow_minor, "
        "COALESCE(SUM(amount_minor), 0) AS net_minor, "
        "COUNT(*) AS count "
        "FROM transactions WHERE " + " AND ".join(where) + f" GROUP BY {expr} ORDER BY period DESC"
    )
    return [
        {
            "period": r["period"],
            "inflow_minor": int(r["inflow_minor"]),
            "outflow_minor": int(r["outflow_minor"]),
            "net_minor": int(r["net_minor"]),
            "count": int(r["count"]),
        }
        for r in store.execute(sql, params).fetchall()
    ]
