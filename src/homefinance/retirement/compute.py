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
