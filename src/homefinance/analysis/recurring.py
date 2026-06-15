"""Recurring-charge detection + next-occurrence forecast.

Groups confirmed, non-transfer Leaves transactions by (payee, amount within a
tolerance), then looks for a regular cadence via the median gap between dates.
Pure stdlib arithmetic — no numpy.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from statistics import median
from typing import Any

from homefinance.db.store import Store

# (label, low_days, high_days) — median gap falling in [low, high] gets the label.
_CADENCES: list[tuple[str, int, int]] = [
    ("weekly", 6, 8),
    ("biweekly", 12, 16),
    ("monthly", 27, 33),
    ("quarterly", 85, 95),
    ("annual", 358, 372),
]


def _cadence_label(median_gap_days: float) -> str | None:
    for label, lo, hi in _CADENCES:
        if lo <= median_gap_days <= hi:
            return label
    return None


def _confidence(gaps: list[int], median_gap: float) -> float:
    """Higher when gaps are tight around the median. In [0, 1]."""
    if not gaps or median_gap <= 0:
        return 0.0
    avg_dev = sum(abs(g - median_gap) for g in gaps) / len(gaps)
    regularity = max(0.0, 1.0 - (avg_dev / median_gap))
    count_factor = min(1.0, len(gaps) / 5.0)  # saturates at ~6 occurrences
    return round(regularity * count_factor, 3)


def detect_recurring(
    store: Store,
    *,
    min_occurrences: int = 3,
    amount_tolerance_minor: int = 200,
) -> list[dict[str, Any]]:
    """Return detected recurring series, highest confidence first."""
    rows = store.execute(
        "SELECT payee, amount_minor, date FROM transactions "
        "WHERE deleted = 0 AND is_split_parent = 0 AND status = 'confirmed' "
        "AND transfer_account_id IS NULL AND payee IS NOT NULL AND payee != '' "
        "ORDER BY payee, date"
    ).fetchall()

    # Bucket by payee, then cluster amounts within tolerance.
    by_payee: dict[str, list[tuple[int, str]]] = {}
    for r in rows:
        by_payee.setdefault(r["payee"], []).append((int(r["amount_minor"]), r["date"]))

    series: list[dict[str, Any]] = []
    for payee, txns in by_payee.items():
        # Group by amount cluster: sort by amount, greedily cluster within tolerance.
        txns_sorted = sorted(txns)
        clusters: list[list[tuple[int, str]]] = []
        for amount, d in txns_sorted:
            if clusters and abs(amount - clusters[-1][0][0]) <= amount_tolerance_minor:
                clusters[-1].append((amount, d))
            else:
                clusters.append([(amount, d)])

        for cluster in clusters:
            if len(cluster) < min_occurrences:
                continue
            dates = sorted(_date.fromisoformat(d) for _, d in cluster)
            gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            if not gaps:
                continue
            med = median(gaps)
            conf = _confidence(gaps, med)
            last = dates[-1]
            next_expected = (last + timedelta(days=round(med))).isoformat()
            typical = round(median(a for a, _ in cluster))
            series.append(
                {
                    "payee": payee,
                    "typical_amount_minor": int(typical),
                    "occurrences": len(cluster),
                    "median_gap_days": round(med, 1),
                    "cadence": _cadence_label(med),
                    "first_seen": dates[0].isoformat(),
                    "last_seen": last.isoformat(),
                    "next_expected": next_expected,
                    "confidence": conf,
                }
            )

    series.sort(key=lambda s: s["confidence"], reverse=True)
    return series
