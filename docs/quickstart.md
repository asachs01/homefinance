# Quickstart

A 10-minute walkthrough from clone to first analysis.

## 1. Install

Python 3.11+ is required.

```bash
git clone https://github.com/asachs01/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 2. Token

Generate a YNAB Personal Access Token at <https://app.ynab.com/settings/developer>. Export it in your shell — that is the safest place:

```bash
export HOMEFINANCE_YNAB_TOKEN=<token>
```

Putting the token in `~/.homefinance/config.toml` is also supported but is discouraged.

## 3. Initialize

```bash
homefinance init
```

You will be prompted to pick budgets and supply nicknames. Defaults are sensible — just press Return.

To do this non-interactively:

```bash
homefinance init --token "$HOMEFINANCE_YNAB_TOKEN" \
    --budget <budget-id> --nickname personal --no-sync
homefinance sync
```

## 4. Verify

```bash
homefinance status
```

You should see a table with your registered budgets, the last-sync timestamp, the server-knowledge cursor, and the most recent reconciliation status (`ok` or `drift`).

## 5. Use it from Claude Code

Add the plugin under `plugin/` to your Claude Code plugin folder (or symlink it). Restart Claude Code. The 8 tools and 2 skills become available.

Try:

> Show me my finances at a glance.

Claude will call `list_sources` then `list_accounts` and render a small balance table.

## Importing a statement

For accounts YNAB doesn't cover (or for one-off PDF statements), register the account once and then ingest files.

```bash
homefinance accounts add --nickname citi-cc --type credit_card --currency USD
# (For CSV or PDF parsers, also author ~/.homefinance/templates/statement:citi-cc.toml.)
homefinance ingest ~/Downloads/citi-2026-06.pdf --account citi-cc
```

The CLI parses, reconciles balance against the statement's closing total, and shows a preview. Pressing `y` confirms; anything else rejects (deletes the staged rows; keeps the batch row for audit).

For a fully scripted flow, pass `--no-prompt`, then later run `homefinance batch confirm <id>` when you're ready.

## Categorizing & analyzing

YNAB transactions arrive categorized; statement-imported ones don't. Unify them once, then analyze.

```bash
# Add a rule, then apply (re-runnable any time)
homefinance categorize rules add --field payee --pattern "TRADER JOE" --category Groceries
homefinance categorize apply
```

From Claude Code, the `/homefinance:categorize` skill drives a faster loop: it surfaces uncategorized payees and proposes categories (constrained to your YNAB names) for you to confirm or promote into rules.

Then ask analytical questions via `/homefinance:analyze`:

> How did my cash flow look over the last 6 months?
> What subscriptions am I paying, and what's due next?
> Any unusual spending last month?

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

## Day-to-day

- `homefinance sync` — re-sync from YNAB (cron-able)
- `homefinance ynab add-budget --budget-id <id> --nickname <name>` — register more budgets
- `homefinance db-path` — print where the DB lives

## Reset

To reset entirely:

```bash
rm -rf ~/.homefinance/
```

(All data is local; this is the only place it lives.)
