---
name: homefinance-explore
description: Use when the user wants a guided first look at their financial data, asks "show me my finances at a glance", asks about spending by category or by month, asks about balances or recent transactions, or invokes /homefinance:explore. Exercises the full read-tool surface.
---

# homefinance — Explore the data

You are giving the user a guided first look at their finances using the homefinance MCP tools.

## Tool surface (8 tools)

- `list_sources` — registered budgets, last-sync info
- `list_accounts(source_id?, include_closed?)` — accounts with balances
- `get_account(account_id)` — one account + latest reconciliation
- `list_categories(source_id?, include_hidden?)` — category list
- `query_transactions(filters, mode='leaves'|'tops')` — transaction listing. **Always reach for `mode='leaves'`** (the default) when you'll sum amounts or group by category. Use `mode='tops'` only when the user wants the "one row per user-facing transaction" view.
- `summarize_spending(filters, group_by)` — aggregate over the Leaves view; `group_by ∈ {category, payee, month, account, day_of_week}`.
- `get_sync_status` — when the user asks "is this data current?"
- `sync_ynab(source_id?)` — only when the user explicitly asks to sync.

## Canonical opening questions to offer

Pick one based on context; do not ask all four:

1. **"Show me my finances at a glance."** → `list_sources` then `list_accounts`. Render account balances in a small table grouped by `type` (checking, savings, credit_card). Convert `*_minor` cents to dollars in the *output*, not in queries.

2. **"What did I spend on dining last month?"** → resolve "dining" against `list_categories` (look for "Dining Out", "Restaurants", or similar). Use `summarize_spending(group_by='category', date_from=<month-start>, date_to=<month-end>)`. If the user asks for a list, follow with `query_transactions(category_id=…, date_from=…, date_to=…)`.

3. **"How has my spending trended?"** → `summarize_spending(group_by='month')` over the last 6-12 months. Present as a small markdown table; flag any month that is >25% off the median.

4. **"What were my biggest expenses last month?"** → `query_transactions(date_from=…, date_to=…, amount_max_minor=-some_threshold)` sorted by absolute amount.

## Rules

- Amounts are stored in **signed integer minor units (cents)**. Negative = outflow. Convert to dollars only in user-facing output.
- Never call `sync_ynab` unprompted. The user controls when to refresh.
- Statement-imported transactions live in two states: **`confirmed`** (analytically visible) and **`pending_review`** (excluded by default). If the user explicitly asks "what's awaiting review?" pass `include_pending=True` to `query_transactions`. Never include pending rows in spending summaries — `summarize_spending` already filters them out.
- If `get_sync_status` shows `pending_batch_count > 0` for any source, mention it: the user may have forgotten to confirm a batch. Suggest `/homefinance:import-statement` or `homefinance batch confirm <id>`.
- If `get_sync_status` shows `last_reconciliation = 'drift'`, mention it briefly when relevant (e.g., the user asks about balances) but do not block the analysis.
- For category questions, prefer **`summarize_spending(group_by='canonical_category')`** — it unifies YNAB and statement categories. If statement spend is large and shows under `(uncategorized)`, suggest `/homefinance:categorize` first.
- For cash flow, trends, recurring charges, or anomalies, hand off to **`/homefinance:analyze`** rather than answering from raw `query_transactions` output.
- If the user asks a question the read tools cannot answer (e.g., budget targets, retirement planning), say so honestly — retirement lands in SP4.

## When the user asks "is anything off?"

Run `get_sync_status`. If `drift_account_count > 0`, surface the affected accounts via the `drift_report` JSON and suggest a re-sync via `sync_ynab`.
