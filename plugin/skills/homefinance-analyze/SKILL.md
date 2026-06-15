---
name: homefinance-analyze
description: Use when the user asks about cash flow, income vs spending, spending trends over time, recurring charges or subscriptions, upcoming bills, or unusual/anomalous spending. Covers the SP3 analytics tools.
---

# homefinance — Analyze spending & cash flow

You answer analytical questions over the user's categorized transaction store.

## Tools

- `cash_flow(date_from?, date_to?, group_by='month'|'week', source_id?)` — inflow / outflow / net per period. **Transfers are excluded** (internal moves don't count as income or spending). Confirmed-only.
- `summarize_spending(group_by='canonical_category', …)` — spending by your unified category vocabulary across YNAB + statements. Prefer `canonical_category` over the per-source `category` for cross-source views.
- `detect_recurring(min_occurrences?, amount_tolerance_minor?)` — recurring charges with a typical amount, cadence (weekly/monthly/…), last-seen, **next-expected** date, and a confidence score.
- `detect_anomalies(trailing_months?, z_threshold?)` — category-month spend spikes vs a trailing baseline, with z-scores.

## How to answer well

- **Money is signed integer cents.** Convert to dollars (`/100`, two decimals) only in your prose, never in tool arguments.
- For "how am I doing?" → `cash_flow(group_by='month')`; report net per month and the trend.
- For "where does my money go?" → `summarize_spending(group_by='canonical_category')` over the period.
- For "what subscriptions am I paying?" → `detect_recurring`; lead with the highest-confidence series and the next-expected dates.
- For "anything unusual?" → `detect_anomalies`; explain each flag in plain terms (category X was N× its usual month).
- If results look thin, check whether categorization has been run — suggest `/homefinance:categorize`. Uncategorized spend shows up under `(uncategorized)`.
- Never include `pending_review` (unconfirmed statement) rows — the tools already exclude them.

## Honesty

If a question needs something these tools don't compute (budget targets, projections beyond a recurring forecast, retirement planning), say so — those are out of scope for SP3 (retirement is SP4).
