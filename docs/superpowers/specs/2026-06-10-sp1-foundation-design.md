# SP1 — Foundation + YNAB Spine — Design Spec

| | |
|---|---|
| **Status** | Draft (awaiting user review) |
| **Sub-project** | SP1 of the homeFinance program |
| **Date** | 2026-06-10 |
| **Successor** | Implementation plan, to be created via the `superpowers:writing-plans` skill on approval |

---

## 1. Context

`homeFinance` is an open-source, local-first home financial analysis and planning toolset, distributed as a Claude Code plugin (skills + an MCP server). It enables a single household to analyze bank, credit-card, and bill data; integrate with YNAB; and (in later sub-projects) optimize retirement contributions across Traditional IRA, Roth IRA, and HSA accounts.

This document specifies **SP1 — Foundation + YNAB Spine**, the first of four sub-projects. SP1 establishes the canonical local data store, the architectural seam that subsequent data sources plug into, the YNAB integration, the MCP server skeleton, and the plugin scaffold.

### 1.1 Why SP1 first

Foundation sub-projects justify themselves by passing one test: *does the second data source plug in with zero schema change?* SP1 is designed so that SP2 (statement & bill ingestion via Docling) becomes a new `AccountSource` implementation rather than a schema rewrite.

---

## 2. Program decomposition

The `homeFinance` program is decomposed into four sub-projects. Each gets its own spec → plan → build cycle.

| # | Sub-project | Delivers | Depends on |
|---|---|---|---|
| **SP1** | **Foundation + YNAB spine** *(this spec)* | Canonical store, account registry with provenance, YNAB sync, MCP server skeleton, plugin scaffold | — |
| SP2 | Statement & bill ingestion | Tiered pipeline: OFX/QFX/CSV (exact), PDF/bills via Docling + Claude + reconciliation | SP1 |
| SP3 | Spending & cash-flow analysis | Trends, categorization rules, anomaly detection, bill forecasting | SP1 (richer with SP2) |
| SP4 | Retirement & tax-advantaged optimization | Traditional IRA / Roth IRA / HSA contribution-limit and tax logic | Lighter coupling — needs balances + rules; better with SP3 cash-flow |

The plugin is **not a phase** — it is the wrapper that grows across all four sub-projects.

---

## 3. Foundational constraints

| | Constraint | Source / Reasoning |
|---|---|---|
| **C-1** | Open-source, local-first, self-hosted | Each install serves one household; no hosted backend; no multi-tenancy |
| **C-2** | Data never leaves the machine | Every external integration is explicit and opt-in |
| **C-3** | No personal data or secrets in the repo | Tokens, account names, the database file itself are gitignored |
| **C-4** | YNAB is the spine; statements fill the accounts YNAB doesn't cover | Provenance is *per account*; one account = one source |
| **C-5** | Read-only YNAB access | Aligned with the established financial-MCP posture (read + safe operations, no money movement). Structurally enforced — see §7.1 |
| **C-6** | Single coherent language — Python 3.11+ | Docling (SP2) is Python-only; financial ecosystem is Python; MCP Python SDK is mature |
| **C-7** | License: MIT | Conventional for utility tooling; compatible with Docling, MarkItDown, and upstream deps |

---

## 4. Architecture overview

### 4.1 Three invariants enforced by construction

1. **Provenance per account** — every account belongs to exactly one `source` (FK). Double-counting across YNAB and statements is impossible at the table level, not by convention.
2. **Idempotent upserts** — every imported row has a `(source_id, external_id)` UNIQUE key. Re-running sync N times produces identical state.
3. **Money is integer, not float** — all amounts stored as signed minor units (cents). YNAB's milliunits are converted at the mapping boundary; **floats never enter the store**.

### 4.2 The `AccountSource` seam

`src/homefinance/sources/base.py` defines a Python `Protocol` (`AccountSource`) with a small set of operations:

```python
class AccountSource(Protocol):
    source_id: str                                # e.g., "ynab:<budget_id>"
    kind: Literal["ynab", "statement"]

    def list_remote_accounts(self) -> list[RemoteAccount]: ...
    def list_remote_categories(self) -> list[RemoteCategory]: ...
    def pull_delta(self, cursor: int | None) -> Delta: ...
    def reconcile(self, account_id: str) -> ReconciliationResult: ...
```

