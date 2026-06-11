# homefinance

Open-source, local-first home financial analysis — distributed as a Claude Code plugin.

**Status:** SP1 (Foundation + YNAB spine) ready for use.

## What it does

- Syncs **YNAB** (read-only) into a local SQLite store.
- Exposes 8 read tools over the store via a stdio MCP server.
- Ships two Claude Code skills (`homefinance-setup`, `homefinance-explore`) for guided setup and analysis.
- Designed so statement ingestion (SP2), spending analytics (SP3), and retirement optimization (SP4) plug in without schema changes.

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/asachs/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Get a YNAB Personal Access Token from
#    https://app.ynab.com/settings/developer → "New Token"
export HOMEFINANCE_YNAB_TOKEN=<your-token>

# 3. First-run setup (interactive)
homefinance init

# 4. Verify
homefinance status
```

After `init`, point Claude Code at the bundled plugin under `plugin/`, then ask: *"Show me my finances at a glance."*

## Data lives at

- Config: `~/.homefinance/config.toml` (or `$XDG_CONFIG_HOME/homefinance/config.toml`)
- Database: `~/.homefinance/db.sqlite3` (or `$XDG_DATA_HOME/homefinance/db.sqlite3`)

**Nothing leaves your machine** except outbound calls to `api.ynab.com`.

## Privacy & posture

- **Read-only** YNAB access — the client class exposes no write methods, ever.
- **No telemetry**, no analytics, no remote logging.
- All amounts stored as signed integer minor units (cents). Floats never enter the store.

## Documentation

- [Architecture](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
- [SP1 design spec](docs/superpowers/specs/2026-06-10-sp1-foundation-design.md)
- [SP1 implementation plan](docs/superpowers/plans/2026-06-10-sp1-foundation.md)

## License

MIT.
