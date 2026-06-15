# SP2 — Statement & Bill Ingestion — Design Spec

| | |
|---|---|
| **Status** | Draft (awaiting user review) |
| **Sub-project** | SP2 of the homeFinance program |
| **Date** | 2026-06-12 |
| **Depends on** | SP1 (`docs/superpowers/specs/2026-06-10-sp1-foundation-design.md`) — shipped on `main` |
| **Successor** | Implementation plan via `superpowers:writing-plans` on approval |

---

## 1. Context

SP1 shipped the foundation + YNAB sync spine. SP2 adds the second data source contemplated in SP1's program map: **statement & bill ingestion** — reading non-YNAB-tracked accounts from local statement files (CSV / OFX / QFX / PDF) into the same canonical store.

This sub-project is the first real test of SP1's `AccountSource` seam: SP2 ships an entirely new adapter without changing the schema's shape, the integer-money discipline, the atomic-transaction guarantee, or the read tools' contracts.

### 1.1 Why now

User-confirmed practical context (Q1, refined): **PDFs are the lingua franca across the user's non-YNAB accounts.** That makes Docling-based PDF ingestion the critical path of SP2, not an optional second tier as initially framed in SP1's spec. Structured formats (CSV/OFX/QFX) ship alongside as cheap secondary parsers wherever an account also offers exact exports — they are simpler and stronger than PDF parsing whenever they're available.

### 1.2 Deliberate pivot from SP1's original framing

SP1 § 2 described SP2 as "PDF/bills via Docling + Claude + reconciliation." **SP2 deliberately removes Claude from the parsing path.** Reason: any non-determinism in money extraction silently corrupts the store, which violates SP1's core money-safety discipline (§ 4.1). Docling produces structured cells; a per-account *template* maps cells to canonical fields deterministically. Claude may help users *author* templates as out-of-band tooling, but never extracts amounts at runtime. This is a real refinement of SP1's program decomposition and is the most consequential design call in SP2.

---

## 2. Program position

| # | Sub-project | Status |
|---|---|---|
| SP1 | Foundation + YNAB spine | **Shipped on `main`** |
| **SP2** | **Statement & bill ingestion** *(this spec)* | Brainstorm complete; spec under review |
| SP3 | Spending & cash-flow analysis | Not started |
| SP4 | Retirement & tax-advantaged optimization | Not started |

---

## 3. Foundational constraints (delta from SP1)

Every SP1 constraint (C-1 through C-7) carries over unchanged. SP2 adds:

| | Constraint | Reasoning |
|---|---|---|
| **C-8** | **No LLM in the money path** | Non-determinism in money extraction silently corrupts the store. Docling extracts structured cells; templates map cells deterministically. Claude is allowed in out-of-band template-authoring tooling but never at ingest time. |
| **C-9** | **Every batch requires explicit human confirmation** | Reconciliation success is a *signal* that confirmation is low-risk; not a license to skip it. The store never silently accepts batch-imported money. |
| **C-10** | **Lean install stays lean** | `pip install homefinance` (without `[ingest]`) must not transitively import `docling` or `torch`. Enforced by a subprocess-based test (see § 10.5). |

---

## 4. Architecture overview

### 4.1 Three invariants inherited + one new

The three invariants from SP1 § 4.1 (provenance per account, idempotent upserts, integer money) carry over unchanged. SP2 adds:

> **Invariant 4 — No money lands in canonical store without explicit confirmation.**
> Statement-ingested rows enter the store with `status='pending_review'` and `batch_id=<batch>`. They become analytically visible only after a user issues `confirm_batch(batch_id)`. `summarize_spending` excludes pending rows unconditionally; `query_transactions` excludes them by default.

### 4.2 The parser registry (Strategy pattern)

`sources/statement/parsers/` holds N implementations of a `StatementParser` Protocol. `ingest_file(path, account_id)` sniffs the file (extension first, magic-byte fallback) and dispatches to the first parser that claims it.

