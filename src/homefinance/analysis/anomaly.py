"""Anomaly detection: per-(canonical_category, month) spend spikes.

For each category, build a monthly spend series, compute the trailing-window
mean and population standard deviation, and flag any month exceeding
mean + z_threshold * sigma. Windows with zero variance (sigma == 0) are
skipped — a degenerate baseline can't yield a meaningful z-score. Categories
with too few months of history are skipped too (never falsely flagged).
Pure stdlib — no numpy.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from homefinance.db.store import Store


def detect_anomalies(
    store: Store,
    *,
    trailing_months: int = 6,
    z_threshold: float = 2.0,
    min_history_months: int = 3,
) -> list[dict[str, Any]]:
    """Flag category-month spend spikes. Most-recent flags first."""
    rows = store.execute(
        "SELECT canonical_category AS cat, substr(date, 1, 7) AS period, "
        "SUM(ABS(amount_minor)) AS spend "
        "FROM transactions "
        "WHERE deleted = 0 AND is_split_parent = 0 AND status = 'confirmed' "
        "AND transfer_account_id IS NULL AND amount_minor < 0 "
        "AND canonical_category IS NOT NULL "
        "GROUP BY cat, period ORDER BY cat, period"
    ).fetchall()

    by_cat: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        by_cat.setdefault(r["cat"], []).append((r["period"], int(r["spend"])))

    flags: list[dict[str, Any]] = []
    for _cat, series in by_cat.items():
        if len(series) < min_history_months:
            continue
        for i in range(min_history_months, len(series)):
            window = [spend for _, spend in series[max(0, i - trailing_months) : i]]
            if len(window) < 2:
                continue
            mu = mean(window)
            sigma = pstdev(window)
            if sigma == 0:
                continue  # degenerate baseline — no meaningful z-score
            period, spend = series[i]
            if spend > mu + z_threshold * sigma:
                flags.append(
                    {
                        "canonical_category": _cat,
                        "period": period,
                        "spend_minor": spend,
                        "baseline_mean_minor": round(mu),
                        "baseline_stdev_minor": round(sigma),
                        "z_score": round((spend - mu) / sigma, 2),
                    }
                )
    flags.sort(key=lambda f: f["period"], reverse=True)
    return flags
