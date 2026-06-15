---
name: homefinance-import-statement
description: Use when the user asks to import or ingest a bank or credit-card statement, mentions a path to a .csv/.ofx/.qfx/.pdf file in a financial context, asks about pending batches awaiting review, or invokes /homefinance:import-statement. Walks the user through parse → preview → confirm/reject with money-safety guardrails.
---

# homefinance — Import a statement

You are helping the user import one statement file (CSV / OFX / QFX / PDF) into the local homefinance store.

## Pre-flight

1. Confirm the statement-fed **account** the file belongs to. If the user didn't specify, call `list_sources` and offer the statement-kind sources as choices. If the right account isn't registered, tell them to run `homefinance accounts add --nickname <nick> --type <type>` first (or do it for them via MCP — there is no `register_statement_account` MCP tool, so this step is CLI-only).

2. Confirm the file path exists. Don't guess.

## The flow

1. **`ingest_statement(path, account_nickname)`** — parses, stages, returns a `BatchPreview` dict.
2. **Always show the preview** — list `txn_count`, `reconciliation_status`, `drift_minor` (if any), `statement_period_start` / `_end`, and the first few transactions (under `first_transactions`).
3. **Then ask the user**: confirm, reject, or look at more details.

## Reconciliation status — how to read it

- `reconciliation_status='ok'` — the parser's sum matches the statement's opening→closing delta exactly. **Confirmation is low-risk.** Suggest confirm, but still require an explicit "yes" before calling `confirm_batch`.
- `reconciliation_status='drift'` — there is a `drift_minor` mismatch. Show the drift in dollars (`drift_minor / 100`). Walk through the per-row preview; ask the user whether one of the rows looks wrong. Do not confirm until they look at it.
- `reconciliation_status='n/a'` — the parser couldn't extract opening or closing balance, so there's no reconciliation safety net. Emphasize that **manual review is the only check**. Offer to render the full transaction list.

## Rules

- **Never auto-confirm.** Even when reconciliation is `ok`, require an explicit human approval.
- After the user approves: call `confirm_batch(batch_id)`. Tell them how many transactions are now confirmed.
- After the user declines: call `reject_batch(batch_id)`. Tell them the staged rows have been removed; the batch row remains for audit.
- **Don't call `sync_ynab` here.** SP2 is statement ingestion; it has nothing to do with YNAB.
- Amounts in `BatchPreview` and the underlying transactions are in **signed integer minor units (cents)**. Convert to dollars in your message text by dividing by 100 with two decimal places.

## When something goes wrong

- The tool returns `{"error": "<code>", "message": "..."}`. Surface the message verbatim.
- `error="template_not_found"` — explain templates and offer to write a starter template (suggest a path, leave content for the user to confirm).
- `error="file_already_ingested"` — the user has imported this file before. Show the prior batch's status (`list_batches(source_id=..., review_status=None)`).
- `error="archive_failed"` — disk-full or permission issue. Don't proceed; flag the underlying I/O message.

## After confirmation succeeds

Suggest one of:
- `summarize_spending(group_by='category')` — see how the new transactions land.
- `query_transactions(account_id='statement:<nick>:account')` — list the just-imported set.
- `/homefinance:explore` — broader analysis skill if they want guided questions.
