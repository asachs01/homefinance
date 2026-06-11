import pytest

from homefinance.sources.ynab.ids import make_id, source_id_for
from homefinance.sources.ynab.mapping import to_minor_units


def test_to_minor_units_positive() -> None:
    assert to_minor_units(45670) == 4567


def test_to_minor_units_negative() -> None:
    assert to_minor_units(-45670) == -4567


def test_to_minor_units_zero() -> None:
    assert to_minor_units(0) == 0


def test_to_minor_units_rejects_sub_cent() -> None:
    with pytest.raises(ValueError, match="non-cent"):
        to_minor_units(12345)


def test_source_id_for_formats_budget() -> None:
    assert source_id_for("abc-123") == "ynab:abc-123"


def test_make_id_concats_source_and_external() -> None:
    assert make_id("ynab:abc", "acct-1") == "ynab:abc:acct-1"
