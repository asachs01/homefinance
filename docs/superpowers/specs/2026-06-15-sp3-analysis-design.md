# SP3 — Spending & Cash-Flow Analysis — Design Spec

| | |
|---|---|
| **Status** | Draft (user pre-approved recommendations; spec for record + plan input) |
| **Sub-project** | SP3 of the homeFinance program |
| **Date** | 2026-06-15 |
| **Depends on** | SP1 (foundation + YNAB) and SP2 (statement ingestion) — both merged to `main` |
| **Successor** | Implementation plan via `superpowers:writing-plans` |

---

## 1. Context

SP1 shipped the canonical store + YNAB sync; SP2 added statement-file ingestion (CSV/OFX/QFX/PDF) behind the same `AccountSource` seam. SP3 is the **analytics layer**: it turns the accumulated, multi-source transaction store into spending insight.

SP3 delivers all four feature areas from the program map in one sub-project, each kept minimal-but-complete:

1. **Categorization & canonical taxonomy** (the foundation the rest build on)
2. **Cash-flow & trends**
3. **Recurring & bill forecasting**
4. **Anomaly detection**

It resolves the SP1/SP2 parked items: OS-3 (categorization rules / fuzzy matching), OS-4 (analytics beyond `summarize_spending`), OS-8 / OQ-2 (canonical category unification), and OQ-1 (`list_payees` tool).

### 1.1 The keystone problem

YNAB rows arrive already categorized; **statement-ingested rows have `category_id = NULL`**, and YNAB categories are per-source (budget-scoped). So "spending by category" works today only for YNAB data and bins all statement spending into `(uncategorized)`. SP3's categorization slice fixes this, and the three analytics slices are dramatically richer once it lands.

---

## 2. Program position