The YNAB adapter implements it for SP1; the statement adapter implements it for SP2. All sources funnel through the same upsert path and the same reconciliation discipline. **This seam is the load-bearing element of the entire program.**

### 4.3 Read paths

| Read surface | Purpose |
|---|---|
| Python library (`homefinance` package) | Internal — used by CLI, MCP server, and tests |
| CLI (`homefinance` command) | Manual operation: `init`, `sync`, `status`, `db-path`, etc. |
| MCP server (stdio) | Agent-facing — Claude calls 8 read tools (+ `sync_ynab`) over the canonical store |

The MCP server runs as a stdio subprocess spawned by Claude Code. **It has no network surface.** The only outbound network call from the entire system is the YNAB API call made by `run_sync()`.

---

## 5. Repository & plugin structure

```
homefinance/                            # repo root
├── README.md                           # what it is + quickstart
├── LICENSE                             # MIT
├── CHANGELOG.md                        # keepachangelog format
├── pyproject.toml                      # deps + entry points (CLI + MCP server)
├── .gitignore                          # excludes user data and secrets
├── .env.example                        # documents required env vars; no real values
│
├── plugin/                             # Claude Code plugin — user-facing shell
│   ├── plugin.json                     # plugin metadata + skill + MCP wiring
│   ├── skills/
│   │   ├── homefinance-setup/SKILL.md  # onboarding skill (token, init, first sync)
│   │   └── homefinance-explore/SKILL.md# first analysis-starter
│   └── .mcp.json                       # registers `python -m homefinance.mcp_server`
│
├── src/homefinance/                    # the actual engine
│   ├── config.py                       # config loading; env wins over file
│   ├── db/
│   │   ├── schema.sql                  # canonical schema
│   │   ├── migrations/                 # versioned migrations (yoyo-migrations)
│   │   └── store.py                    # repository over sqlite3
│   ├── sources/
│   │   ├── base.py                     # AccountSource protocol — the SP2 seam
│   │   └── ynab/
│   │       ├── client.py               # read-only httpx YNAB client
│   │       ├── sync.py                 # delta sync + atomic upsert
│   │       └── mapping.py              # YNAB → canonical (single source of truth)
│   ├── analysis/                       # SP3 fills this
│   ├── mcp_server/
│   │   ├── __main__.py                 # stdio entry point
│   │   └── tools.py                    # read-only tool registrations + sync_ynab
│   └── cli.py                          # `homefinance init / sync / status / db-path`
│
├── tests/
│   ├── fixtures/ynab/                  # recorded, sanitized YNAB API responses
│   ├── test_db.py
│   ├── test_ynab_sync.py
│   ├── test_mcp_tools.py
│   └── test_cli.py
│
├── scripts/
│   └── record_fixtures.py              # one-time PAT-based fixture capture
│
└── docs/
    ├── quickstart.md
    ├── architecture.md
    └── superpowers/specs/
        └── 2026-06-10-sp1-foundation-design.md
```

### 5.1 Design decisions baked into the layout

- **`src/` layout** — modern Python practice; prevents accidental imports from CWD during tests.
- **Plugin shell separate from engine.** `plugin/` is the Claude Code surface (skills + MCP wiring); `src/homefinance/` is the importable engine.
- **CLI + MCP share the same library.** `homefinance sync` (CLI) and the MCP `sync_ynab` tool both call `homefinance.sources.ynab.sync.run_sync()`. One implementation, two front doors.
- **No user data, ever, in the repo.** Database file, config file, and tokens live outside the repo (see §5.2).
- **Migrations from day one.** SP2–SP4 will add tables/columns; self-hosters need clean upgrades. `yoyo-migrations` (pure SQL, no ORM) over Alembic.

### 5.2 Configuration and secrets