| Parser | Format | Library |
|---|---|---|
| `CSVParser` | `.csv` | stdlib `csv` (no extra deps) |
| `OFXParser` | `.ofx` | `ofxtools` (in `[ingest]` extra) |
| `QFXParser` | `.qfx` | `ofxtools` (QFX is a Quicken OFX flavor) |
| `DoclingPDFParser` | `.pdf` (and `.png`/`.jpg` later) | `docling` (in `[ingest]` extra) |

Per-account *templates* are an optional dict any parser may consult — e.g., a CSV column mapping for `citi-cc`, or a Docling layout template for `wells-checking`. Templates live in `~/.homefinance/templates/<source_id>.toml`. SP2 ships **no bank-specific templates** — users author them as they encounter banks (see § 7.4).

### 4.3 Two-phase write path: stage → confirm

YNAB's `run_sync` path: pull → atomic upsert → committed. SP2's `ingest_file` path: parse → reconcile → **stage as pending** → user confirms → atomic flip to confirmed (or reject → atomic delete). Both paths use the same underlying `db/_upsert.py` helpers (extracted from SP1 in a small refactor), so the SQL-level discipline (single transaction, `(source_id, external_id)` UNIQUE upsert, integer money) is uniformly enforced.

### 4.4 The `AccountSource` seam holds, with one honest divergence

`StatementAccountSource` implements the same SP1 Protocol as `YNABAccountSource`:
- `source_id`, `kind = "statement"`, `nickname` — populated identically.
- `validate()` → checks template/config presence (not network auth).
- `pull(cursor)` → returns an **empty `SyncDelta`**. Statements don't have a "remote to poll." The Protocol is honored so MCP read tools (`list_sources`, `get_sync_status`, etc.) treat the two adapters uniformly; the write path is `ingest_file`, not `run_sync`.

---

## 5. Repository delta + dependency strategy

### 5.1 Layout

```
src/homefinance/sources/statement/        ← new
├── __init__.py
├── source.py                             # StatementAccountSource
├── ingest.py                             # ingest_file() orchestrator
├── archive.py                            # source-file archiving
├── templates.py                          # template loader (TOML)
└── parsers/
    ├── __init__.py                       # registry + dispatch
    ├── base.py                           # StatementParser Protocol + ParsedStatement
    ├── csv.py                            # template-driven CSV parser (stdlib only)
    ├── ofx.py                            # ofxtools-based; handles OFX and QFX
    └── docling_pdf.py                    # Docling + template

src/homefinance/db/
├── _upsert.py                            ← new (extracted from sources/ynab/sync.py)
└── migrations/
    └── 0002-statement-batches.sql        ← new

src/homefinance/cli.py                    ← extended: accounts/ingest/batches subcommands
src/homefinance/mcp_server/{tools,__main__}.py
                                          ← extended: 4 new tools + 3 surgical updates
pyproject.toml                            ← +[ingest] optional extra

plugin/skills/
├── homefinance-setup/SKILL.md            ← edited: statement-account setup section
├── homefinance-explore/SKILL.md          ← edited: include_pending note
└── homefinance-import-statement/SKILL.md ← new

scripts/record_docling_fixtures.py        ← new (maintainer-only)
tests/fixtures/docling/                   ← new (sanitized captured Docling JSON)
tests/integration/test_docling_live.py    ← new (manual-dispatch CI only)
```

### 5.2 Dependency strategy

```toml
[project.optional-dependencies]
ofx = [
    "ofxtools>=0.10",     # OFX + QFX parsing — pure-Python, no torch
]
ingest = [
    "ofxtools>=0.10",     # OFX + QFX parsing
    "docling>=2.0",       # PDF/image extraction (PyTorch + ~200MB models)
]
```

- `pip install homefinance` → YNAB-only, lean. CSV parser still works (stdlib only).
- `pip install homefinance[ofx]` → adds OFX/QFX (lightweight; no torch). Default CI installs this so OFX/QFX tests run on every PR without the Docling stack.
- `pip install homefinance[ingest]` → full statement support (OFX/QFX + Docling PDF).
- **Parsers are lazy-imported by the registry** — `docling_pdf.py` and `ofx.py` are imported only on first dispatch to them, not at package import time. The lean install never triggers `ImportError`.
- A subprocess-based test (§ 10.5) enforces the lazy-import discipline by asserting `docling` does not appear in `sys.modules` after importing the package.

