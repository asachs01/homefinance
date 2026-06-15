"""Load year-keyed IRS contribution limits from the bundled data file.

Fail-loud on an unknown tax year — never guess a number (spec C-15).
"""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).resolve().parent / "data" / "irs_limits.toml"

_REQUIRED_KEYS = (
    "ira_limit_minor",
    "ira_catchup_minor",
    "ira_catchup_age",
    "hsa_self_only_minor",
    "hsa_family_minor",
    "hsa_catchup_minor",
    "hsa_catchup_age",
    "source",
)
_REQUIRED_BANDS = ("single", "married_jointly", "married_separately")


class LimitsNotFound(Exception):
    """Raised when no IRS limit data exists for the requested tax year."""

    code = "no_limit_data"


@cache
def _all_years() -> dict[str, Any]:
    return tomllib.loads(_DATA_FILE.read_text())


def available_years() -> list[int]:
    """Tax years present in the data file, ascending."""
    return sorted(int(y) for y in _all_years())


def load_limits(tax_year: int) -> dict[str, Any]:
    """Return the validated limits dict for ``tax_year``.

    Raises ``LimitsNotFound`` if the year is absent, or ``ValueError`` if the
    year's entry is missing a required key (a malformed data file).
    """
    data = _all_years()
    entry: dict[str, Any] | None = data.get(str(tax_year))
    if entry is None:
        raise LimitsNotFound(f"no IRS limit data for {tax_year}; add it to irs_limits.toml")
    for key in _REQUIRED_KEYS:
        if key not in entry:
            raise ValueError(f"irs_limits.toml[{tax_year}] missing key {key!r}")
    bands = entry.get("roth_phaseout") or {}
    for band in _REQUIRED_BANDS:
        if band not in bands:
            raise ValueError(f"irs_limits.toml[{tax_year}] missing roth_phaseout band {band!r}")
    return entry
