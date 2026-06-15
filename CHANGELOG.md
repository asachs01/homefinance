# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding (SP1).
- SP1 foundation: canonical SQLite store, YNAB read-only sync engine, 8-tool MCP server, CLI (`init`/`sync`/`status`/`db-path`/`ynab add-budget`/`ynab remove-budget`), plugin manifest and two skills (`homefinance-setup`, `homefinance-explore`), CI on Python 3.11 and 3.12.
- SP2 statement ingestion: CSV / OFX / QFX / Docling-PDF parsers behind a Strategy-pattern registry, per-account TOML templates, two-phase write path (`pending_review` → confirm/reject), 4 new MCP tools (`ingest_statement`, `list_batches`, `confirm_batch`, `reject_batch`), 5 new CLI commands (`accounts add`, `ingest`, `batches`, `batch confirm/reject`), and the `homefinance-import-statement` skill. Lean install (`pip install -e .`) keeps the same dependency footprint; statement support gated to the new `[ingest]` extra. Migration 0002 adds `transactions.status` + `transactions.batch_id` and the `statement_batches` table.