---

## 6. Data model — migration 0002

One migration. Two new columns on `transactions`. One new table.

```sql
-- Migration 0002: statement batches + transaction status/batch link

CREATE TABLE statement_batches (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                TEXT NOT NULL REFERENCES sources(id),
    file_hash                TEXT NOT NULL,                  -- SHA-256 of the source file
    file_path_original       TEXT NOT NULL,                  -- where the user supplied it
    file_path_archive        TEXT,                           -- where we copied it (NULL if --no-archive)
    parser                   TEXT NOT NULL,                  -- 'csv' | 'ofx' | 'qfx' | 'docling_pdf'
    statement_period_start   TEXT,                           -- YYYY-MM-DD (NULL if parser couldn't detect)
    statement_period_end     TEXT,
    opening_balance_minor    INTEGER,
    closing_balance_minor    INTEGER,
    parsed_at                TEXT NOT NULL,                  -- ISO 8601 UTC
    review_status            TEXT NOT NULL,                  -- 'pending' | 'confirmed' | 'rejected'
    review_resolved_at       TEXT,                           -- ISO 8601 UTC when confirmed/rejected
    txn_count                INTEGER NOT NULL DEFAULT 0,
    reconciliation_status    TEXT NOT NULL,                  -- 'ok' | 'drift' | 'n/a'
    drift_minor              INTEGER,                        -- computed - reported; NULL if recon='n/a'
    notes                    TEXT,
    UNIQUE (file_hash, source_id)                            -- file-level dedup, per source
);

CREATE INDEX idx_statement_batches_source ON statement_batches(source_id);
CREATE INDEX idx_statement_batches_review ON statement_batches(review_status);

ALTER TABLE transactions ADD COLUMN status   TEXT NOT NULL DEFAULT 'confirmed';
ALTER TABLE transactions ADD COLUMN batch_id INTEGER REFERENCES statement_batches(id);

CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_batch  ON transactions(batch_id) WHERE batch_id IS NOT NULL;
```

### 6.1 The `status` column default is the compatibility story

`DEFAULT 'confirmed'` means every existing YNAB row gets `'confirmed'` automatically on migration. New YNAB rows continue inserting with the default — **zero changes needed in `sources/ynab/sync.py`**. Only statement-ingested rows insert with `'pending_review'`. The SP1 zero-rework guarantee holds.

### 6.2 Status enum — two values, not three

| Value | When | Visible to analytics |
|---|---|---|
| **`confirmed`** | All existing YNAB rows; new YNAB rows; statement rows after `confirm_batch` | ✅ Yes (default) |
| **`pending_review`** | Statement rows immediately after `ingest_file`, before user confirms | ❌ Excluded by default |

**Reject = DELETE** the staged rows entirely. The `statement_batches` row stays with `review_status='rejected'` for audit (file hash, parser, parse counts, reconciliation, timestamps — everything except the rows themselves). Re-ingesting requires `--reingest`.

### 6.3 How SP1's MCP tools update

| Tool | Change |
|---|---|
| `query_transactions` | Gains `include_pending: bool = False`. Default unchanged (filter `status = 'confirmed'`). |
| **`summarize_spending`** | **Always** filters `status = 'confirmed'`. **No opt-in.** Aggregations never silently include unconfirmed data. |
| `get_sync_status` | Adds per-source `pending_batch_count` from `statement_batches WHERE review_status='pending'`. |
| All others (`list_sources`, `list_accounts`, `get_account`, `list_categories`, `sync_ynab`) | No change. |

---

## 7. Parser interface + registry

### 7.1 `StatementParser` Protocol

```python
@runtime_checkable
class StatementParser(Protocol):
    name: str                              # 'csv' | 'ofx' | 'qfx' | 'docling_pdf'

    @classmethod
    def claims(cls, path: Path) -> bool:
        """True if this parser thinks it can handle this file.
        Sniffs by extension; may do a light magic-byte check."""
        ...

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        """Parse the file into a structured representation.
        Raises ParseError, TemplateNotFound, etc. on failure."""
        ...
```

### 7.2 `ParsedStatement` dataclass

