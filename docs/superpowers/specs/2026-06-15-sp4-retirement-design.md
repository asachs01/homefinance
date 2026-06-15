# SP4 — Retirement & Tax-Advantaged Optimization — Design Spec

| | |
|---|---|
| **Status** | Draft (user pre-approved recommendations; spec for record + plan input) |
| **Sub-project** | SP4 of the homeFinance program (the final one) |
| **Date** | 2026-06-15 |
| **Depends on** | SP1 (config + store), SP2, SP3 — all merged to `main` |
| **Successor** | Implementation plan via `superpowers:writing-plans` |

---

## 1. Context

SP1 shipped the store + YNAB sync; SP2 added statement ingestion; SP3 added the analytics layer. SP4 is the program's final piece, named in SP1 §1: *optimize retirement contributions across Traditional IRA, Roth IRA, and HSA accounts* and "help folks get the most out of their existing money."

SP4 is **architecturally different** from SP1–SP3. Those moved and analyzed *data already in the store*. SP4 produces **guidance about tax-advantaged retirement money** — and the numbers (contribution limits, catch-up amounts, Roth MAGI phase-out bands) are **US-specific and tax-year-specific**. Wrong or stale numbers actively mislead, so SP4's design is built around *correctness, currency, and an explicit advice boundary* more than around data movement.

### 1.1 The data gap

The store models accounts with a generic `type` (at most `investment` / `other`) and transactions. It has **no** notion of: which account is a Roth IRA, contributions-to-date this tax year, the user's MAGI, filing status, age, or HSA coverage type. Most of these aren't derivable from transactions (MAGI is a tax-return figure; brokerage-internal contributions rarely appear as bank transactions; age/filing status are personal facts). **SP4 is therefore an overlay fed by user-declared inputs + a bundled IRS-limits reference — not something computed from existing rows.**

---

## 2. Program position

| # | Sub-project | Status |
|---|---|---|
| SP1 | Foundation + YNAB spine | Merged |
| SP2 | Statement & bill ingestion | Merged |
| SP3 | Spending & cash-flow analysis | Merged |
| **SP4** | **Retirement & tax-advantaged optimization** *(this spec)* | Brainstorm complete |

---

## 3. Constraints (delta)

All prior constraints carry over. SP4 adds:

| | Constraint | Reasoning |
|---|---|---|
| **C-14** | **Informational, not advice.** Every SP4 output carries a disclaimer; tools state facts and headroom, never directives ("you should…"). | Open-source self-hosted tool; we don't have the user's full financial picture and aren't qualified to give financial/tax advice. (Posture decision Q1=A.) |
| **C-15** | **Year-specific numbers are data, cited, and fail-loud.** IRS limits live in a bundled per-year TOML with a `source` per year. A tax year not in the file produces an explicit refusal, never a guessed number. | Staleness is the top correctness risk. A wrong-but-authoritative-looking number is the worst failure. (Limits decision Q2=A.) |
| **C-16** | **All computation deterministic; no LLM in the math path.** Claude explains context at the skill layer only. | Consistent with SP2/SP3. Money/eligibility math must be testable and reproducible. |
| **C-17** | **Numbers verified against the IRS source at implementation time.** The data file's 2025 and 2026 entries must be checked against the cited IRS publication before SP4 ships; the file is the single correction point thereafter. | Protects against shipping stale/incorrect figures; isolates "is the logic correct" (fully unit-tested) from "are the numbers current" (verified + trivially correctable). |

---

## 4. Architecture overview

A new self-contained `src/homefinance/retirement/` package. **No new third-party dependencies** (stdlib `tomllib` + existing `pydantic`). No database migration — SP4 reads config + a bundled data file, writes nothing to the store.

```
src/homefinance/retirement/
├── __init__.py
├── data/
│   └── irs_limits.toml      # year-keyed limits + Roth MAGI bands + source citations
├── limits.py                # load + validate the data file; fail-loud on unknown year
├── inputs.py                # parse the [retirement] config section (Pydantic)
└── compute.py               # pure functions: headroom, Roth phase-out, HSA caps, deadline, opportunities
```

### 4.1 The three account types (v1 scope)

