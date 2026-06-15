"""Pure, deterministic retirement computations.

All money is integer minor units (cents). No LLM, no I/O — these functions
take already-loaded limits + plain inputs and return plain dicts. Outputs are
informational; callers attach DISCLAIMER.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

DISCLAIMER = (
    "Informational only — not financial, tax, or legal advice. Contribution "
    "limits and phase-outs are summarized from IRS sources for the stated tax "
    "year; verify against current IRS publications before acting."
)


def _ira_limit_with_catchup(age: int, limits: dict[str, Any]) -> tuple[int, int]:
    """Return (limit_minor, catchup_applied_minor) for the combined IRA bucket."""
    catchup = limits["ira_catchup_minor"] if age >= limits["ira_catchup_age"] else 0
    return limits["ira_limit_minor"] + catchup, catchup


def ira_headroom(
    *,
    age: int,
    trad_contributed_minor: int,
    roth_contributed_minor: int,
    limits: dict[str, Any],
) -> dict[str, Any]:
    """Combined Traditional + Roth IRA headroom (they share ONE annual bucket)."""
    limit, catchup = _ira_limit_with_catchup(age, limits)
    contributed = trad_contributed_minor + roth_contributed_minor
    return {
        "limit_minor": limit,
        "catchup_applied_minor": catchup,
        "contributed_minor": contributed,
        "remaining_minor": max(0, limit - contributed),
    }


def contribution_deadline(tax_year: int) -> str:
    """Federal tax-filing deadline for the tax year: April 15 of the next year.

    A documented simplification — not adjusted for weekends/holidays/extensions.
    """
    return date(tax_year + 1, 4, 15).isoformat()


def _round_up_to_nearest_10_dollars(amount_minor: float) -> int:
    """Round a cents amount up to the nearest $10 (1000 cents) — IRS worksheet rule."""
    return math.ceil(amount_minor / 1000) * 1000


def _phaseout_band_key(filing_status: str) -> str:
    """Map filing status to its Roth phase-out band key.

    'head_of_household' shares the 'single' band per IRS rules.
    """
    if filing_status in ("single", "head_of_household"):
        return "single"
    return filing_status


def roth_eligibility(
    *,
    filing_status: str,
    magi_minor: int,
    age: int,
    limits: dict[str, Any],
) -> dict[str, Any]:
    """Reduced Roth contribution sub-limit given MAGI + filing status.

    Below the band → full IRA limit; at/above the high end → $0; within the
    band → IRS worksheet: limit * (1 - (magi-low)/(high-low)), rounded UP to
    the nearest $10, with any positive result floored to $200.
    """
    full_limit, _ = _ira_limit_with_catchup(age, limits)
    band = limits["roth_phaseout"][_phaseout_band_key(filing_status)]
    low, high = band["low_minor"], band["high_minor"]

    if magi_minor < low:
        return {
            "status": "full",
            "roth_limit_minor": full_limit,
            "band_low_minor": low,
            "band_high_minor": high,
        }
    if magi_minor >= high:
        return {
            "status": "none",
            "roth_limit_minor": 0,
            "band_low_minor": low,
            "band_high_minor": high,
        }

    frac = (magi_minor - low) / (high - low)
    reduced = _round_up_to_nearest_10_dollars(full_limit * (1.0 - frac))
    if 0 < reduced < 20000:  # IRS $200 floor
        reduced = 20000
    return {
        "status": "partial",
        "roth_limit_minor": int(reduced),
        "band_low_minor": low,
        "band_high_minor": high,
    }