```python
@dataclass(frozen=True, slots=True)
class ParsedStatement:
    statement_period_start: str | None     # YYYY-MM-DD
    statement_period_end: str | None
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    transactions: tuple[RemoteTransaction, ...]   # SP1 dataclass — REUSED unchanged
    source_format: str                            # parser.name
    parser_metadata: dict[str, Any]               # e.g., template id used, parser warnings
```

Reusing SP1's `RemoteTransaction` is the load-bearing detail of the seam. The same canonical wire type that the YNAB adapter emits is what the statement adapter emits.

### 7.3 Parser-specific notes

- **`CSVParser`** — Requires a template (column mapping). Refuses to import accounts without one. Templates declare which columns are `date`, `amount` (or `inflow`+`outflow`), `payee`, `memo`, and optional `opening_balance`/`closing_balance` cells.
- **`OFXParser` / `QFXParser`** — OFX is structured XML/SGML and self-describing. No template needed. `ofxtools` handles both formats.
- **`DoclingPDFParser`** — Docling extracts structured table cells. Requires a template that names the table (by header text or column position) and maps cells to canonical fields. Without a template: refuses with `TemplateNotFound` and a remediation pointer.

### 7.4 Templates

Live at `~/.homefinance/templates/<source_id>.toml`. Format example for CSV:

```toml
parser = "csv"

[columns]
date         = "Transaction Date"
amount       = "Amount"
payee        = "Description"
memo         = "Notes"

[options]
date_format  = "%m/%d/%Y"
sign         = "natural"     # 'natural' | 'invert' (some banks emit positive for outflows)
```

For Docling PDF:

```toml
parser = "docling_pdf"

[table]
# Either header_match or position_index identifies the transaction table
header_match = ["Date", "Description", "Amount"]

[columns]
date         = 0
payee        = 1
amount       = 2

[options]
date_format  = "%m/%d/%y"
sign         = "natural"
```

**SP2 ships zero pre-built templates.** Users author them as they encounter banks. Documentation includes a worked example per parser type. Claude-assisted template authoring is out-of-scope for SP2 (§ 11 OS-7).

---

## 8. Ingest → confirm flow

### 8.1 The pipeline

`ingest_file(path, account_nickname, archive=True, allow_reingest=False) → BatchPreview`:

1. **Resolve** `account_nickname` → `source_id` (`statement:<nick>`) and `account_id`. If not registered → `AccountNotConfigured`.
2. **Hash** the file: `file_hash = sha256(content).hexdigest()`.
3. **File-level dedup**: check `statement_batches (file_hash, source_id)`.
   - Exists, `pending` or `confirmed` → `FileAlreadyIngested` error.
   - Exists, `rejected` → require `allow_reingest=True` (CLI prompts; MCP requires `--reingest` flag from user).
4. **Dispatch** to parser registry. Sniff by extension first, magic-byte fallback. May raise `NoSuitableParser`, `TemplateNotFound`, `ParseError` — each maps to a user-facing message; no DB writes.
5. **Parse** → `ParsedStatement`.
6. **Build row-level synthetic `external_id`s** (§ 8.2).
7. **Reconcile** (§ 8.4).
8. **Archive** if enabled (§ 8.5). If archive fails → abort BEFORE any DB write.
9. **ATOMIC TRANSACTION** (single `store.transaction()`):
   - `INSERT INTO statement_batches (...)` with `review_status='pending'`.
   - For each row: upsert into `transactions` via `db/_upsert.py` helpers, with `status='pending_review'` and `batch_id=<new>`.
10. **Return `BatchPreview`** = `{batch_id, txn_count, reconciliation_status, drift_minor, period dates, opening/closing balance, first N transactions, file_path_archive}`.

### 8.2 Row-level synthetic `external_id`

PDFs and CSVs lack stable IDs. We manufacture one from row content:

```python
def _row_external_id(account_id: str, date: str, amount_minor: int,
                     payee: str | None, memo: str | None) -> str:
    payload = f"{account_id}|{date}|{amount_minor}|{payee or ''}|{memo or ''}"
    return sha256(payload.encode("utf-8")).hexdigest()[:16]   # 64 bits — ample
```