| Concern | Resolution |
|---|---|
| YNAB Personal Access Token | `HOMEFINANCE_YNAB_TOKEN` env var (preferred) **or** `[ynab].token` in `~/.homefinance/config.toml`. **Env beats file.** Never logged. Loaded as `pydantic.SecretStr`. |
| Config path | Default `~/.homefinance/config.toml`. Honors `XDG_CONFIG_HOME` when set. Override with `HOMEFINANCE_CONFIG`. |
| Database path | Default `~/.homefinance/db.sqlite3`. Honors `XDG_DATA_HOME` when set. Override with `HOMEFINANCE_DB`. |
| Validation | Pydantic v2 settings at startup. Errors are friendly with file:line and remediation steps. |
| `.env.example` | Documents env vars with placeholders. No real values. |

### 5.3 Multi-budget configuration

The `[ynab]` config supports an array of budgets sharing one PAT:

```toml
[ynab]
# token may live here OR (preferred) in HOMEFINANCE_YNAB_TOKEN
# token = "..."

[[ynab.budgets]]
budget_id = "abc-123"
nickname  = "personal"

[[ynab.budgets]]
budget_id = "def-456"
nickname  = "family"
```

- `homefinance init` walks the user through PAT entry, lists budgets via `GET /budgets`, and writes the chosen set.
- `homefinance ynab add-budget` and `remove-budget` adjust later.
- When two budgets contain an account with the same display name, MCP tool output prepends the nickname for disambiguation.

---

## 6. Data model & schema

### 6.1 Money discipline

**All monetary values are stored as signed integers in minor units (cents).** Floats are forbidden inside the store. YNAB's API uses milliunits (1000ths); conversion happens in exactly one place — `src/homefinance/sources/ynab/mapping.py` — at the boundary between the wire format and the canonical model. Conversion:

```
canonical_minor = ynab_milliunits // 10
```

Sign convention: **negative = outflow, positive = inflow.**

### 6.2 Schema (DDL sketch)

