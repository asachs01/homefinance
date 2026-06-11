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
