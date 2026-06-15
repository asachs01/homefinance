# Architecture

A 5-minute orientation for contributors.

## Layout

```
src/homefinance/
├── config.py           # TOML + env loader; XDG-aware paths; SecretStr token
├── db/
│   ├── schema.sql      # canonical schema (also yoyo's first migration)
│   ├── migrations/     # versioned SQL migrations
│   ├── migrate.py      # yoyo runner
│   └── store.py        # Store: PRAGMAs + atomic-transaction context + Row reads
├── sources/
│   ├── base.py         # AccountSource Protocol + RemoteX dataclasses ← the seam (unchanged by SP2)
│   ├── ynab/           # SP1 adapter
│   │   ├── models.py       # Pydantic models for the YNAB API subset we consume
│   │   ├── client.py       # read-only HTTP client (httpx + tenacity)
│   │   ├── fake_client.py  # JSON-fixture-backed test double
│   │   ├── ids.py          # deterministic ID helpers (ynab:<budget>:<external>)
│   │   ├── mapping.py      # YNAB → canonical (pure functions; money conversion)
│   │   ├── source.py       # YNABAccountSource — implements AccountSource
│   │   └── sync.py         # run_sync — generic orchestrator over AccountSource
│   └── statement/      # SP2 adapter
│       ├── source.py       # StatementAccountSource
│       ├── ingest.py       # ingest_file orchestrator + confirm/reject
│       ├── archive.py      # source-file archiving
│       ├── templates.py    # per-account TOML template loader
│       └── parsers/        # Strategy registry; lazy-imported parser impls
├── mcp_server/
│   ├── __main__.py     # stdio entry; FastMCP tool registrations
│   └── tools.py        # tool implementations as plain functions (testable)
└── cli.py              # typer + rich CLI (init / sync / status / ynab subcmds)
```

## Three invariants

The design enforces these *by construction*, not by convention.

1. **Provenance per account.** Every account has a foreign key to `sources`. Double-counting across YNAB and (future) statement sources is impossible.

2. **Idempotent upserts.** Every imported row carries `(source_id, external_id)` UNIQUE. Re-running sync produces identical state.

3. **Money is integer, not float.** All amounts are signed minor units (cents). `to_minor_units` is the only converter; it raises on sub-cent input.

## The AccountSource seam

`sources/base.py` defines a `Protocol` with `validate()` and `pull(cursor)`. YNAB implements it; SP2's statement adapter will implement it; the generic `run_sync` orchestrator consumes only the protocol. Adding a new source is "implement the protocol" — not "rewire the store."

## Atomic sync

`run_sync` stages all upserts in memory, then applies them inside a single SQLite `BEGIN/COMMIT` together with the new `server_knowledge` cursor and the `sync_runs` row. Either the whole sync moves forward or nothing does; the next run retries from the same cursor.

## Two-phase write path (SP2)

Statement parses don't go straight into the canonical store. Pipeline:

1. `ingest_file` parses + reconciles + stages rows with `status='pending_review'` and `batch_id=<batch>`.
2. The user reviews via the `homefinance-import-statement` skill or the `homefinance ingest` CLI prompt.
3. `confirm_batch` atomically flips the rows to `status='confirmed'`. `reject_batch` deletes them; the `statement_batches` row stays for audit.

`summarize_spending` always filters `status='confirmed'`. `query_transactions` excludes pending rows by default; opt in with `include_pending=True`.

## Tools vs skills

- **Tools** (8 read tools + `sync_ynab`) are primitives. They live in code and ship with the package.
- **Skills** (`homefinance-setup`, `homefinance-explore`) are workflows. They live in `plugin/skills/` as markdown and can be edited by users without code changes.

## See also

- [SP1 design spec](superpowers/specs/2026-06-10-sp1-foundation-design.md) — the design record.
- [SP1 implementation plan](superpowers/plans/2026-06-10-sp1-foundation.md) — the task-by-task build.
