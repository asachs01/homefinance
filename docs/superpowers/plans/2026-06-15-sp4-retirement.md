# SP4 — Retirement & Tax-Advantaged Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the homeFinance retirement-optimization overlay: contribution **headroom** + opportunities for Traditional IRA / Roth IRA / HSA, computed deterministically from a bundled, cited, per-year IRS-limits file plus a `[retirement]` config section — surfaced as informational facts (never advice) through 3 MCP tools, a `retirement` CLI, and a skill.

**Architecture:** A self-contained `src/homefinance/retirement/` package: a year-keyed `irs_limits.toml` data file + a fail-loud loader, a Pydantic parser for the `[retirement]` config section, and pure compute functions (shared-IRA headroom, Roth MAGI phase-out, HSA caps, deadline, opportunities). No database migration (SP4 reads config + data, writes nothing to the store). No new third-party dependencies. Every output carries an "informational, not advice" disclaimer. See spec: `docs/superpowers/specs/2026-06-15-sp4-retirement-design.md`.

**Tech Stack:** Python 3.11+, stdlib (`tomllib`, `datetime`, `math`), `pydantic` v2, `typer` + `rich`, official `mcp` SDK, `pytest`. No new dependencies.

---

## Prerequisites

```bash
cd /Users/asachs/Documents/projects/personal/homeFinance
git rev-parse --abbrev-ref HEAD   # → sp4-retirement (already created off main; SP1-3 merged)
```

Reuse the venv at `~/.virtualenvs/homeFinance/`; use absolute binary paths (`~/.virtualenvs/homeFinance/bin/{python,pytest,mypy,ruff}`). **Baseline at start: full suite = 178 passing.** Every code task ends by running `ruff check src tests`, **`ruff format .` then `ruff format --check .`** (CI checks the whole repo), and `mypy` — all must be clean before commit.

All money is **integer minor units (cents)**, program-wide.

---

## File Structure

```
src/homefinance/retirement/
├── __init__.py                 # Task 1
├── data/irs_limits.toml        # Task 1 (2025 values); Task 2 (verify + 2026)
├── limits.py                   # Task 1  (load + fail-loud)
├── inputs.py                   # Task 3  ([retirement] config parsing)
└── compute.py                  # Tasks 4-6 (headroom / roth / hsa / deadline / opportunities)

src/homefinance/mcp_server/{tools,__main__}.py   # Task 7 (3 tools + wrappers)
src/homefinance/cli.py                           # Task 8 (retirement group)
plugin/skills/homefinance-retirement/SKILL.md    # Task 9
README.md, docs/{quickstart,architecture}.md, CHANGELOG.md   # Task 10

tests/
├── test_retirement_limits.py   # Task 1
├── test_retirement_inputs.py   # Task 3
├── test_retirement_compute.py  # Tasks 4-6
├── test_mcp_tools.py           # Task 7 (extend)
└── test_cli.py                 # Task 8 (extend)
```

