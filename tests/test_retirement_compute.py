from homefinance.retirement.compute import (
    DISCLAIMER,
    contribution_deadline,
    ira_headroom,
    roth_eligibility,
)
from homefinance.retirement.limits import load_limits


def test_disclaimer_is_nonempty_and_says_not_advice() -> None:
    assert "not financial" in DISCLAIMER.lower()


def test_ira_headroom_combined_bucket_under_50() -> None:
    lim = load_limits(2025)
    out = ira_headroom(
        age=40, trad_contributed_minor=200000, roth_contributed_minor=100000, limits=lim
    )
    # $7,000 limit (no catch-up), $3,000 contributed → $4,000 remaining.
    assert out["limit_minor"] == 700000
    assert out["catchup_applied_minor"] == 0
    assert out["contributed_minor"] == 300000
    assert out["remaining_minor"] == 400000


def test_ira_headroom_catchup_at_50() -> None:
    lim = load_limits(2025)
    out = ira_headroom(age=55, trad_contributed_minor=0, roth_contributed_minor=0, limits=lim)
    # $7,000 + $1,000 catch-up = $8,000 limit, nothing contributed.
    assert out["limit_minor"] == 800000
    assert out["catchup_applied_minor"] == 100000
    assert out["remaining_minor"] == 800000


def test_ira_headroom_over_contributed_clamps_to_zero() -> None:
    lim = load_limits(2025)
    out = ira_headroom(
        age=40, trad_contributed_minor=500000, roth_contributed_minor=500000, limits=lim
    )
    assert out["remaining_minor"] == 0  # never negative


def test_contribution_deadline_is_april_15_next_year() -> None:
    assert contribution_deadline(2025) == "2026-04-15"
    assert contribution_deadline(2026) == "2027-04-15"


def test_roth_full_below_band() -> None:
    lim = load_limits(2025)
    out = roth_eligibility(filing_status="single", magi_minor=10000000, age=40, limits=lim)
    assert out["status"] == "full"
    assert out["roth_limit_minor"] == 700000  # full $7,000


def test_roth_none_at_or_above_high() -> None:
    lim = load_limits(2025)
    out = roth_eligibility(filing_status="single", magi_minor=16500000, age=40, limits=lim)
    assert out["status"] == "none"
    assert out["roth_limit_minor"] == 0


def test_roth_partial_midband_rounds_up_to_10() -> None:
    lim = load_limits(2025)
    # single band $150k-$165k (width $15k). MAGI $157,500 → exactly halfway →
    # 0.5 * $7,000 = $3,500, rounded up to nearest $10 = $3,500.
    out = roth_eligibility(filing_status="single", magi_minor=15750000, age=40, limits=lim)
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 350000


def test_roth_partial_floor_200() -> None:
    lim = load_limits(2025)
    # Near the top of the band the formula yields a tiny positive number; the
    # IRS rule floors any >$0 result to $200.
    out = roth_eligibility(filing_status="single", magi_minor=16499000, age=40, limits=lim)
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 20000  # $200 floor


def test_roth_catchup_raises_full_limit() -> None:
    lim = load_limits(2025)
    out = roth_eligibility(filing_status="single", magi_minor=10000000, age=55, limits=lim)
    assert out["roth_limit_minor"] == 800000  # $8,000 with catch-up


def test_roth_head_of_household_uses_single_band() -> None:
    lim = load_limits(2025)
    out = roth_eligibility(
        filing_status="head_of_household", magi_minor=10000000, age=40, limits=lim
    )
    assert out["status"] == "full"


def test_roth_married_separately_band() -> None:
    lim = load_limits(2025)
    # MFS band $0-$10k. MAGI $5,000 → halfway → $3,500.
    out = roth_eligibility(
        filing_status="married_separately", magi_minor=500000, age=40, limits=lim
    )
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 350000
