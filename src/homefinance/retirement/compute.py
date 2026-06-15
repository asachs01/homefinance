"""Pure, deterministic retirement computations.

All money is integer minor units (cents). No LLM, no I/O — these functions
take already-loaded limits + plain inputs and return plain dicts. Outputs are
informational; callers attach DISCLAIMER.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DISCLAIMER = (
    "Informational only — not financial, tax, or legal advice. Contribution "
    "limits and phase-outs are summarized from IRS sources for the stated tax "
    "year; verify against current IRS publications before acting."
)

ROTH_ROUND_MINOR = 1000  # IRS worksheet rounds the reduced Roth limit up to the nearest $10
ROTH_FLOOR_MINOR = 20000  # a positive reduced limit below $200 is floored to $200


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

    # Partial: reduced = full_limit * (high - magi) / (high - low), rounded UP
    # to the nearest $10, then floored to $200 if positive. Done in the integer
    # domain (no float) so a value exactly on a $10 boundary never rounds up an
    # extra $10 from floating-point representation error.
    numerator = full_limit * (high - magi_minor)  # exact integer (cents²-scaled)
    denom_10 = (high - low) * ROTH_ROUND_MINOR  # denominator x $10 step
    units = -(-numerator // denom_10)  # ceil division (ints)
    reduced = units * ROTH_ROUND_MINOR
    if 0 < reduced < ROTH_FLOOR_MINOR:
        reduced = ROTH_FLOOR_MINOR
    return {
        "status": "partial",
        "roth_limit_minor": reduced,
        "band_low_minor": low,
        "band_high_minor": high,
    }


def hsa_headroom(
    *,
    age: int,
    hsa_coverage: str | None,
    hsa_contributed_minor: int,
    limits: dict[str, Any],
) -> dict[str, Any] | None:
    """HSA headroom for self-only or family coverage, or None if no HSA configured."""
    if hsa_coverage == "self_only":
        cap = limits["hsa_self_only_minor"]
    elif hsa_coverage == "family":
        cap = limits["hsa_family_minor"]
    else:
        return None
    catchup = limits["hsa_catchup_minor"] if age >= limits["hsa_catchup_age"] else 0
    limit = cap + catchup
    return {
        "coverage": hsa_coverage,
        "limit_minor": limit,
        "catchup_applied_minor": catchup,
        "contributed_minor": hsa_contributed_minor,
        "remaining_minor": max(0, limit - hsa_contributed_minor),
    }


def opportunities(
    *,
    tax_year: int,
    ira: dict[str, Any],
    hsa: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Flag accounts with unused headroom, each tagged with the contribution deadline."""
    deadline = contribution_deadline(tax_year)
    out: list[dict[str, Any]] = []
    if ira["remaining_minor"] > 0:
        out.append(
            {"account": "ira", "remaining_minor": ira["remaining_minor"], "deadline": deadline}
        )
    if hsa is not None and hsa["remaining_minor"] > 0:
        out.append(
            {"account": "hsa", "remaining_minor": hsa["remaining_minor"], "deadline": deadline}
        )
    return out