```sql
-- Sources: registry of configured data sources (one per YNAB budget; later, per statement-fed account)
CREATE TABLE sources (
    id          TEXT PRIMARY KEY,           -- "ynab:<budget_id>"
    kind        TEXT NOT NULL,              -- "ynab" | "statement"
    nickname    TEXT,                       -- user-supplied display label
    config      TEXT,                       -- JSON snapshot of source-specific config
    created_at  TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE TABLE accounts (
    id                       TEXT PRIMARY KEY,         -- "ynab:<budget>:<account_id>"
    source_id                TEXT NOT NULL REFERENCES sources(id),
    external_id              TEXT NOT NULL,            -- e.g., YNAB account UUID
    name                     TEXT NOT NULL,
    type                     TEXT NOT NULL,            -- canonical: checking | savings | credit_card | investment | loan | cash | other
    on_budget                INTEGER NOT NULL DEFAULT 1,
    closed                   INTEGER NOT NULL DEFAULT 0,
    currency                 TEXT NOT NULL DEFAULT 'USD',
    cleared_balance_minor    INTEGER,                  -- as reported by source
    uncleared_balance_minor  INTEGER,                  -- as reported by source
    balance_as_of            TEXT,                     -- ISO 8601 UTC
    last_synced_at           TEXT,
    UNIQUE (source_id, external_id)
);

CREATE TABLE categories (
    id           TEXT PRIMARY KEY,                     -- "ynab:<budget>:<category_id>"
    source_id    TEXT NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,
    name         TEXT NOT NULL,
    group_name   TEXT,                                 -- YNAB's category group
    hidden       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE payees (
    id                  TEXT PRIMARY KEY,              -- "ynab:<budget>:<payee_id>"
    source_id           TEXT NOT NULL REFERENCES sources(id),
    external_id         TEXT NOT NULL,
    name                TEXT NOT NULL,
    transfer_account_id TEXT REFERENCES accounts(id),  -- YNAB transfer payees reference an account
    deleted             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source_id, external_id)
);

CREATE TABLE transactions (
    id                     TEXT PRIMARY KEY,           -- "ynab:<budget>:<txn_id>"
    source_id              TEXT NOT NULL REFERENCES sources(id),
    external_id            TEXT NOT NULL,
    account_id             TEXT NOT NULL REFERENCES accounts(id),
    date                   TEXT NOT NULL,              -- ISO 8601 date (YYYY-MM-DD)
    amount_minor           INTEGER NOT NULL,           -- signed cents (negative = outflow)
    currency               TEXT NOT NULL,              -- denormalized from account
    payee                  TEXT,                       -- denormalized name (display)
    payee_id               TEXT REFERENCES payees(id),
    memo                   TEXT,
    category_id            TEXT REFERENCES categories(id),
    cleared                TEXT,                       -- "cleared" | "uncleared" | "reconciled"
    approved               INTEGER NOT NULL DEFAULT 1,
    flag_color             TEXT,
    import_id              TEXT,                       -- YNAB's bank-import dedup key
    transfer_account_id    TEXT REFERENCES accounts(id),
    parent_id              TEXT REFERENCES transactions(id),  -- split parent (NULL for non-splits and split parents themselves)
    deleted                INTEGER NOT NULL DEFAULT 0,
    raw                    TEXT,                       -- JSON: original payload, for debug/audit
    synced_at              TEXT NOT NULL,
    UNIQUE (source_id, external_id)
);

CREATE TABLE sync_state (
    source_id         TEXT PRIMARY KEY REFERENCES sources(id),
    last_sync_at      TEXT NOT NULL,
    server_knowledge  INTEGER,                         -- YNAB's delta cursor
    last_error        TEXT,
    last_error_at     TEXT
);

CREATE TABLE sync_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         TEXT NOT NULL REFERENCES sources(id),
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,                   -- "success" | "failed" | "partial"
    txns_inserted     INTEGER NOT NULL DEFAULT 0,
    txns_updated      INTEGER NOT NULL DEFAULT 0,
    txns_deleted      INTEGER NOT NULL DEFAULT 0,
    accounts_touched  INTEGER NOT NULL DEFAULT 0,
    reconciliation    TEXT NOT NULL,                   -- "ok" | "drift" | "n/a"
    drift_report      TEXT,                            -- JSON: per-account deltas when reconciliation='drift'
    error             TEXT
);

-- Indexes
CREATE INDEX idx_transactions_account_date ON transactions(account_id, date);
CREATE INDEX idx_transactions_date         ON transactions(date);
CREATE INDEX idx_transactions_category     ON transactions(category_id);
CREATE INDEX idx_transactions_payee        ON transactions(payee);
CREATE INDEX idx_transactions_parent       ON transactions(parent_id);
CREATE INDEX idx_accounts_source           ON accounts(source_id);
CREATE INDEX idx_sync_runs_source_time     ON sync_runs(source_id, started_at);
```

`schema_version` is managed automatically by `yoyo-migrations`.

### 6.3 Split transactions

YNAB splits are modeled as **parent + children rows linked by `parent_id`**:

- The parent row carries the aggregate amount and (typically) no category.
- Each child row carries one category and a partial amount; children sum to the parent's amount.
- Both parent and children share a `(source_id, external_id)` family in YNAB's data; we preserve the parent's transaction ID and assign deterministic child IDs (`<parent_id>:sub:<n>`).

Analytical queries follow exactly one of two disciplines — never both, or amounts double-count:

| Discipline | Use for | SQL filter |
|---|---|---|
| **Parent-only** | Totals (cash flow, account-level sums) | `WHERE parent_id IS NULL` |
| **Children-only for split parents** | Category breakdowns | exclude split *parents* (where children exist); include all non-split rows |

The `summarize_spending` MCP tool encodes this discipline in code (see §8.2).

### 6.4 Balance reconciliation

The store retains **both** the source-reported balance (on the account row) and is capable of computing balance from transactions on demand. After every sync, the engine compares them per account:

- Match → `sync_runs.reconciliation = 'ok'`.
- Mismatch → `sync_runs.reconciliation = 'drift'`, with a JSON `drift_report` listing per-account deltas (account_id, computed_minor, reported_minor, delta_minor).

**Drift never fails a sync** (see §9.3). It is surfaced via `get_sync_status` so the user can investigate.

### 6.5 Category mapping across sources

Per-source for SP1. YNAB's categories are owned by their YNAB source. A canonical category-mapping layer is *not* designed now and is explicitly deferred to SP3 (see §10, OS-8). The schema does not foreclose adding a `canonical_categories` table later.

