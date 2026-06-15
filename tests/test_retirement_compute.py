from homefinance.retirement.compute import (
    DISCLAIMER,
    contribution_deadline,
    hsa_headroom,
    ira_headroom,
    opportunities,
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


def test_roth_partial_exact_10_boundary_no_float_overshoot() -> None:
    lim = load_limits(2025)
    # single band $150k-$165k. MAGI $156,150 → remaining = $7,000 * (165000-156150)/15000
    # = $7,000 * 8850/15000 = $4,130.00 exactly — must NOT round up to $4,140.
    out = roth_eligibility(filing_status="single", magi_minor=15615000, age=40, limits=lim)
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 413000  # $4,130, not $4,140


def test_roth_partial_fractional_rounds_up_to_next_10() -> None:
    lim = load_limits(2025)
    # A MAGI whose exact remaining is NOT a $10 multiple must round UP to the next $10.
    # MAGI $156,160 → $7,000 * (165000-156160)/15000 = $7,000 * 8840/15000 = $4,125.33...
    # rounds UP to $4,130.
    out = roth_eligibility(filing_status="single", magi_minor=15616000, age=40, limits=lim)
    assert out["roth_limit_minor"] == 413000  # rounded up from $4,125.33 → $4,130


def test_hsa_self_only_under_55() -> None:
    lim = load_limits(2025)
    out = hsa_headroom(age=40, hsa_coverage="self_only", hsa_contributed_minor=100000, limits=lim)
    assert out is not None
    assert out["limit_minor"] == 430000  # $4,300
    assert out["catchup_applied_minor"] == 0
    assert out["remaining_minor"] == 330000  # $3,300 left


def test_hsa_family_with_catchup_at_55() -> None:
    lim = load_limits(2025)
    out = hsa_headroom(age=60, hsa_coverage="family", hsa_contributed_minor=0, limits=lim)
    assert out is not None
    assert out["limit_minor"] == 955000  # $8,550 + $1,000 catch-up
    assert out["catchup_applied_minor"] == 100000


def test_hsa_none_when_no_coverage() -> None:
    lim = load_limits(2025)
    assert hsa_headroom(age=40, hsa_coverage=None, hsa_contributed_minor=0, limits=lim) is None


def test_opportunities_flags_unused_headroom_with_deadline() -> None:
    lim = load_limits(2025)
    ira = ira_headroom(age=40, trad_contributed_minor=0, roth_contributed_minor=0, limits=lim)
    hsa = hsa_headroom(age=40, hsa_coverage="family", hsa_contributed_minor=0, limits=lim)
    opps = opportunities(tax_year=2025, ira=ira, hsa=hsa)
    accounts = {o["account"] for o in opps}
    assert "ira" in accounts and "hsa" in accounts
    assert all(o["deadline"] == "2026-04-15" for o in opps)
    assert all(o["remaining_minor"] > 0 for o in opps)


def test_opportunities_empty_when_maxed() -> None:
    lim = load_limits(2025)
    ira = ira_headroom(age=40, trad_contributed_minor=700000, roth_contributed_minor=0, limits=lim)
    opps = opportunities(tax_year=2025, ira=ira, hsa=None)
    assert opps == []
