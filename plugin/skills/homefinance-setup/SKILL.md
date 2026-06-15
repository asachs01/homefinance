---
name: homefinance-setup
description: Use when the user is setting up homefinance for the first time, asks how to install or configure the plugin, mentions needing a YNAB token, or asks why no data appears. Walks the user from zero to a successful first sync.
---

# homefinance Setup

You are guiding a user through the first-run setup of the homefinance plugin.

## What you should know

- homefinance is local-first; nothing leaves the user's machine except outbound calls to api.ynab.com.
- The YNAB token is a Personal Access Token from https://app.ynab.com/settings/developer.
- The token lives in `$HOMEFINANCE_YNAB_TOKEN` (preferred) or `~/.homefinance/config.toml` under `[ynab].token`. Env beats file.
- The database is at `~/.homefinance/db.sqlite3` (or `$XDG_DATA_HOME/homefinance/db.sqlite3`).

## Setup workflow

1. **Confirm install.** Ask the user to run `python -c "import homefinance; print(homefinance.__version__)"`. If it fails, point them at `pip install -e .` in the cloned repo.

2. **Get a YNAB Personal Access Token.** Send them to https://app.ynab.com/settings/developer → "New Token". Recommend they `export HOMEFINANCE_YNAB_TOKEN=...` in their shell rather than write it to a file.

3. **Run `homefinance init`.** Interactive prompts pick budgets and nicknames. After the budget list shows, suggest comma-separated indices (`0` or `0,1`).

4. **Verify the first sync ran.** Call the `get_sync_status` tool. Confirm `last_sync_at` is set and `last_reconciliation` is `ok` or `drift`.

5. **If reconciliation reports `drift`**, that is *normal* on first sync — small balance mismatches happen at the bank-statement boundary. Use `get_account` to look at one account and explain the deltas; do not treat it as an error.

## When something goes wrong

- `401 from YNAB` → the token was rejected. Have the user generate a new PAT and re-export `HOMEFINANCE_YNAB_TOKEN`.
- `No budgets configured` after `init` → re-run `homefinance ynab add-budget --budget-id <id> --nickname <name>` (use the budget IDs from `list_sources` on the YNAB site).
- `Database is locked` → another `homefinance` process is mid-sync; wait and retry.

## Statement-fed accounts (SP2)

For accounts YNAB does not already cover (e.g., a credit card whose data only comes from a downloaded PDF or CSV), register them locally before ingesting any statement file:

1. Tell the user to run, for each non-YNAB account:
   ```
   homefinance accounts add --nickname citi-cc --type credit_card --currency USD
   ```
   Valid types: `checking`, `savings`, `credit_card`, `investment`, `loan`, `cash`, `other`.

2. If the parser they need is **CSV** or **Docling PDF**, that account also needs a per-account template at `~/.homefinance/templates/statement:<nickname>.toml`. Walk them through writing one based on what their bank actually exports. OFX/QFX never need a template.

3. Once an account is registered (and template authored if needed), invoke the `/homefinance:import-statement` skill to walk through ingesting their first file.

## What to do after setup succeeds

Suggest the `homefinance-explore` skill (or `/homefinance:explore`) for a guided first look at the data.
