from homefinance.retirement.compute import (
    DISCLAIMER,
    contribution_deadline,
    ira_headroom,
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
