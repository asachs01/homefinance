import pytest

from homefinance.retirement.inputs import RetirementConfig, parse_retirement


def test_parse_full_section() -> None:
    raw = {
        "birth_year": 1985,
        "filing_status": "single",
        "magi_minor": 14000000,
        "hsa_coverage": "family",
        "contributed": {
            "traditional_ira_minor": 200000,
            "roth_ira_minor": 100000,
            "hsa_minor": 300000,
        },
    }
    cfg = parse_retirement(raw)
    assert isinstance(cfg, RetirementConfig)
    assert cfg.birth_year == 1985
    assert cfg.filing_status == "single"
    assert cfg.magi_minor == 14000000
    assert cfg.hsa_coverage == "family"
    assert cfg.contributed.traditional_ira_minor == 200000
    assert cfg.contributed.roth_ira_minor == 100000
    assert cfg.contributed.hsa_minor == 300000


def test_parse_none_when_absent() -> None:
    assert parse_retirement(None) is None
    assert parse_retirement({}) is None


def test_defaults_for_optional_fields() -> None:
    cfg = parse_retirement({"birth_year": 1990, "filing_status": "married_jointly"})
    assert cfg is not None
    assert cfg.magi_minor is None
    assert cfg.hsa_coverage is None
    assert cfg.contributed.traditional_ira_minor == 0
    assert cfg.contributed.roth_ira_minor == 0
    assert cfg.contributed.hsa_minor == 0


def test_invalid_filing_status_rejected() -> None:
    with pytest.raises(ValueError):
        parse_retirement({"birth_year": 1990, "filing_status": "banana"})


def test_invalid_hsa_coverage_rejected() -> None:
    with pytest.raises(ValueError):
        parse_retirement(
            {"birth_year": 1990, "filing_status": "single", "hsa_coverage": "platinum"}
        )


def test_age_in_returns_year_minus_birth_year() -> None:
    cfg = parse_retirement({"birth_year": 1985, "filing_status": "single"})
    assert cfg is not None
    assert cfg.age_in(2025) == 40