Two scenarios this handles cleanly:

- **Overlapping statement periods** — June statement and July statement both include the June 30 transaction. Same hash, same row → SP1's `ON CONFLICT (source_id, external_id) DO UPDATE` makes the second a no-op refresh. Idempotent.
- **Within-batch collisions** — two real $4.50 coffees same day, same merchant, same memo. Suffix with `:N` per-batch:

```python
seen: dict[str, int] = {}
for txn in parsed.transactions:
    base = _row_external_id(account_id, txn.date, txn.amount_minor, txn.payee, txn.memo)
    n = seen.get(base, 0)
    external_id = base if n == 0 else f"{base}:{n}"
    seen[base] = n + 1
```

Order-sensitive: parsers must preserve transaction order from the source.

### 8.3 File-level dedup

`UNIQUE (file_hash, source_id)` on `statement_batches`. Same file, same source = blocked. Same file, different source = allowed. `--reingest` semantics:

1. DELETE the prior batch row from `statement_batches` (audit lost — explicit opt-in).
2. Re-run pipeline from step 4.

### 8.4 Reconciliation

```python
if opening_balance_minor is not None and closing_balance_minor is not None:
    expected = closing_balance_minor - opening_balance_minor
    actual   = sum(t.amount_minor for t in transactions)
    drift    = actual - expected
    status   = 'ok' if drift == 0 else 'drift'
else:
    status, drift = 'n/a', None
```

**Drift never rejects** and **never auto-confirms.** Drift sets `reconciliation_status='drift'` and `drift_minor=<delta>`. The batch lands as `pending_review` regardless. `recon='ok'` is a *signal* that makes confirmation easy; not a license to skip it.

### 8.5 Archive

Default: ON. Path: `~/.homefinance/archive/<source_id>/<file_hash>.<original_extension>`.
- Hash-named for collision-free storage; original path preserved in `statement_batches.file_path_original`.
- Archive directory created with mode 0o700 (consistent with config dir security).
- `--no-archive` skips the copy; `file_path_archive` stays NULL.
- Archive failure (disk full, permissions) → `ArchiveFailed` error **before any DB write**.

### 8.6 Confirm / reject lifecycle

Both atomic, both idempotent on already-resolved batches:

```sql
-- confirm
BEGIN;
UPDATE transactions       SET status='confirmed'
                          WHERE batch_id = ? AND status = 'pending_review';
UPDATE statement_batches  SET review_status='confirmed', review_resolved_at = ?
                          WHERE id = ? AND review_status = 'pending';
COMMIT;

-- reject
BEGIN;
DELETE FROM transactions  WHERE batch_id = ?;
UPDATE statement_batches  SET review_status='rejected', review_resolved_at = ?
                          WHERE id = ? AND review_status = 'pending';
COMMIT;
```

Confirm on already-confirmed: no-op (WHERE filters). Reject on already-rejected: no-op. Confirm on rejected: returns error (rows are gone). Reject on confirmed: returns error (destructive on confirmed data; user must explicitly DELETE if they really mean it — out of scope).

---

## 9. CLI + MCP surface

### 9.1 Five new CLI commands

| Command | Purpose | Key flags |
|---|---|---|
| `homefinance accounts add` | Register a statement-fed account | `--nickname` (required), `--type` (required), `--currency`, `--display-name` |
| `homefinance ingest <path>` | Parse + stage a statement | `--account` (required), `--no-archive`, `--no-prompt`, `--reingest` |
| `homefinance batches` | List batches | `--pending\|--confirmed\|--rejected\|--all` (default `--pending`), `--source` |
| `homefinance batch confirm <id>` | Confirm | — |
| `homefinance batch reject <id>` | Reject | — |

**CLI prompt model**: `homefinance ingest` with prompt (default) parses + stages, then renders a Rich preview table and asks `Confirm? [y/N/show-more]`. `--no-prompt` just stages and prints the batch id for scripting.

**Account-id model**: each statement-fed account → `source_id = statement:<nickname>`, `account_id = statement:<nickname>:account` (with `account` as the constant `external_id`). Preserves SP1's source→N-accounts hierarchy even though N=1 for statements. Multi-account statements (one PDF, multiple bank accounts) are explicitly out of scope (§ 11, OS-1).

