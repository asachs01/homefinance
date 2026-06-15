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
├── analysis/           # SP3 analytics (pure, deterministic — no numpy/pandas)
│   ├── categorize.py   # rule engine + idempotent apply pass + suggestion helpers
│   ├── cashflow.py     # inflow/outflow/net per period (transfers excluded)
│   ├── recurring.py    # median-gap cadence detection + next-occurrence forecast
│   └── anomaly.py      # category-month z-score baseline
├── retirement/         # SP4 tax-advantaged overlay (pure, deterministic; no DB, no new deps)
│   ├── data/irs_limits.toml # year-keyed, cited IRS limits + Roth MAGI bands
│   ├── limits.py            # fail-loud loader (unknown year → error, never a guess)
│   ├── inputs.py            # [retirement] config parsing (Pydantic)
│   └── compute.py           # shared-IRA headroom, Roth phase-out, HSA, deadline, opportunities
├── mcp_server/
│   ├── __main__.py     # stdio entry; FastMCP tool registrations
│   └── tools.py        # tool implementations as plain functions (testable)
└── cli.py              # typer + rich CLI (init / sync / status / ynab / accounts / ingest / categorize / retirement)
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

## Categorization & the canonical taxonomy (SP3)

The canonical category vocabulary *is* the set of YNAB category names. `apply_categorization` is idempotent: it derives YNAB rows' categories from their names, fills statement rows from ordered rules, and never clobbers manual assignments (`category_source='manual'`). Analytics group by `canonical_category` for cross-source views. Claude assists only the unmatched long tail at the skill layer — every runtime money path stays deterministic. Cash-flow, recurring detection, and anomaly detection are pure SQL + stdlib arithmetic (no numpy/pandas).

## Retirement overlay (SP4)

SP4 doesn't read the transaction store — it's an overlay fed by a bundled, cited per-year IRS-limits file plus a `[retirement]` config section. It computes deterministic facts: contribution headroom (the IRA limit is one shared Traditional+Roth bucket), Roth MAGI phase-out eligibility, HSA caps, and the contribution deadline. Every output is informational, carries a disclaimer, and never prescribes. Unknown tax years fail loud rather than guess; the data file is the single, citable correction point for new years.

## Tools vs skills

- **Tools** (24 read/analysis tools) are primitives. They live in code and ship with the package.
- **Skills** (`homefinance-setup`, `homefinance-explore`, `homefinance-import-statement`, `homefinance-categorize`, `homefinance-analyze`, `homefinance-retirement`) are workflows. They live in `plugin/skills/` as markdown and can be edited by users without code changes.

## See also

- [SP1 design spec](superpowers/specs/2026-06-10-sp1-foundation-design.md) — the design record.
- [SP1 implementation plan](superpowers/plans/2026-06-10-sp1-foundation.md) — the task-by-task build.