The constant `DISCLAIMER` (defined in Task 4's `compute.py`) is the single source for the disclaimer text:
`"Informational only — not financial, tax, or legal advice. Contribution limits and phase-outs are summarized from IRS sources for the stated tax year; verify against current IRS publications before acting."`

---

## Task 1: IRS limits data file + fail-loud loader

**Files:**
- Create: `src/homefinance/retirement/__init__.py`
- Create: `src/homefinance/retirement/data/irs_limits.toml`
- Create: `src/homefinance/retirement/limits.py`
- Create: `tests/test_retirement_limits.py`

- [ ] **Step 1: Create `src/homefinance/retirement/__init__.py`**

```python
"""SP4 retirement & tax-advantaged optimization (Traditional IRA / Roth IRA / HSA).

An overlay fed by a bundled, cited, per-year IRS-limits file plus the
``[retirement]`` config section — not derived from the transaction store.
Informational only; see the DISCLAIMER constant in ``compute.py``.
"""
```

- [ ] **Step 2: Create `src/homefinance/retirement/data/irs_limits.toml`** with the 2025 figures (high-confidence; the 2026 block + a verification pass land in Task 2). **All values are integer cents.**

```toml
# IRS contribution limits + Roth MAGI phase-out bands, by tax year.
# All money values are integer minor units (cents).
# VERIFY against the cited IRS source before relying on these (see C-17).

[2025]
source = "IRS Rev. Proc. 2024-25 (HSA) + Notice 2024-80 (IRA/Roth) — verify at irs.gov"
ira_limit_minor      = 700000     # $7,000 combined Traditional + Roth
ira_catchup_minor    = 100000     # +$1,000 at age >= 50
ira_catchup_age      = 50
hsa_self_only_minor  = 430000     # $4,300
hsa_family_minor     = 855000     # $8,550
hsa_catchup_minor    = 100000     # +$1,000 at age >= 55
hsa_catchup_age      = 55

[2025.roth_phaseout.single]
low_minor  = 15000000             # $150,000  (also used for head_of_household)
high_minor = 16500000             # $165,000

[2025.roth_phaseout.married_jointly]
low_minor  = 23600000             # $236,000
high_minor = 24600000             # $246,000

[2025.roth_phaseout.married_separately]
low_minor  = 0
high_minor = 1000000              # $10,000
```

- [ ] **Step 3: Write failing tests at `tests/test_retirement_limits.py`**

```python
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
```

- [ ] **Step 4: Run to confirm fail**

Run: `~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_limits.py -v`
Expected: `ModuleNotFoundError: No module named 'homefinance.retirement.limits'`.

- [ ] **Step 5: Implement `src/homefinance/retirement/limits.py`**

```python
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
    entry = data.get(str(tax_year))
    if entry is None:
        raise LimitsNotFound(
            f"no IRS limit data for {tax_year}; add it to irs_limits.toml"
        )
    for key in _REQUIRED_KEYS:
        if key not in entry:
            raise ValueError(f"irs_limits.toml[{tax_year}] missing key {key!r}")
    bands = entry.get("roth_phaseout") or {}
    for band in _REQUIRED_BANDS:
        if band not in bands:
            raise ValueError(
                f"irs_limits.toml[{tax_year}] missing roth_phaseout band {band!r}"
            )
    return entry
```

- [ ] **Step 6: Run to confirm pass + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_limits.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests
~/.virtualenvs/homeFinance/bin/ruff format .
~/.virtualenvs/homeFinance/bin/ruff format --check .
~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/retirement/__init__.py \
        src/homefinance/retirement/data/irs_limits.toml \
        src/homefinance/retirement/limits.py \
        tests/test_retirement_limits.py
git commit -m "feat(retirement): IRS limits data file (2025) + fail-loud loader"
```
Expected: `4 passed`.

Note for packaging: `pyproject.toml`'s `[tool.hatch.build.targets.wheel.shared-data]` already ships `db/schema.sql` and `db/migrations`. The retirement TOML lives **inside the package** (`src/homefinance/retirement/data/`) and is loaded by `__file__`-relative path, so it ships automatically with the wheel's package data — no pyproject change needed. (If a later sdist/wheel build ever omits it, add `"src/homefinance/retirement/data" = "homefinance/retirement/data"` to that block — but do NOT add it pre-emptively.)

---

## Task 2: Verify the IRS figures + add 2026

**Goal:** Confirm the 2025 numbers and add a verified 2026 block. This is the C-17 verification step — the data file is the single point of truth for the numbers, so they must be right and cited.

**Files:**
- Modify: `src/homefinance/retirement/data/irs_limits.toml`
- Modify: `tests/test_retirement_limits.py` (add a 2026 structural test)

- [ ] **Step 1: Verify 2025 + obtain 2026 figures from the IRS.** Use `WebFetch` against official IRS pages (or, if WebFetch is unavailable in this environment, STOP and report `NEEDS_CONTEXT` asking the controller to supply the verified 2026 numbers — do NOT guess). Fetch:
  - IRA / Roth limits + Roth MAGI phase-out: `https://www.irs.gov/retirement-plans/plan-participant-employee/amount-of-roth-ira-contributions-that-you-can-make-for-2025` and the corresponding 2026 page, plus the IRS "401(k) limit increases / IRA" news release for the relevant year.
  - HSA limits: the IRS Revenue Procedure announcing HSA inflation-adjusted amounts (search `site:irs.gov HSA inflation adjusted <year>`).

  Record, for **2025** (confirm the values already in the file) and **2026**: `ira_limit_minor`, `ira_catchup_minor`, `hsa_self_only_minor`, `hsa_family_minor`, `hsa_catchup_minor`, and the three Roth phase-out bands (`single`, `married_jointly`, `married_separately`) as `low_minor`/`high_minor`. Convert dollars → cents (×100).

- [ ] **Step 2: Correct any 2025 discrepancy and append the `[2026]` block** to `irs_limits.toml`, mirroring the 2025 structure, with a real `source = "<IRS publication + URL>"` citation for 2026 (and update 2025's `source` to the confirmed citation/URL). The catch-up ages (`ira_catchup_age = 50`, `hsa_catchup_age = 55`) are stable statutory ages — keep them unless the IRS source says otherwise.

- [ ] **Step 3: Add a structural test to `tests/test_retirement_limits.py`** (asserts 2026 loads with all required keys; does NOT hardcode the dollar values, so the test stays valid if a figure is corrected later):

```python
def test_load_limits_2026_is_structurally_complete() -> None:
    lim = load_limits(2026)
    for key in (
        "ira_limit_minor", "ira_catchup_minor", "ira_catchup_age",
        "hsa_self_only_minor", "hsa_family_minor", "hsa_catchup_minor",
        "hsa_catchup_age", "source",
    ):
        assert key in lim, f"2026 missing {key}"
    for band in ("single", "married_jointly", "married_separately"):
        assert lim["roth_phaseout"][band]["low_minor"] >= 0
        assert lim["roth_phaseout"][band]["high_minor"] > lim["roth_phaseout"][band]["low_minor"]
    assert 2026 in available_years()
```

- [ ] **Step 4: Run + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_limits.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format --check .
git add src/homefinance/retirement/data/irs_limits.toml tests/test_retirement_limits.py
git commit -m "feat(retirement): verify 2025 figures + add cited 2026 IRS limits"
```
Expected: `5 passed`. **In your report, paste the 2025 + 2026 numbers you used and the source URLs**, so the controller's spec review can confirm them.

---

## Task 3: `[retirement]` config parsing

**Files:**
- Create: `src/homefinance/retirement/inputs.py`
- Create: `tests/test_retirement_inputs.py`

- [ ] **Step 1: Write failing tests at `tests/test_retirement_inputs.py`**

```python
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
        parse_retirement({"birth_year": 1990, "filing_status": "single", "hsa_coverage": "platinum"})


def test_age_in_returns_year_minus_birth_year() -> None:
    cfg = parse_retirement({"birth_year": 1985, "filing_status": "single"})
    assert cfg is not None
    assert cfg.age_in(2025) == 40
```

- [ ] **Step 2: Confirm fail** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/retirement/inputs.py`**

```python
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
```

- [ ] **Step 4: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_inputs.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/retirement/inputs.py tests/test_retirement_inputs.py
git commit -m "feat(retirement): [retirement] config parsing with filing-status/hsa enums"
```
Expected: `6 passed`.

---

## Task 4: compute — IRA headroom + deadline + DISCLAIMER

**Files:**
- Create: `src/homefinance/retirement/compute.py`
- Create: `tests/test_retirement_compute.py`

- [ ] **Step 1: Write failing tests at `tests/test_retirement_compute.py`**

```python
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
    out = ira_headroom(
        age=55, trad_contributed_minor=0, roth_contributed_minor=0, limits=lim
    )
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
```

- [ ] **Step 2: Confirm fail** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/homefinance/retirement/compute.py`** (this file grows in Tasks 5-6; start with the disclaimer, IRA headroom, deadline, and a small money-rounding helper used later):

```python
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
```

- [ ] **Step 4: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_compute.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/retirement/compute.py tests/test_retirement_compute.py
git commit -m "feat(retirement): IRA combined-bucket headroom + deadline + disclaimer"
```
Expected: `5 passed`.

---

## Task 5: compute — Roth MAGI phase-out (the formula)

**Files:**
- Modify: `src/homefinance/retirement/compute.py` (append `roth_eligibility`)
- Modify: `tests/test_retirement_compute.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_retirement_compute.py`**

```python
from homefinance.retirement.compute import roth_eligibility


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
    out = roth_eligibility(filing_status="head_of_household", magi_minor=10000000, age=40, limits=lim)
    assert out["status"] == "full"


def test_roth_married_separately_band() -> None:
    lim = load_limits(2025)
    # MFS band $0-$10k. MAGI $5,000 → halfway → $3,500.
    out = roth_eligibility(filing_status="married_separately", magi_minor=500000, age=40, limits=lim)
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 350000
```

- [ ] **Step 2: Confirm fail** — `ImportError` on `roth_eligibility`.

- [ ] **Step 3: Append to `src/homefinance/retirement/compute.py`**

```python
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
        return {"status": "full", "roth_limit_minor": full_limit,
                "band_low_minor": low, "band_high_minor": high}
    if magi_minor >= high:
        return {"status": "none", "roth_limit_minor": 0,
                "band_low_minor": low, "band_high_minor": high}

    frac = (magi_minor - low) / (high - low)
    reduced = _round_up_to_nearest_10_dollars(full_limit * (1.0 - frac))
    if 0 < reduced < 20000:  # IRS $200 floor
        reduced = 20000
    return {"status": "partial", "roth_limit_minor": int(reduced),
            "band_low_minor": low, "band_high_minor": high}
```

- [ ] **Step 4: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_compute.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/retirement/compute.py tests/test_retirement_compute.py
git commit -m "feat(retirement): Roth MAGI phase-out (round-up-\$10 + \$200 floor)"
```
Expected: `12 passed` (5 from Task 4 + 7 new).

---

## Task 6: compute — HSA headroom + opportunities

**Files:**
- Modify: `src/homefinance/retirement/compute.py` (append)
- Modify: `tests/test_retirement_compute.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_retirement_compute.py`**

```python
from homefinance.retirement.compute import hsa_headroom, opportunities


def test_hsa_self_only_under_55() -> None:
    lim = load_limits(2025)
    out = hsa_headroom(age=40, hsa_coverage="self_only", hsa_contributed_minor=100000, limits=lim)
    assert out is not None
    assert out["limit_minor"] == 430000      # $4,300
    assert out["catchup_applied_minor"] == 0
    assert out["remaining_minor"] == 330000  # $3,300 left


def test_hsa_family_with_catchup_at_55() -> None:
    lim = load_limits(2025)
    out = hsa_headroom(age=60, hsa_coverage="family", hsa_contributed_minor=0, limits=lim)
    assert out is not None
    assert out["limit_minor"] == 955000      # $8,550 + $1,000 catch-up
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
```

- [ ] **Step 2: Confirm fail** — `ImportError`.

- [ ] **Step 3: Append to `src/homefinance/retirement/compute.py`**

```python
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
        out.append({"account": "ira", "remaining_minor": ira["remaining_minor"],
                    "deadline": deadline})
    if hsa is not None and hsa["remaining_minor"] > 0:
        out.append({"account": "hsa", "remaining_minor": hsa["remaining_minor"],
                    "deadline": deadline})
    return out
```

- [ ] **Step 4: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_retirement_compute.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/retirement/compute.py tests/test_retirement_compute.py
git commit -m "feat(retirement): HSA headroom + opportunities flagging"
```
Expected: `17 passed`.

---

## Task 7: MCP tools (3)

**Files:**
- Modify: `src/homefinance/mcp_server/tools.py`
- Modify: `src/homefinance/mcp_server/__main__.py`
- Modify: `tests/test_mcp_tools.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_mcp_tools.py`** (these test the plain library functions; note they do NOT need a synced store — retirement is config/data driven):

```python
def test_mcp_contribution_limits_2025() -> None:
    from homefinance.mcp_server.tools import contribution_limits as mcp_contribution_limits

    out = mcp_contribution_limits(tax_year=2025)
    assert out["ira_limit_minor"] == 700000
    assert "disclaimer" in out
    assert "source" in out


def test_mcp_contribution_limits_unknown_year_returns_error() -> None:
    from homefinance.mcp_server.tools import contribution_limits as mcp_contribution_limits

    out = mcp_contribution_limits(tax_year=1999)
    assert out["error"] == "no_limit_data"


def test_mcp_roth_eligibility_partial() -> None:
    from homefinance.mcp_server.tools import roth_eligibility as mcp_roth_eligibility

    out = mcp_roth_eligibility(tax_year=2025, filing_status="single", magi_minor=15750000, age=40)
    assert out["status"] == "partial"
    assert out["roth_limit_minor"] == 350000
    assert "disclaimer" in out


def test_mcp_retirement_summary_from_config() -> None:
    from homefinance.mcp_server.tools import retirement_summary as mcp_retirement_summary

    cfg = {
        "birth_year": 1985,
        "filing_status": "single",
        "magi_minor": 14000000,
        "hsa_coverage": "family",
        "contributed": {"traditional_ira_minor": 200000, "roth_ira_minor": 100000, "hsa_minor": 300000},
    }
    out = mcp_retirement_summary(tax_year=2025, retirement_cfg=cfg)
    assert out["ira"]["remaining_minor"] == 400000   # $7,000 - $3,000
    assert out["roth"]["status"] == "full"           # MAGI $140k < $150k band
    assert out["hsa"]["remaining_minor"] == 555000   # $8,550 - $3,000
    assert any(o["account"] == "ira" for o in out["opportunities"])
    assert out["deadline"] == "2026-04-15"
    assert "disclaimer" in out


def test_mcp_retirement_summary_no_config_returns_friendly_message() -> None:
    from homefinance.mcp_server.tools import retirement_summary as mcp_retirement_summary

    out = mcp_retirement_summary(tax_year=2025, retirement_cfg=None)
    assert "configure" in out["message"].lower()
```

- [ ] **Step 2: Confirm fail** — `ImportError`.

- [ ] **Step 3: Append to `src/homefinance/mcp_server/tools.py`** (top-of-file imports, matching the project's one-import-per-alias style used elsewhere in this file):

```python
from homefinance.retirement.compute import (
    DISCLAIMER as _DISCLAIMER,
)
from homefinance.retirement.compute import (
    contribution_deadline as _contribution_deadline,
)
from homefinance.retirement.compute import (
    hsa_headroom as _hsa_headroom,
)
from homefinance.retirement.compute import (
    ira_headroom as _ira_headroom,
)
from homefinance.retirement.compute import (
    opportunities as _opportunities,
)
from homefinance.retirement.compute import (
    roth_eligibility as _roth_eligibility,
)
from homefinance.retirement.inputs import parse_retirement as _parse_retirement
from homefinance.retirement.limits import LimitsNotFound as _LimitsNotFound
from homefinance.retirement.limits import load_limits as _load_limits


def contribution_limits(*, tax_year: int) -> dict[str, Any]:
    """Raw IRS limits for a tax year (with source + disclaimer), or an error dict."""
    try:
        lim = _load_limits(tax_year)
    except _LimitsNotFound as e:
        return {"error": e.code, "message": str(e)}
    return {
        "tax_year": tax_year,
        "ira_limit_minor": lim["ira_limit_minor"],
        "ira_catchup_minor": lim["ira_catchup_minor"],
        "ira_catchup_age": lim["ira_catchup_age"],
        "hsa_self_only_minor": lim["hsa_self_only_minor"],
        "hsa_family_minor": lim["hsa_family_minor"],
        "hsa_catchup_minor": lim["hsa_catchup_minor"],
        "hsa_catchup_age": lim["hsa_catchup_age"],
        "roth_phaseout": lim["roth_phaseout"],
        "source": lim["source"],
        "disclaimer": _DISCLAIMER,
    }


def roth_eligibility(
    *, tax_year: int, filing_status: str, magi_minor: int, age: int = 40
) -> dict[str, Any]:
    """Roth phase-out status + reduced limit for a tax year, or an error dict."""
    try:
        lim = _load_limits(tax_year)
    except _LimitsNotFound as e:
        return {"error": e.code, "message": str(e)}
    out = _roth_eligibility(filing_status=filing_status, magi_minor=magi_minor, age=age, limits=lim)
    out["disclaimer"] = _DISCLAIMER
    return out


def retirement_summary(
    *,
    tax_year: int,
    retirement_cfg: dict[str, Any] | None,
    magi_override_minor: int | None = None,
    age_override: int | None = None,
) -> dict[str, Any]:
    """Full per-account headroom + opportunities for the tax year.

    ``retirement_cfg`` is the raw ``[retirement]`` config dict (or None). The
    MCP wrapper loads it from config; tests pass it directly.
    """
    cfg = _parse_retirement(retirement_cfg)
    if cfg is None:
        return {
            "message": "No retirement profile configured. Add a [retirement] section "
                       "to ~/.homefinance/config.toml (birth_year, filing_status, "
                       "magi_minor, hsa_coverage, [retirement.contributed]).",
            "disclaimer": _DISCLAIMER,
        }
    try:
        lim = _load_limits(tax_year)
    except _LimitsNotFound as e:
        return {"error": e.code, "message": str(e)}

    age = age_override if age_override is not None else cfg.age_in(tax_year)
    magi = magi_override_minor if magi_override_minor is not None else cfg.magi_minor

    ira = _ira_headroom(
        age=age,
        trad_contributed_minor=cfg.contributed.traditional_ira_minor,
        roth_contributed_minor=cfg.contributed.roth_ira_minor,
        limits=lim,
    )
    hsa = _hsa_headroom(
        age=age, hsa_coverage=cfg.hsa_coverage,
        hsa_contributed_minor=cfg.contributed.hsa_minor, limits=lim,
    )
    roth: dict[str, Any] = (
        _roth_eligibility(filing_status=cfg.filing_status, magi_minor=magi, age=age, limits=lim)
        if magi is not None
        else {"status": "unknown", "message": "MAGI needed to assess Roth eligibility"}
    )

    return {
        "tax_year": tax_year,
        "age": age,
        "filing_status": cfg.filing_status,
        "ira": ira,
        "roth": roth,
        "hsa": hsa,
        "deadline": _contribution_deadline(tax_year),
        "opportunities": _opportunities(tax_year=tax_year, ira=ira, hsa=hsa),
        "source": lim["source"],
        "disclaimer": _DISCLAIMER,
    }
```

- [ ] **Step 4: Append `@mcp.tool()` wrappers to `src/homefinance/mcp_server/__main__.py`** (the summary wrapper loads the `[retirement]` section from the cached config):

```python
@mcp.tool()
def contribution_limits(tax_year: int) -> dict:
    """IRS contribution limits for a tax year (IRA / Roth bands / HSA) with source + disclaimer."""
    return _tools.contribution_limits(tax_year=tax_year)


@mcp.tool()
def roth_eligibility(tax_year: int, filing_status: str, magi_minor: int, age: int = 40) -> dict:
    """Roth IRA MAGI phase-out status + reduced contribution limit for a tax year."""
    return _tools.roth_eligibility(
        tax_year=tax_year, filing_status=filing_status, magi_minor=magi_minor, age=age
    )


@mcp.tool()
def retirement_summary(
    tax_year: int,
    magi_override_minor: int | None = None,
    age_override: int | None = None,
) -> dict:
    """Per-account contribution headroom + opportunities, read from the [retirement] config."""
    cfg = _cfg_cached()
    raw = None
    if cfg.config_path.exists():
        import tomllib

        raw = tomllib.loads(cfg.config_path.read_text()).get("retirement")
    return _tools.retirement_summary(
        tax_year=tax_year, retirement_cfg=raw,
        magi_override_minor=magi_override_minor, age_override=age_override,
    )
```

- [ ] **Step 5: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_mcp_tools.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/mcp_server/tools.py src/homefinance/mcp_server/__main__.py tests/test_mcp_tools.py
git commit -m "feat(mcp): retirement_summary / contribution_limits / roth_eligibility tools"
```
Expected: all prior MCP tests + 5 new pass.

---

## Task 8: CLI `retirement summary`

**Files:**
- Modify: `src/homefinance/cli.py`
- Modify: `tests/test_cli.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_cli.py`**

```python
def test_retirement_summary_no_config(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    result = runner.invoke(app, ["retirement", "summary", "--tax-year", "2025"])
    assert result.exit_code == 0
    assert "retirement" in result.stdout.lower()


def test_retirement_summary_with_config(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    # Append a [retirement] section to the config the env fixture points at.
    cfg_path = env / "config.toml"
    cfg_path.write_text(
        cfg_path.read_text()
        + '\n[retirement]\nbirth_year = 1985\nfiling_status = "single"\n'
        + "magi_minor = 14000000\nhsa_coverage = \"family\"\n"
        + "[retirement.contributed]\ntraditional_ira_minor = 200000\n"
        + "roth_ira_minor = 100000\nhsa_minor = 300000\n"
    )
    result = runner.invoke(app, ["retirement", "summary", "--tax-year", "2025"])
    assert result.exit_code == 0, result.stdout
    assert "IRA" in result.stdout
    assert "not financial" in result.stdout.lower()  # disclaimer printed


def test_retirement_summary_unknown_year_errors(env: Path) -> None:
    runner.invoke(app, ["init", "--token", "T", "--budget", "budget-tiny",
                        "--nickname", "tiny", "--no-sync"])
    result = runner.invoke(app, ["retirement", "summary", "--tax-year", "1999"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Confirm fail** — `No such command 'retirement'`.

- [ ] **Step 3: Add the `retirement` group to `src/homefinance/cli.py`** (import at top; register the sub-typer near the others):

```python
from homefinance.mcp_server.tools import retirement_summary as _retirement_summary_tool


retirement_app = typer.Typer(help="Retirement contribution headroom & opportunities.")
app.add_typer(retirement_app, name="retirement")


@retirement_app.command("summary")
def retirement_summary_cmd(
    tax_year: int = typer.Option(..., "--tax-year"),
    magi: int | None = typer.Option(None, "--magi", help="MAGI in whole dollars (override)."),
) -> None:
    """Show per-account contribution headroom for the tax year."""
    cfg = load_config()
    raw = None
    if cfg.config_path.exists():
        import tomllib

        raw = tomllib.loads(cfg.config_path.read_text()).get("retirement")

    magi_override = magi * 100 if magi is not None else None
    out = _retirement_summary_tool(
        tax_year=tax_year, retirement_cfg=raw, magi_override_minor=magi_override
    )

    if out.get("error") == "no_limit_data":
        err_console.print(f"[red]{out['message']}[/]")
        raise typer.Exit(code=1)
    if "message" in out and "ira" not in out:
        console.print(f"[yellow]{out['message']}[/]")
        console.print(f"\n[dim]{out['disclaimer']}[/]")
        return

    table = Table(title=f"Retirement headroom — tax year {out['tax_year']} (age {out['age']})")
    table.add_column("account")
    table.add_column("limit", justify="right")
    table.add_column("contributed", justify="right")
    table.add_column("remaining", justify="right")
    ira = out["ira"]
    table.add_row("IRA (Trad+Roth)", f"${ira['limit_minor'] / 100:,.0f}",
                  f"${ira['contributed_minor'] / 100:,.0f}", f"${ira['remaining_minor'] / 100:,.0f}")
    hsa = out["hsa"]
    if hsa is not None:
        table.add_row(f"HSA ({hsa['coverage']})", f"${hsa['limit_minor'] / 100:,.0f}",
                      f"${hsa['contributed_minor'] / 100:,.0f}", f"${hsa['remaining_minor'] / 100:,.0f}")
    console.print(table)

    roth = out["roth"]
    console.print(f"Roth eligibility: [bold]{roth['status']}[/]" +
                  (f" (limit ${roth['roth_limit_minor'] / 100:,.0f})" if "roth_limit_minor" in roth else ""))
    if out["opportunities"]:
        console.print(f"\n[green]Unused headroom[/] (deadline {out['deadline']}):")
        for o in out["opportunities"]:
            console.print(f"  • {o['account']}: ${o['remaining_minor'] / 100:,.0f}")
    console.print(f"\n[dim]{out['disclaimer']}[/]")
```

- [ ] **Step 4: Run + lint/format/typecheck + commit**

```bash
~/.virtualenvs/homeFinance/bin/pytest tests/test_cli.py -v
~/.virtualenvs/homeFinance/bin/ruff check src tests && ~/.virtualenvs/homeFinance/bin/ruff format . && ~/.virtualenvs/homeFinance/bin/ruff format --check . && ~/.virtualenvs/homeFinance/bin/mypy
git add src/homefinance/cli.py tests/test_cli.py
git commit -m "feat(cli): retirement summary command"
```
Expected: 3 new tests pass; full test_cli.py still passes.

---

## Task 9: `homefinance-retirement` skill

**Files:**
- Create: `plugin/skills/homefinance-retirement/SKILL.md`

- [ ] **Step 1: Create `plugin/skills/homefinance-retirement/SKILL.md`**

```markdown
---
name: homefinance-retirement
description: Use when the user asks about retirement contributions, IRA/Roth/HSA limits, how much more they can contribute, whether they're eligible for a Roth, contribution deadlines, or wants to set up their retirement profile. Covers the SP4 tax-advantaged tools.
---

# homefinance — Retirement & tax-advantaged headroom

You help the user see how much tax-advantaged contribution room they have left — for Traditional IRA, Roth IRA, and HSA — and surface unused opportunities. **You state facts, never give advice.**

## Hard rules

- **Informational only — never prescriptive.** Report limits, headroom, eligibility, and deadlines. Do NOT say "you should contribute X." The user decides; you inform.
- **Always show the disclaimer.** Every tool returns a `disclaimer` field — surface it.
- **Numbers are for a specific tax year and from IRS sources.** Mention the `source` and remind the user to verify against current IRS publications.
- **Money is integer cents** in the tool I/O. Convert to dollars (`/100`) in your prose only.
- If a required input (MAGI, age, filing status) is missing, **ask — don't guess.** Roth eligibility needs MAGI + filing status; catch-up needs age.

## Setup

If the user has no `[retirement]` profile, help them add one to `~/.homefinance/config.toml`:

```toml
[retirement]
birth_year    = 1985
filing_status = "single"          # single | head_of_household | married_jointly | married_separately
magi_minor    = 14000000          # modified AGI in cents ($140,000)
hsa_coverage  = "family"          # self_only | family (omit if no HSA)

[retirement.contributed]          # contributions ALREADY made this tax year, in cents
traditional_ira_minor = 200000
roth_ira_minor        = 100000
hsa_minor             = 300000
```

This lives in the same 0o600 file as the YNAB token — MAGI stays local.

## Answering

- "How much more can I contribute?" → `retirement_summary(tax_year=<current>)`. Walk through each account's remaining headroom and the deadline.
- "Am I eligible for a Roth?" → `roth_eligibility(tax_year, filing_status, magi_minor)`. Explain full / partial / none and what the phase-out band means.
- "What are this year's limits?" → `contribution_limits(tax_year)`. Cite the `source`.
- Explain context honestly: the IRA limit is **shared** across Traditional + Roth (one bucket); HSA is separate and has a notable triple-tax advantage; contributions for a tax year can generally be made until the April filing deadline.
- An unknown tax year returns `{"error": "no_limit_data"}` — tell the user that year's figures aren't bundled and can be added to `irs_limits.toml`.

## Out of scope (say so honestly)

Employer 401(k)s, Traditional IRA deductibility phase-outs, backdoor Roth / conversions, and any portfolio or asset-allocation advice are not covered. Point the user to a qualified tax professional for those.
```

- [ ] **Step 2: Verify frontmatter + commit**

```bash
~/.virtualenvs/homeFinance/bin/python -c "
import re, pathlib
t = pathlib.Path('plugin/skills/homefinance-retirement/SKILL.md').read_text()
m = re.match(r'^---\n(.*?)\n---', t, re.DOTALL); assert m and 'name: homefinance-retirement' in m.group(1)
print('OK')
"
git add plugin/skills/homefinance-retirement/SKILL.md
git commit -m "feat(plugin): homefinance-retirement skill (facts-not-advice)"
```

---

## Task 10: Docs + final verification

**Files:**
- Modify: `README.md`, `docs/quickstart.md`, `docs/architecture.md`, `CHANGELOG.md`

- [ ] **Step 1: Update `README.md`** — in "What it does", add a bullet and flip the status line:

```markdown
- **Retirement headroom**: deterministic Traditional IRA / Roth IRA / HSA contribution limits, remaining headroom, Roth MAGI phase-out eligibility, and contribution deadlines from a bundled, cited, per-year IRS-limits file — informational only, never advice.
```

Update the status line to: `**Status:** SP1–SP4 complete (YNAB spine, statement ingestion, spending analytics, retirement headroom).` And update the skills list to include `homefinance-retirement` (six skills) and the program-status line to note SP4 done / program complete.

- [ ] **Step 2: Append to `docs/quickstart.md`** after the categorize/analyze section:

```markdown
## Retirement headroom

Declare your retirement profile once in `~/.homefinance/config.toml`:

```toml
[retirement]
birth_year    = 1985
filing_status = "single"
magi_minor    = 14000000        # MAGI in cents ($140,000)
hsa_coverage  = "family"

[retirement.contributed]        # already contributed this tax year, in cents
traditional_ira_minor = 200000
roth_ira_minor        = 100000
hsa_minor             = 300000
```

Then:

```bash
homefinance retirement summary --tax-year 2025
```

It shows each account's limit, what you've contributed, remaining headroom, Roth eligibility, and the deadline — with an *informational only, not advice* disclaimer. From Claude Code, `/homefinance:retirement` does the same conversationally and helps set up the profile.
```

- [ ] **Step 3: Extend `docs/architecture.md`** — under "Layout" add the `retirement/` subtree, and add a short section:

```markdown
retirement/              # SP4 tax-advantaged overlay (pure, deterministic; no DB, no new deps)
├── data/irs_limits.toml # year-keyed, cited IRS limits + Roth MAGI bands
├── limits.py            # fail-loud loader (unknown year → error, never a guess)
├── inputs.py            # [retirement] config parsing (Pydantic)
└── compute.py           # shared-IRA headroom, Roth phase-out, HSA, deadline, opportunities
```

```markdown
## Retirement overlay (SP4)

SP4 doesn't read the transaction store — it's an overlay fed by a bundled, cited per-year IRS-limits file plus a `[retirement]` config section. It computes deterministic facts: contribution headroom (the IRA limit is one shared Traditional+Roth bucket), Roth MAGI phase-out eligibility, HSA caps, and the contribution deadline. Every output is informational, carries a disclaimer, and never prescribes. Unknown tax years fail loud rather than guess; the data file is the single, citable correction point for new years.
```

- [ ] **Step 4: Update `CHANGELOG.md`** under `[Unreleased] / ### Added`:

```markdown
- SP4 retirement & tax-advantaged optimization: deterministic Traditional IRA / Roth IRA / HSA contribution headroom, Roth MAGI phase-out eligibility, HSA caps, and contribution deadlines from a bundled, cited, per-year IRS-limits file (2025 + 2026) that fails loud on unknown years. A `[retirement]` config section supplies birth year / filing status / MAGI / coverage / contributions-to-date (with per-call overrides). 3 MCP tools (`retirement_summary`, `contribution_limits`, `roth_eligibility`), a `retirement summary` CLI, and the `homefinance-retirement` skill. Informational only — every output carries a not-financial-advice disclaimer. No database migration; no new third-party dependencies.
```

- [ ] **Step 5: Full verification**

```bash
~/.virtualenvs/homeFinance/bin/pytest --cov=homefinance --cov-report=term --cov-fail-under=80
~/.virtualenvs/homeFinance/bin/ruff check .
~/.virtualenvs/homeFinance/bin/ruff format --check .
~/.virtualenvs/homeFinance/bin/mypy
```
Expected: all clean, coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/quickstart.md docs/architecture.md CHANGELOG.md
git commit -m "docs: SP4 retirement overlay in README/quickstart/architecture/changelog"
```

---

## Closing — what SP4 delivers

A deterministic retirement-headroom overlay: Traditional IRA / Roth IRA / HSA limits, remaining headroom (shared-IRA-aware), Roth MAGI phase-out eligibility, HSA caps, and contribution deadlines — from a bundled, cited, fail-loud per-year IRS-limits file plus a `[retirement]` config section. 3 MCP tools, a `retirement` CLI, and a facts-not-advice skill. No DB migration, no new dependencies, no LLM in any tested path. This completes the homeFinance program (SP1–SP4).

## Plan self-review

| Spec section | Implemented in |
|---|---|
| §3 C-14 (informational, disclaimer everywhere) | DISCLAIMER (T4) attached by every tool (T7); skill rules (T9) |
| §3 C-15 (year data, fail-loud) | `load_limits` + `LimitsNotFound` (T1); error path in tools (T7) |
| §3 C-16 (deterministic, no LLM) | compute.py pure functions (T4-6); LLM only in skill (T9) |
| §3 C-17 (verify numbers vs IRS) | T2 (explicit WebFetch verification + cite) |
| §4 package layout | T1, T3, T4 |
| §4.1 three account types + shared IRA | `ira_headroom` shared bucket (T4); hsa separate (T6) |
| §4.2 Roth phase-out formula | `roth_eligibility` (T5) — round-up-\$10 + \$200 floor |
| §5 irs_limits.toml shape | T1 (2025) + T2 (2026) |
| §6 [retirement] config | `inputs.py` (T3); summary reads it (T7) |
| §7 compute functions | T4 (ira, deadline), T5 (roth), T6 (hsa, opportunities) |
| §8.1 three MCP tools | T7 |
| §8.2 CLI | T8 |
| §8.3 skill | T9 |
| §9 error model + 3-tier tests | T1-T8 (validation, fail-loud, missing-config) |
| §10 out of scope | Not implemented (401k, deductibility, backdoor, etc.) — correct |

Type/signature consistency verified: `load_limits(tax_year) -> dict`, `ira_headroom(*, age, trad_contributed_minor, roth_contributed_minor, limits) -> dict`, `roth_eligibility(*, filing_status, magi_minor, age, limits) -> dict`, `hsa_headroom(...) -> dict | None`, `retirement_summary(*, tax_year, retirement_cfg, ...)` are referenced identically by the MCP wrappers (T7) and CLI (T8). DISCLAIMER text matches the spec verbatim. No placeholders (the `2025-XX` / "VERIFY" tokens in T1's data file are intentional and resolved in T2).

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-15-sp4-retirement.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review.

**2. Inline Execution** — batch with checkpoints.

Defaulting to subagent-driven unless told otherwise.
