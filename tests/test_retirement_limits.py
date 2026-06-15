import pytest

from homefinance.retirement.limits import LimitsNotFound, load_limits


def test_load_limits_2025_has_required_keys() -> None:
    lim = load_limits(2025)
    assert lim["ira_limit_minor"] == 700000
    assert lim["ira_catchup_minor"] == 100000
    assert lim["ira_catchup_age"] == 50
    assert lim["hsa_self_only_minor"] == 430000
    assert lim["hsa_family_minor"] == 855000
    assert lim["hsa_catchup_age"] == 55
    assert "source" in lim


def test_load_limits_2025_roth_bands() -> None:
    lim = load_limits(2025)
    assert lim["roth_phaseout"]["single"]["low_minor"] == 15000000
    assert lim["roth_phaseout"]["single"]["high_minor"] == 16500000
    assert lim["roth_phaseout"]["married_jointly"]["low_minor"] == 23600000
    assert lim["roth_phaseout"]["married_separately"]["high_minor"] == 1000000


def test_load_limits_unknown_year_fails_loud() -> None:
    with pytest.raises(LimitsNotFound, match="1999"):
        load_limits(1999)


def test_available_years_includes_2025() -> None:
    from homefinance.retirement.limits import available_years

    assert 2025 in available_years()