**Updates to existing SP1 CLI:**
- `homefinance status` — adds a "Pending batches" sub-table when any exist.
- `homefinance sync` — unchanged.

### 9.2 Four new MCP tools

| Tool | Returns |
|---|---|
| `ingest_statement(path, account_nickname, archive=True)` | `BatchPreview` dict |
| `list_batches(source_id?, review_status='pending')` | `list[batch_dict]` |
| `confirm_batch(batch_id)` | result dict |
| `reject_batch(batch_id)` | result dict |

Plus the three SP1 tool updates from § 6.3.

Total MCP surface after SP2: **12 tools** (8 SP1 + 4 new), with 3 SP1 tools getting parameter or behavior tweaks. No new `register_statement_account` MCP tool — account registration is setup-time CLI only, matching YNAB's pattern.

### 9.3 Skills

| Skill | Status | Purpose |
|---|---|---|
| `homefinance-import-statement` | **New** | Orchestrates `ingest_statement → preview → confirm/reject`. Embeds rule: **never auto-confirm**, even on `recon='ok'`. |
| `homefinance-setup` | Edited | Adds a "Setting up statement-fed accounts" section walking through `homefinance accounts add`. |
| `homefinance-explore` | Edited | Brief note about `include_pending` so Claude knows to opt in only when explicitly asked. |

---

## 10. Error handling, drift policy, testing

### 10.1 Parser error model

| Class | When | What the user sees | DB side effect |
|---|---|---|---|
| `AccountNotConfigured` | Unknown `--account` nickname | "no account `<nick>` configured. Run `homefinance accounts add --nickname <nick> --type checking` first." | None |
| `NoSuitableParser` | Registry can't claim the file | "no parser knows `<path>` (saw extension `.txt`). Supported: csv, ofx, qfx, pdf." | None |
| `TemplateNotFound` | Parser needs per-account template | "no column-mapping template for account `citi-cc`; create one at `~/.homefinance/templates/citi-cc.toml`. Example: …" | None |
| `ParseError` | Right format, malformed | "could not parse `<path>` as `csv`: row 12: amount column missing." | None |
| `ArchiveFailed` | Cannot copy file to archive | "could not archive `<path>` to `<archive_dir>`: <reason>. No data written." | **None — aborts BEFORE DB write** |
| `FileAlreadyIngested` | `UNIQUE (file_hash, source_id)` violation | "already ingested as batch #N on YYYY-MM-DD. Use `--reingest` to re-process." | None |

Each is a distinct Python exception with a stable error code; MCP callers branch on `error.code`, not parse the message.

### 10.2 Drift policy summary (rolled up)

- **Drift never rejects** the batch and **never auto-confirms** it.
- **All batches require explicit human confirmation**, regardless of reconciliation status. `recon='ok'` is a signal that makes confirmation easy; not a license to skip it.
- **`summarize_spending` always excludes `pending_review`** — no opt-in.
- **`query_transactions` defaults to excluding `pending_review`**; `include_pending=True` opt-in for explicit review queries.

### 10.3 Three-tier testing strategy

| Tier | Coverage | Speed |
|---|---|---|
| **Unit** — `tests/test_statement_parsers/` | `CSVParser` (template-driven mapping, missing-column errors, signed-amount handling, balance extraction). OFX/QFX (sanitized real-bank exports as fixtures). `DoclingPDFParser` logic against captured Docling JSON via `FakeDoclingPDFParser`. | Sub-second per test |
| **Integration** — `tests/test_ingest.py` | Full pipeline: parse → reconcile → stage → confirm → analytic query. Idempotency on re-ingest. Row-hash dedup across overlapping statement periods. Confirm flips status. Reject deletes rows. `ArchiveFailed` aborts before DB writes. | Few hundred ms per test |
| **End-to-end** — `tests/test_cli.py`, `tests/test_mcp_tools.py` | `homefinance ingest --no-prompt` → batch exists. `homefinance batch confirm` → status flipped. `CliRunner(input=...)` simulates inline `[y/N]` prompt. MCP tools called as plain functions per SP1 pattern. | Slower; few tests |