| Account | Limit basis | Catch-up | Notes |
|---|---|---|---|
| **Traditional IRA** | Shares ONE combined IRA limit with Roth | age ≥ 50 | Contribution always allowed; *deductibility* phase-out is out of scope (see §10). |
| **Roth IRA** | Shares the combined IRA limit; the Roth *sub-limit* is reduced by the MAGI phase-out | age ≥ 50 | Phase-out keyed to filing status + MAGI. |
| **HSA** | Separate limit; self-only vs family cap | age ≥ 55 | Requires an HSA-eligible HDHP (user-declared; SP4 doesn't verify eligibility). |

**The shared-IRA rule is load-bearing.** Traditional + Roth contributions draw from a *single* annual IRA bucket (e.g. $7,000 combined in 2025, not $7,000 each). $4,000 in Roth ⇒ $3,000 of remaining IRA headroom, allocable to either. HSA is independent.

### 4.2 Roth MAGI phase-out (the formula)

Given filing status + MAGI for the tax year, the Roth contribution sub-limit is:

- **MAGI < phase-out low** → full IRA limit available as Roth.
- **MAGI ≥ phase-out high** → $0 Roth (Traditional still available for the full IRA bucket).
- **In the band** → reduced per the IRS worksheet:
  `reduced = limit × (1 − (MAGI − low) / (high − low))`, rounded **up to the nearest $10**; if the result is `> $0` and `< $200`, it is floored to **$200**.

The bands differ by filing status (single/HoH, married-filing-jointly, married-filing-separately).

---

## 5. Data model — `irs_limits.toml`

Year-keyed, cited. Shape (illustrative; 2026 figures **must be verified at implementation** per C-17):

```toml
[2025]
source = "IRS Notice 2024-80 / Rev. Proc. 2024-25 (verify at irs.gov)"
ira_limit_minor          = 700000      # $7,000 combined Traditional + Roth
ira_catchup_minor        = 100000      # +$1,000 at age >= 50
ira_catchup_age          = 50
hsa_self_only_minor      = 430000      # $4,300
hsa_family_minor         = 855000      # $8,550
hsa_catchup_minor        = 100000      # +$1,000 at age >= 55
hsa_catchup_age          = 55

[2025.roth_phaseout.single]            # also covers head_of_household
low_minor  = 15000000                  # $150,000
high_minor = 16500000                  # $165,000

[2025.roth_phaseout.married_jointly]
low_minor  = 23600000                  # $236,000
high_minor = 24600000                  # $246,000

[2025.roth_phaseout.married_separately]
low_minor  = 0
high_minor = 1000000                   # $10,000

[2026]
source = "IRS Notice 2025-XX (VERIFY at irs.gov before release)"
# ... same keys; 2026 values verified against the IRS source at implementation time ...
```

All money is **integer minor units (cents)**, consistent with the whole program. The loader validates that every required key is present for a year and raises a clear error otherwise.

---

## 6. The `[retirement]` config section

Added to `~/.homefinance/config.toml` (SP1's secure, gitignored, 0o600 file). Parsed by `inputs.py` into a Pydantic model; absent section → SP4 tools return a friendly "configure retirement first" message (never crash).

```toml
[retirement]
birth_year     = 1985
filing_status  = "single"        # single | head_of_household | married_jointly | married_separately
magi_minor     = 14000000        # $140,000 modified AGI (sensitive — stays in the 0o600 file)
hsa_coverage   = "family"        # "self_only" | "family" | none if no HSA

[retirement.contributed]         # contributions already made for the CURRENT tax year, in cents
traditional_ira_minor = 200000   # $2,000
roth_ira_minor        = 100000   # $1,000
hsa_minor             = 300000   # $3,000
```

Age is derived as `tax_year − birth_year` (catch-up eligibility uses age attained during the tax year — a documented simplification; SP4 doesn't model mid-year birthdays). Any field is overridable per tool call for "what-if" scenarios (e.g. `magi_override`).

---

## 7. Computation (all pure, deterministic) — `compute.py`

| Function | Output |
|---|---|
| `ira_headroom(...)` | Combined IRA limit (with catch-up), total IRA contributed (trad + roth), remaining shared headroom. |
| `roth_eligibility(tax_year, filing_status, magi, limits)` | Status (`full` / `partial` / `none`), the reduced Roth sub-limit, the band, and remaining Roth headroom given Roth contributed. |
| `hsa_headroom(...)` | Self-only or family cap (with 55+ catch-up), HSA contributed, remaining headroom — or "no HSA configured". |
| `contribution_deadline(tax_year)` | The contribution deadline: the federal tax-filing deadline, computed as April 15 of `tax_year + 1` (a documented simplification — does not adjust for weekends/holidays/extensions). |
| `opportunities(...)` | A list of flagged unused-headroom items, each with account, amount remaining, and the deadline. |

---

## 8. Surface

### 8.1 MCP tools (3)

| Tool | Returns |
|---|---|
| `retirement_summary(tax_year?, magi_override?, age_override?)` | The whole picture: per-account limit / contributed / headroom, Roth eligibility, HSA cap, deadline, opportunities, and the `disclaimer`. `tax_year` defaults to the current tax year. |
| `contribution_limits(tax_year, filing_status?, age?)` | Raw limits for a year (IRA, Roth bands, HSA), with the `source` citation and `disclaimer`. |
| `roth_eligibility(tax_year, filing_status, magi_minor)` | Phase-out status + reduced Roth limit + `disclaimer`. |

Every tool output includes a `disclaimer` field (C-14). An unknown tax year returns `{"error": "no_limit_data", "message": "no IRS limit data for <year>; add it to irs_limits.toml"}` (C-15) rather than computing.

### 8.2 CLI

- `homefinance retirement summary [--tax-year YYYY] [--magi DOLLARS]` — Rich table of the per-account headroom + opportunities + deadline, with the disclaimer printed.

### 8.3 Skill

`homefinance-retirement` (new) — helps the user populate the `[retirement]` config section, then calls `retirement_summary` and explains it: what headroom means, why HSA's triple-tax-advantage is notable, what the Roth phase-out implies, and the deadline. **Embeds the rules:** always attach the disclaimer; state facts and trade-offs, never "you should"; if MAGI/age aren't configured, ask rather than guess; remind the user the numbers are for the stated tax year and to verify against the IRS.

---

## 9. Error handling + testing

### 9.1 Error model

| Condition | Behavior |
|---|---|
| Tax year not in `irs_limits.toml` | `no_limit_data` error (tool) / clear CLI message. Never guess. |
| `[retirement]` section absent | Friendly "configure retirement first" result; never crash. |
| Invalid `filing_status` / `hsa_coverage` enum | Reject at config-parse time with the valid set. |
| MAGI / contributed not provided and no override | For `retirement_summary`, surface which inputs are missing and what they gate (e.g. "MAGI needed to assess Roth eligibility"); compute what is possible. |

### 9.2 Testing — deterministic, three tiers

| Tier | Coverage |
|---|---|
| Unit | Limits loader (valid year, missing-key rejection, **unknown-year fail-loud**). Shared-IRA headroom (trad+roth draw one bucket; over-contribution → zero, not negative). Roth phase-out at **band boundaries** (just below low → full; mid-band → pro-rated with the round-up-$10 + floor-$200 rule; at/above high → zero; MFS $0–$10k band). HSA self-only vs family + 55+ catch-up + no-HSA. Deadline = April-15-of-next-year. |
| Integration | `retirement_summary` over a seeded `[retirement]` config: correct per-account numbers, opportunities list, disclaimer present. Override path (`magi_override`) changes Roth status. Missing-section path returns the friendly message. |
| End-to-end | `homefinance retirement summary` CLI; the 3 MCP tools as plain functions (SP1-3 pattern). |

**Logic is tested primarily against the 2025 figures** (high-confidence). A structural test asserts 2026 loads and has all required keys; the *values* are verified against the IRS source per C-17 (an explicit implementation step), keeping "logic correct" separate from "numbers current." No LLM in any test. Coverage gate 80%. No new dependencies → CI unchanged.

---

## 10. Out of scope

| | What | Why |
|---|---|---|
| OS-1 | Employer 401(k)/403(b)/457 plans | Different limits + employer-match + vesting complexity; v1 covers the three SP1-named account types. Easy to add as a later data-file + compute extension. |
| OS-2 | Traditional IRA *deductibility* phase-out (workplace-plan-coverage MAGI bands) | The contribution *limit* is unaffected by MAGI (only deductibility is); modeling deductibility needs workplace-plan-coverage facts and adds significant rule surface. Headroom (the optimization goal) is correct without it. Document as a known limitation. |
| OS-3 | Backdoor/mega-backdoor Roth, conversions, recharacterizations | Advanced strategies; cross into advice territory (C-14). |
| OS-4 | Prescriptive recommendations / portfolio/asset-allocation advice | C-14 — out of posture. |
| OS-5 | Weekend/holiday/extension adjustment of the contribution deadline | A documented simplification; April 15 of the following year is the headline date. |
| OS-6 | Non-US tax-advantaged accounts (ISA, RRSP, etc.) | US-only for v1; the data-file structure could be generalized later. |
| OS-7 | Auto-detecting contributions from transactions | Brokerage-internal contributions rarely appear as categorizable bank transactions; user-declared in config is the reliable source. |

---

## 11. Open questions / parked

| | Question | When |
|---|---|---|
| OQ-1 | Whether to add 401(k) as a fourth account type | After v1, if the user wants employer-plan headroom too |
| OQ-2 | Whether to model the Traditional IRA deduction phase-out (OS-2) | If a user actually needs deductibility guidance |
| OQ-3 | Multi-year contribution history (vs current-tax-year only) | If the user wants to track prior years; v1 is current-year-driven (that's what the deadline acts on) |

---

## 12. Next steps

1. Invoke `superpowers:writing-plans`.
2. Build via subagent-driven development on `sp4-retirement` (off `main`). **The plan includes an explicit step to verify the 2025 + 2026 figures against the IRS source and cite them in `irs_limits.toml`.**
3. This completes the homeFinance program (SP1–SP4).
