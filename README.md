# homefinance

Open-source, local-first home financial analysis — distributed as a Claude Code plugin.

**Status:** SP1–SP4 complete (YNAB spine, statement ingestion, spending analytics, retirement headroom).

## What it does

- Syncs **YNAB** (read-only) into a local SQLite store.
- Ingests **statement files** (CSV / OFX / QFX / PDF via Docling) into the same canonical store, with a two-phase confirm/reject lifecycle so the parser's output is never trusted without human review.
- **Analyzes** spending: hybrid categorization (rules + Claude-assisted long tail) into a unified taxonomy, cash-flow (income vs outflow, transfers excluded), recurring-charge detection with next-bill forecasts, and category anomaly detection.
- **Retirement headroom**: deterministic Traditional IRA / Roth IRA / HSA contribution limits, remaining headroom, Roth MAGI phase-out eligibility, and contribution deadlines from a bundled, cited, per-year IRS-limits file — informational only, never advice.
- 24 read/analysis MCP tools across YNAB sync, statement ingestion, analytics, and retirement.
- Six Claude Code skills: `homefinance-setup`, `homefinance-explore`, `homefinance-import-statement`, `homefinance-categorize`, `homefinance-analyze`, `homefinance-retirement`.
- The homeFinance program (SP1–SP4) is complete.

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/asachs01/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Lean install** (`pip install -e .`) supports YNAB sync only.
**Full install** (`pip install -e ".[ingest]"`) adds the Docling PDF + OFX/QFX parsers (~500MB of PyTorch + models on first use).

```bash
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