### 10.4 Docling carve-out

**Docling is never imported in CI's default test run.** Reason: ~500 MB of PyTorch + ~200 MB of layout models. CI runtime would balloon 5+ minutes per matrix entry. Mirror the SP1 `FakeYNABClient` pattern:

- `FakeDoclingPDFParser` — test double that consumes pre-captured Docling structured JSON from `tests/fixtures/docling/<name>/`.
- `scripts/record_docling_fixtures.py` — maintainer-only script. Runs real Docling against a sample PDF, captures structured output, sanitizes (amounts/names per SP1 pattern), saves to fixtures.
- `tests/integration/test_docling_live.py` — opt-in via `pytest tests/integration -m docling`. Not in default `pytest`.

### 10.5 Lazy-import enforcement (load-bearing)

```python
def test_homefinance_does_not_import_docling_without_extra():
    code = (
        "import sys, homefinance, homefinance.sources.statement, "
        "homefinance.sources.statement.parsers; "
        "leaks = [m for m in sys.modules if 'docling' in m]; "
        "assert leaks == [], f'Docling leaked: {leaks}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
```

This is the contract that the lean install stays lean. Any future top-level `import docling` in a parser file fails this test, forcing the import to move inside the method.

### 10.6 CI updates

| Job | Trigger | Installs | Runs |
|---|---|---|---|
| `test` *(existing, edited)* | push + PR to main | `pip install -e ".[dev,ofx]"` (lightweight OFX/QFX; no Docling/torch) | Tiers 1, 2 (via `FakeDoclingPDFParser`), 3 |
| `test-docling` *(new)* | `workflow_dispatch` only | `pip install -e ".[dev,ingest]"` | `pytest tests/integration -m docling` |

Default CI stays under a minute. Live-Docling job runs on demand.

### 10.7 Coverage threshold

Hold at **80%** (SP1's bar). Parser code is mostly straightforward to test; the `FakeDoclingPDFParser` keeps the threshold realistic for the unit/integration tiers.

---

## 11. Out of scope

| | What | Where |
|---|---|---|
| OS-1 | Multi-account statements (one PDF, multiple bank accounts' rows) | Possibly SP2.x or SP3 if real demand. Document as known limitation. |
| OS-2 | Pre-built bank template library | SP2 ships the *machinery*; users author templates. Pre-built templates can land later as a separate `homefinance-templates` distribution. |
| OS-3 | Categorization of statement-ingested rows | SP3 |
| OS-4 | Bills as a distinct entity with due-date / scheduled semantics | SP3 / SP4 — "bills" in SP2 are just statement-derived transactions |
| OS-5 | Auto-confirm on `reconciliation_status='ok'` | Never (C-9 — every batch needs human confirmation) |
| OS-6 | Background daemon / watched folder for ingestion | Never (preserves SP1 § 7.7 stance) |
| OS-7 | Claude-assisted template authoring | Possibly SP2.x as standalone tooling; not part of SP2 v1 |
| OS-8 | Claude-assisted money extraction at runtime | Never (C-8) |
| OS-9 | Image-only PDFs (pure scanned, no text layer) | Docling's OCR can handle these but quality varies; ship with a warning, leave OCR-tuning for users |

---

## 12. Open questions / parked decisions

| | Question | When to revisit |
|---|---|---|
| OQ-1 | Template format extensibility (allow Python templates for parsers that need procedural logic?) | If TOML templates prove insufficient for a real bank during SP2 dogfooding |
| OQ-2 | Whether to expose an `ingest_directory` CLI / MCP shortcut for bulk import | After SP2 lands and users have ingested 10+ statements |
| OQ-3 | `BatchPreview` first-N-transactions sample size (default 5? 10?) | First MCP usage by Claude — adjust based on what Claude needs to make a good summary |

---

## 13. Next steps

1. User reviews this spec.
2. On approval, invoke `superpowers:writing-plans` to produce the implementation plan.
3. Implementation proceeds per the plan with TDD and incremental commits, on a new `sp2-ingest` branch off `main`.
