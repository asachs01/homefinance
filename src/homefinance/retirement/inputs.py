"""Parse the ``[retirement]`` section of config.toml into a typed model.

MAGI is sensitive and stays in SP1's 0o600 config file; this module only
reads an already-loaded dict (the caller supplies it), so tests stay hermetic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FilingStatus = Literal["single", "head_of_household", "married_jointly", "married_separately"]
HsaCoverage = Literal["self_only", "family"]


class Contributed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traditional_ira_minor: int = 0
    roth_ira_minor: int = 0
    hsa_minor: int = 0


class RetirementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_year: int
    filing_status: FilingStatus
    magi_minor: int | None = None
    hsa_coverage: HsaCoverage | None = None
    contributed: Contributed = Field(default_factory=Contributed)

    def age_in(self, tax_year: int) -> int:
        """Age attained during the tax year (year minus birth year).

        A documented simplification — does not model mid-year birthdays.
        """
        return tax_year - self.birth_year


def parse_retirement(raw: dict[str, Any] | None) -> RetirementConfig | None:
    """Parse a ``[retirement]`` config dict, or return None if absent/empty."""
    if not raw:
        return None
    return RetirementConfig(**raw)