| # | Sub-project | Status |
|---|---|---|
| SP1 | Foundation + YNAB spine | **Merged** |
| SP2 | Statement & bill ingestion | **Merged** (PR #1) |
| **SP3** | **Spending & cash-flow analysis** *(this spec)* | Brainstorm complete; spec for review |
| SP4 | Retirement & tax-advantaged optimization | Not started |

---

## 3. Constraints (delta from SP1/SP2)

Every prior constraint carries over. SP3 adds:

| | Constraint | Reasoning |
|---|---|---|
| **C-11** | **Categorization never overwrites YNAB-provided categories** | YNAB is the source of truth for its rows and re-overwrites on every sync. SP3 fills the `NULL`s (statement rows) and derives a canonical layer; it never mutates a YNAB row's `category_id`. |
| **C-12** | **Deterministic analytics; LLM only for the categorization long tail** | Cash-flow, trends, recurring, and anomaly tools are pure, testable code (no LLM in CI). Claude assists *only* in suggesting categories for unmatched payees — and those suggestions are promoted into deterministic rules, so the system converges toward fully deterministic. Mirrors SP2's "no LLM in the money path." |
| **C-13** | **Re-runnable categorization is idempotent and respects manual edits** | The categorization pass can run any number of times. It (re)derives `ynab` and `rule` assignments but never clobbers a `manual` assignment. |

---

## 4. Architecture overview

### 4.1 The canonical category layer (mirror-YNAB)

The canonical vocabulary **is the set of YNAB category names**. No second taxonomy to maintain.

- **YNAB rows:** `canonical_category` = the `name` of their `category_id`'s category. Derived, deterministic, always.
- **Statement rows:** `canonical_category` = whatever the rule engine (or a confirmed Claude suggestion) assigned — by convention one of the existing YNAB category names, with a free-text escape hatch for statement-only categories YNAB lacks.
- **Cross-source analysis** groups by `canonical_category`; YNAB-native analysis can still group by the per-source `category_id` as before.

### 4.2 Hybrid categorization

```
                ┌─────────────── apply_categorization() pass ───────────────┐
 YNAB rows ────▶│ derive canonical_category from YNAB category name (source='ynab') │
 statement ────▶│ run ordered rules (first match wins) → canonical_category (source='rule')│
   rows         │ unmatched → canonical_category stays NULL (surfaced to the user)         │
                └───────────────────────────────────────────────────────────┘
                                   ▲                         │
                                   │ promote                 ▼ suggest
                          add_category_rule          suggest_categories  ──▶ Claude proposes
                                   │                         │                from YNAB names
                                   └──── user confirms ◀──────┘
                                         (writes source='manual' or a new rule)
```

- **Rules** are ordered (`priority` ASC), match `payee` or `memo` by substring or regex, and assign a `canonical_category`.
- **Claude's role** is bounded: it reads the uncategorized-payee list from `suggest_categories`, proposes a `canonical_category` for each (constrained to existing YNAB names where possible), and the user either accepts (writes a `manual` assignment) or promotes the pattern into a rule. Claude never writes amounts; it only proposes category labels for human confirmation.
- **`manual` precedence:** a manual assignment is sticky — re-running `apply_categorization` never overwrites `category_source='manual'` rows.

### 4.3 The four analytics tools are deterministic

| Tool | Method |
|---|---|
| `cash_flow` | SUM of inflow (amount > 0) / outflow (amount < 0) / net per period (month/week), Leaves view, confirmed-only, **transfers excluded**. |
| `detect_recurring` | Group by `(payee, amount within tolerance)`; compute the median gap between occurrences; if regular, emit the series + a forecast `next = last_date + median_gap` with a confidence score. |
| `detect_anomalies` | Per `(canonical_category, month)`, compute trailing-N-month mean/σ; flag months (or large single transactions) exceeding a z-score threshold. |
| `summarize_spending` *(extended)* | Gains `group_by='canonical_category'`. |

All four are pure SQL + arithmetic — no Claude at runtime, fully unit-testable.

---

## 5. Repository delta

```
src/homefinance/
├── db/migrations/0003-categorization-analytics.sql   ← new
├── analysis/                                          ← SP1 created this empty; SP3 fills it
│   ├── __init__.py
│   ├── categorize.py        # rule engine + apply pass + suggest + promote
│   ├── cashflow.py          # inflow/outflow/net by period
│   ├── recurring.py         # periodicity detection + forecast
│   └── anomaly.py           # category-month z-score baseline
├── mcp_server/
│   ├── tools.py             # +7 tools; summarize_spending extended
│   └── __main__.py          # +7 @mcp.tool() wrappers
└── cli.py                   # + `categorize` command group (apply / rules add|list)

plugin/skills/
├── homefinance-categorize/SKILL.md    ← new (rule-building + Claude long-tail loop)
├── homefinance-analyze/SKILL.md       ← new (cash-flow / trends / recurring / anomalies)
└── homefinance-explore/SKILL.md       ← edited (point at the new analysis skills + canonical_category)

tests/
├── test_categorize.py
├── test_cashflow.py
├── test_recurring.py
├── test_anomaly.py
├── test_mcp_tools.py        ← extended (new tools)
└── test_cli.py              ← extended (categorize commands)
```

No new third-party dependencies — SP3 is stdlib + the existing stack (`sqlite3`, `pydantic`, `typer`, `rich`, `mcp`). Anomaly/recurring math is plain Python (no `numpy`/`pandas` — household data volumes don't warrant it, and it keeps the lean install lean).

---

## 6. Data model — migration 0003

```sql
-- Migration 0003: categorization rules + canonical category columns.

CREATE TABLE category_rules (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    priority           INTEGER NOT NULL,            -- lower = evaluated first
    match_field        TEXT NOT NULL,               -- 'payee' | 'memo'
    pattern            TEXT NOT NULL,               -- substring or regex source
    is_regex           INTEGER NOT NULL DEFAULT 0,
    canonical_category TEXT NOT NULL,               -- target canonical category name
    note               TEXT,
    created_at         TEXT NOT NULL
);

CREATE INDEX idx_category_rules_priority ON category_rules(priority);

ALTER TABLE transactions ADD COLUMN canonical_category TEXT;          -- NULL = uncategorized
ALTER TABLE transactions ADD COLUMN category_source    TEXT;          -- 'ynab' | 'rule' | 'manual' | NULL

CREATE INDEX idx_transactions_canonical ON transactions(canonical_category);
```

`canonical_category` defaults to `NULL` (uncategorized) on the `ADD COLUMN`, so existing rows are untouched until the first `apply_categorization` pass derives values. The pass is the single writer of these two columns.

### 6.1 The `apply_categorization` pass (idempotent)

For every non-deleted, non-split-parent transaction:

1. If `category_source = 'manual'` → **skip** (sticky).
2. Else if the row has a YNAB `category_id` (provenance `ynab`) → set `canonical_category` = that category's `name`, `category_source = 'ynab'`.
3. Else (statement row, or YNAB row with no category) → evaluate `category_rules` in `priority` order; first match sets `canonical_category` + `category_source = 'rule'`.
4. No match → leave both `NULL`.

Re-running re-derives steps 2–3 deterministically; manual rows (step 1) are immune. The whole pass runs inside one SQLite transaction.

---

## 7. MCP + CLI + skill surface

### 7.1 Seven new MCP tools (total surface: 19)

| Tool | Purpose |
|---|---|
| `add_category_rule(priority, match_field, pattern, is_regex, canonical_category, note?)` | Append a rule. |
| `list_category_rules()` | Ordered rules. |
| `apply_categorization(source_id?)` | Run the idempotent pass; returns counts (`ynab`/`rule`/`manual`/`uncategorized`). |
| `suggest_categories(limit?)` | Distinct uncategorized payees + sample rows, for the Claude long-tail loop. Returns the existing YNAB category-name set so Claude constrains its suggestions. |
| `set_transaction_category(transaction_id, canonical_category)` | Write a `manual` assignment (the "user confirmed a suggestion" path). |
| `list_payees(source_id?, name_contains?)` | OQ-1, finally. |
| `cash_flow(date_from?, date_to?, group_by='month', source_id?)` | Inflow / outflow / net per period; transfers excluded; confirmed-only. |
| `detect_recurring(min_occurrences=3, amount_tolerance_minor=200)` | Recurring series + next-occurrence forecast + confidence. |
| `detect_anomalies(trailing_months=6, z_threshold=2.0)` | Flagged category-month spikes / large single transactions. |

`summarize_spending` gains `group_by='canonical_category'` (and keeps all existing modes). All inherit the confirmed-only + Leaves disciplines from SP2.

### 7.2 CLI

A `categorize` command group:
- `homefinance categorize apply [--source <id>]` — run the pass; print the counts table.
- `homefinance categorize rules add --field payee --pattern "TRADER JOE" --category Groceries [--regex] [--priority N]`
- `homefinance categorize rules list`

Analytics stay MCP/skill-first (they're exploratory, not scriptable setup) — no new top-level analysis CLI commands in v1.

### 7.3 Skills

| Skill | Status | Purpose |
|---|---|---|
| `homefinance-categorize` | New | Runs `apply_categorization`, then drives the loop: `suggest_categories` → propose canonical labels (constrained to YNAB names) → user confirms → `set_transaction_category` or `add_category_rule` → re-apply. Embeds the rule: **suggest labels only, never amounts; always get human confirmation.** |
| `homefinance-analyze` | New | Cash-flow / trends / recurring / anomalies via the new tools. Converts `*_minor` cents → dollars in output; never includes `pending_review`; explains transfers are excluded from cash flow. |
| `homefinance-explore` | Edited | Points at the two new skills and notes `group_by='canonical_category'`. |

---

## 8. Analytics definitions (locked)

### 8.1 Cash flow

- **Inflow** = Σ `amount_minor` where `amount_minor > 0`. **Outflow** = Σ where `< 0`. **Net** = Σ all.
- **Transfers excluded**: rows with `transfer_account_id IS NOT NULL` are dropped (internal moves between the user's own accounts must not count as income or spending).
- Leaves view (`is_split_parent = 0`), `deleted = 0`, `status = 'confirmed'`.
- `group_by` ∈ {`month`, `week`}.

### 8.2 Recurring detection

- Candidate series = transactions sharing a `payee` with `amount_minor` within `amount_tolerance_minor`.
- A series qualifies if it has ≥ `min_occurrences` and a *regular* cadence — measured by the median gap between sorted dates and the dispersion of those gaps.
- **Forecast:** `next_expected = last_date + median_gap`. **Confidence** = function of occurrence count and gap regularity (low dispersion → high confidence).
- Output: payee, typical amount, cadence label (weekly/biweekly/monthly/quarterly/annual when the median gap is near a known period), last seen, next expected, confidence.

### 8.3 Anomaly detection

- For each `(canonical_category, month)`, compute the spend total. Over a trailing window of `trailing_months`, compute mean and population σ of the monthly totals.
- Flag a month whose total exceeds `mean + z_threshold·σ` (category-level spike).
- Additionally flag any single transaction larger than `z_threshold·σ` above its category's mean transaction size (point anomaly).
- Categories with too few data points to form a baseline are skipped (reported as "insufficient history", never falsely flagged).

---

## 9. Error handling + testing

### 9.1 Error model

| Condition | Behavior |
|---|---|
| Invalid regex in a rule | `add_category_rule` validates `re.compile` at write time; rejects with a clear message. |
| `set_transaction_category` on unknown `transaction_id` | Raise `KeyError`-style error surfaced as `{"error": ...}` to MCP callers. |
| `match_field` not in {`payee`,`memo`} | Reject at write time. |
| Empty store / no history for recurring or anomaly | Return empty results + an explanatory note; never raise. |

### 9.2 Testing — three tiers, all deterministic

| Tier | Coverage |
|---|---|
| Unit | Rule engine (priority order, substring vs regex, first-match-wins, manual stickiness, YNAB-name derivation). Cash-flow math (transfer exclusion, inflow/outflow/net). Recurring (median-gap cadence, forecast, confidence, irregular series rejected). Anomaly (z-score flagging, insufficient-history skip). |
| Integration | `apply_categorization` over a seeded store mixing YNAB-categorized + statement-uncategorized rows: YNAB rows derive names, rules fill statement rows, manual rows stick across re-runs. End-to-end categorize → `summarize_spending(group_by='canonical_category')` reflects the new categories. |
| End-to-end | `homefinance categorize apply/rules` CLI; the 7 MCP tools called as plain functions (SP1/SP2 pattern). |

**No LLM in any test** — the categorization long tail (Claude suggestions) is a skill-level workflow, not a code path, so it isn't unit-tested; the deterministic rule path that backs it is fully covered. Coverage gate stays at **80%**. Default CI unchanged (no new deps).

---

## 10. Out of scope

| | What | Where |
|---|---|---|
| OS-1 | Budgeting / envelope targets (spend vs budgeted) | Future; YNAB already does budgeting, so low value here |
| OS-2 | ML-based auto-categorization (training a model) | Never — the rule + Claude-suggestion loop is sufficient and deterministic |
| OS-3 | Multi-currency normalization in analytics | Future; current data is single-currency per account |
| OS-4 | Scheduled/alerting anomaly notifications | Never within SP3 (no daemon — preserves the SP1 stance); anomalies are pull-based via the tool |
| OS-5 | Retirement / tax-advantaged optimization | SP4 |
| OS-6 | Numpy/pandas analytics engine | Never — household volumes don't warrant it; stdlib math keeps the install lean |

---

## 11. Open questions / parked

| | Question | When |
|---|---|---|
| OQ-1 | Whether to cache recurring-series detection vs recompute each call | If recompute latency is ever felt (unlikely at household scale) |
| OQ-2 | Cadence labels beyond weekly/biweekly/monthly/quarterly/annual | If a real series doesn't fit; add as needed |
| OQ-3 | Whether `homefinance-analyze` should split into per-feature skills | After dogfooding, if the single skill gets unwieldy |

---

## 12. Next steps

1. (Optional) user reviews this spec.
2. Invoke `superpowers:writing-plans` to produce the implementation plan.
3. Build via subagent-driven development on the `sp3-analysis` branch (off `main`, which now has SP1+SP2).