### 6.6 ID strategy

Deterministic IDs (`ynab:<budget_id>:<entity_id>`) are used as primary keys. Rationale: grep-friendly during debugging; stable across re-syncs; the `(source_id, external_id)` UNIQUE constraint also functions as a lookup index. Random UUIDs are explicitly rejected for this reason.

---

## 7. YNAB sync engine

### 7.1 Read-only as a structural property

`YNABClient` exposes **only GET methods** — `get_budgets`, `get_accounts(budget_id, cursor)`, `get_categories(budget_id, cursor)`, `get_transactions(budget_id, cursor)`, `get_payees(budget_id, cursor)`. **No POST / PUT / DELETE methods exist on the class.** Accidental writes are physically impossible, not merely conventional.

### 7.2 Delta sync via `server_knowledge`

YNAB's API supports delta sync for accounts, categories, transactions, and payees:

- **First sync** (`sync_state.server_knowledge IS NULL`): full pull of all 4 entities for each registered budget.
- **Subsequent syncs**: `GET ...?last_knowledge_of_server=<cursor>` returns only changes. Cursor persisted to `sync_state.server_knowledge` per source after a successful sync.

### 7.3 Sync flow

A single function — `run_sync(source_id)` in `src/homefinance/sources/ynab/sync.py` — drives sync. Both the CLI and the MCP tool call it.

1. Load config → resolve token (env wins) and `budget_id`.
2. **Validate token** with `GET /user`. Fail-fast on 401 with remediation message.
3. Read `sync_state.server_knowledge` for the source (NULL ⇒ first sync).
4. Pull accounts, categories, transactions, and payees with `?last_knowledge_of_server=<cursor>`.
5. **Stage all upserts in memory**, then apply in **one SQLite transaction** alongside `sync_state.server_knowledge` and the `sync_runs` row. Atomic by construction.
6. Reconcile per account (§6.4). Record outcome.
7. COMMIT.

### 7.4 Upsert pattern

```sql
INSERT INTO transactions (id, source_id, external_id, account_id, date, amount_minor, ...)
VALUES (?, ?, ?, ?, ?, ?, ...)
ON CONFLICT (source_id, external_id) DO UPDATE SET
    date         = excluded.date,
    amount_minor = excluded.amount_minor,
    payee        = excluded.payee,
    payee_id     = excluded.payee_id,
    memo         = excluded.memo,
    category_id  = excluded.category_id,
    cleared      = excluded.cleared,
    approved     = excluded.approved,
    flag_color   = excluded.flag_color,
    deleted      = excluded.deleted,
    raw          = excluded.raw,
    synced_at    = excluded.synced_at;
```

The same pattern applies to `accounts`, `categories`, and `payees`. Soft-delete: when YNAB returns `deleted: true` in a delta, we set `deleted = 1` rather than removing the row. The audit trail is preserved and the model matches YNAB's.

### 7.5 What we sync (and don't)

| Sync | Defer | Never |
|---|---|---|
| Budgets list (one-time, on `init`) | Months / monthly budget allocations | Any write to YNAB |
| Accounts (+ balances) | Scheduled (future-dated) transactions | |
| Categories (with groups) | | |
| Transactions (including splits) | | |
| Payees | | |

### 7.6 Rate limit & retry posture

YNAB allows 200 requests/hour per token. A full sync is ~4 requests/budget; a delta is ~4 requests/budget. We are nowhere near the limit. Every API call is wrapped with `tenacity`-style exponential backoff:

- Retries on `429`, `5xx`, and transient network errors.
- 3 retries, jittered.
- Honors `Retry-After` header when present.

### 7.7 Trigger model

| Trigger | Mechanism | Notes |
|---|---|---|
| CLI | `homefinance sync` (all sources) or `homefinance sync --source <id>` | Primary entry; cron-able by the user |
| MCP tool | `sync_ynab(source_id?)` | Lets Claude sync mid-conversation; still read-only outside the local store |

There is **no background daemon or scheduler.** Users who want automation cron the CLI.

---

## 8. MCP server surface

