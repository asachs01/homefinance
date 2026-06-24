# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding (SP1).
- SP1 foundation: canonical SQLite store, YNAB read-only sync engine, 8-tool MCP server, CLI (`init`/`sync`/`status`/`db-path`/`ynab add-budget`/`ynab remove-budget`), plugin manifest and two skills (`homefinance-setup`, `homefinance-explore`), CI on Python 3.11 and 3.12.
- SP2 statement ingestion: CSV / OFX / QFX / Docling-PDF parsers behind a Strategy-pattern registry, per-account TOML templates, two-phase write path (`pending_review` → confirm/reject), 4 new MCP tools (`ingest_statement`, `list_batches`, `confirm_batch`, `reject_batch`), 5 new CLI commands (`accounts add`, `ingest`, `batches`, `batch confirm/reject`), and the `homefinance-import-statement` skill. Lean install (`pip install -e .`) keeps the same dependency footprint; statement support gated to the new `[ingest]` extra. Migration 0002 adds `transactions.status` + `transactions.batch_id` and the `statement_batches` table.
- SP3 analytics: hybrid categorization (deterministic ordered rule engine + Claude-assisted long-tail suggestions promoted into rules) into a canonical "mirror-YNAB" taxonomy; `cash_flow`, `detect_recurring` (with next-bill forecast), and `detect_anomalies`; 7 new MCP tools (incl. `list_payees`) plus `summarize_spending(group_by='canonical_category')`; a `categorize` CLI group; and two skills (`homefinance-categorize`, `homefinance-analyze`). Migration 0003 adds the `category_rules` table and `transactions.canonical_category` / `category_source`. No new third-party dependencies.
- SP4 retirement & tax-advantaged optimization: deterministic Traditional IRA / Roth IRA / HSA contribution headroom, Roth MAGI phase-out eligibility, HSA caps, and contribution deadlines from a bundled, cited, per-year IRS-limits file (2025 + 2026) that fails loud on unknown years. A `[retirement]` config section supplies birth year / filing status / MAGI / coverage / contributions-to-date (with per-call overrides). 3 MCP tools (`retirement_summary`, `contribution_limits`, `roth_eligibility`), a `retirement summary` CLI, and the `homefinance-retirement` skill. Informational only — every output carries a not-financial-advice disclaimer. No database migration; no new third-party dependencies.
- Open-source community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1), `SECURITY.md`, GitHub issue templates (bug/feature) and a pull-request template — all reinforcing the "never commit real financial data" posture.