### 8.1 Design philosophy

Tools are **primitives** (data access). Skills are **workflows** (markdown recipes that orchestrate tools + Claude's reasoning). This separation keeps the tool surface small, stable, and composable while allowing new analyses to be added as user-editable skill files without shipping a release.

Exception to "no convenience tools": aggregation primitives that encode a *correctness discipline* (e.g., the split-handling rule) are worth shipping as server-side tools, because code-enforced correctness beats prompt-enforced correctness.

### 8.2 The 8 SP1 tools

| Tool | Signature (simplified) | Purpose |
|---|---|---|
| `list_sources` | `() -> Source[]` | Registered budgets + last-sync summary |
| `list_accounts` | `(source_id?: str, include_closed?: bool=False) -> Account[]` | Accounts across or within budgets; budget nickname for disambiguation |
| `get_account` | `(account_id: str) -> AccountDetail` | Single account + latest reconciliation status |
| `list_categories` | `(source_id?: str, include_hidden?: bool=False) -> Category[]` | Categories per source |
| `query_transactions` | `(filters: TxFilters) -> Transaction[]` | Workhorse. Filters: account/source/date/category/payee/amount/cleared/include_deleted/limit/offset. **Excludes split parents by default** (`parent_id IS NULL`); set `include_splits=True` to include children. |
| `summarize_spending` | `(filters: TxFilters, group_by: 'category'\|'payee'\|'month'\|'account'\|'day_of_week') -> Bucket[]` | Server-side aggregation that automatically applies the correct split-handling rule per `group_by` (see §6.3). |
| `get_sync_status` | `() -> SyncStatus` | Last-sync per source + drift summary |
| `sync_ynab` | `(source_id?: str) -> SyncRunRow` | Triggers `run_sync()`. Defaults to all YNAB sources. Returns counts + reconciliation outcome. |

Tool naming convention: **`verb_noun`** (e.g., `list_accounts`, `query_transactions`) for stronger natural-language affinity.

`payees` are *stored* in SP1 but **no `list_payees` tool ships in SP1** — payee queries go through `query_transactions(payee_contains=...)` and `summarize_spending(group_by='payee')`. A dedicated `list_payees` tool is parked for SP3 (see §11, OQ-1).

### 8.3 Skills shipped with SP1

| Skill | Purpose | Triggered by |
|---|---|---|
| `homefinance-setup` | Onboarding — PAT entry, `init`, first sync, verification | `/homefinance:setup` or mentioning the plugin first time |
| `homefinance-explore` | Analysis-starter — exercises the tool surface with canonical questions ("show finances at a glance"; "what did I spend on dining last month"; "how have balances trended") | `/homefinance:explore` |

Both are `SKILL.md` files under `plugin/skills/`. Together they constitute the user's first-hour-of-value. SP3 will add deeper analysis skills; SP4 will add retirement skills.

---

## 9. Error handling, resilience, and testing

### 9.1 The atomicity guarantee

The entire sync — every upsert, the `server_knowledge` cursor update, and the `sync_runs` row — runs inside **one SQLite `BEGIN/COMMIT`**. Either the whole sync moves forward or nothing does, and the next run retries from the same cursor. This eliminates partial-recovery logic, distributed-transaction reasoning, and "what if the process dies mid-sync" branches. SQLite's atomicity buys all of it for free.

### 9.2 Failure model

| Class | Behavior | User sees |
|---|---|---|
| Config / pre-flight (missing token, bad TOML, unwritable DB) | Fail before any API call | Friendly message with file path + remediation |
| 401 from YNAB | Fail fast | "YNAB token rejected. Generate a new PAT at app.ynab.com/settings/developer and update `$HOMEFINANCE_YNAB_TOKEN` or `~/.homefinance/config.toml`." |
| 403 / wrong budget | Fail fast | List budgets the token can see |
| Network / 5xx | `tenacity` exponential backoff (3 retries, jittered) | Logged retries; final failure surfaces underlying cause |
| 429 (rate limit) | Honor `Retry-After`; else backoff | Transparent to caller |
| Mapping / validation error on a single row | Log raw payload (redacted), **skip the row**, mark `sync_runs.status = 'partial'` | Sync completes; partial count and "review" message |
| Reconciliation drift | **Never fails the sync.** Logged; `sync_runs.reconciliation = 'drift'` with per-account deltas in `drift_report` | Surfaced via the next `get_sync_status` |
| Atomic-sync failure (SQLite IO / constraint) | Transaction rolls back; cursor unchanged | Next sync retries from same state |

### 9.3 Drift policy

**Warn, do not fail.** Bank-side small drifts are real-world; failing a sync over a 3¢ mismatch is hostile UX. Drift surfaces via `sync_runs.reconciliation = 'drift'` and the next `get_sync_status` call. The user decides whether to investigate.

### 9.4 Testing strategy

Three layers; **no real YNAB in CI**.

| Layer | Coverage | Speed |
|---|---|---|
| Unit | `mapping.py` (milliunits → minor units; signed math; YNAB payload → canonical row), split-handling math, query-discipline rules, money edge cases | Fast, no I/O |
| Integration | In-process SQLite + `FakeYNABClient` (conforms to same `Protocol` as the real client, returns recorded fixtures). Scenarios: full first sync; delta sync; idempotency (re-run = no-op); soft-delete propagation; split-transaction sum invariant; drift detection; auth-error path; partial sync | Sub-second per test |
| End-to-end | Spawn MCP server over stdio + send tool calls; `homefinance sync` CLI as subprocess; both pointed at the fake | Slower but few |

### 9.5 Fixture capture

`scripts/record_fixtures.py` is a one-time PAT-driven script that hits YNAB and writes sanitized JSON to `tests/fixtures/ynab/`. Sanitization replaces real account names, payees, IDs, and amounts with deterministic test data. The author runs it once on real data to bootstrap; future contributors never need a YNAB token to run tests.

### 9.6 CI

Standalone GitHub Actions workflow (not the WYRE fleet's reusable workflow — this is a personal open-source repo, kept independent for external-contributor clarity). Steps:

- Python matrix: **3.11, 3.12** (and 3.13 when released and stable).
- `ruff check` + `ruff format --check`.
- `mypy src/` (strict mode for new code).
- `pytest --cov --cov-fail-under=80`.
- Build `sdist` and `wheel`.

Release-on-tag is deferred until after SP1 stabilizes.

### 9.7 Logging

Default: **friendly text** at INFO level. `--log-format json` is available for power users / scripting.

PII never appears at default level:

- Excluded: account names, payee names, memo text, amounts.
- Included: source IDs, counts, statuses, durations, reconciliation outcomes.

DEBUG level may include redacted samples (e.g., first 50 chars of a memo with PII placeholders).

---

## 10. Out of scope

| | What | Where |
|---|---|---|
| OS-1 | Statement and bill ingestion | SP2 |
| OS-2 | Docling-based PDF/image parsing | SP2 |
| OS-3 | Categorization rules / fuzzy matching | SP3 |
| OS-4 | Spending analytics beyond `summarize_spending` | SP3 |
| OS-5 | Retirement, IRA, Roth, HSA logic | SP4 |
| OS-6 | YNAB write operations | Never (read-only posture) |
| OS-7 | Background daemon / scheduler | Never (cron the CLI if needed) |
| OS-8 | Canonical category unification across sources | SP3 |
| OS-9 | Multi-token / multi-user support | Never (one household per install) |
| OS-10 | Mobile / web UI | Never within SP1; CLI + Claude Code are the surfaces |

---

## 11. Open questions / parked decisions

| | Question | When to revisit |
|---|---|---|
| OQ-1 | Whether `list_payees` warrants its own MCP tool | SP3, when categorization rules need payee enumeration |
| OQ-2 | Canonical category mapping across sources | SP3 |
| OQ-3 | PyPI publish vs git-install-only | After SP1 stabilizes |
| OQ-4 | Plugin distribution channel (standalone vs joining a marketplace) | After SP1 stabilizes |

---

## 12. Next steps

1. User reviews this spec.
2. On approval, invoke `superpowers:writing-plans` to produce the implementation plan.
3. Implementation proceeds per the plan with TDD and incremental commits.
