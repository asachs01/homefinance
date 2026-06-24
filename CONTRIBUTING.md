# Contributing to homefinance

Thanks for your interest in improving **homefinance** — an open-source, local-first
home financial analysis tool distributed as a Claude Code plugin.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## ⚠️ Never share real financial data

This is a personal-finance project. **Do not** include real account numbers,
balances, transaction exports, statement files, or YNAB tokens in issues, pull
requests, test fixtures, or commits. Use small, clearly synthetic samples (see
`tests/fixtures/statement/` for the pattern — fake bank/account IDs, generic
merchants). Treat any secret that lands in git history as compromised and rotate it.

## Development setup

Requires **Python 3.11+** (CI runs 3.11 and 3.12).

```bash
git clone https://github.com/asachs01/homefinance.git
cd homefinance
python -m venv .venv && source .venv/bin/activate

# [dev] = test + lint tooling; [ofx] = pure-Python OFX/QFX parsers (what CI uses)
pip install -e ".[dev,ofx]"
```

> Heads-up for macOS users: keep your clone **outside** iCloud-synced folders
> (`~/Documents`, `~/Desktop`). iCloud can evict `.git` pack files to "dataless"
> stubs, which makes git fail with `mmap failed: Resource deadlock avoided`.

PDF statement ingestion (Docling) is optional and heavy (~500 MB of PyTorch +
models). Install it only if you're working on that path:

```bash
pip install -e ".[ingest]"
```

## Before you open a pull request

Run the same checks CI does — all must pass:

```bash
ruff check .                 # lint
ruff format --check .        # formatting
mypy                         # strict type-checking (src/)
pytest --cov=homefinance --cov-report=term-missing --cov-fail-under=80
```

`ruff format .` (without `--check`) auto-fixes formatting.

## Conventions

- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` — with an optional
  scope, e.g. `fix(retirement): …`.
- **Changelog**: add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md)
  for any user-facing change. The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- **Money** is always stored as signed integer minor units (cents). Floats must
  never enter the store.
- **YNAB access is read-only**, by design. Don't add write paths to the YNAB client.
- New parsers go behind the existing Strategy-pattern registry; database changes
  ship as a new numbered migration.
- Keep it simple. Readable, maintainable code is valued over clever code.

## Pull request flow

1. Fork and branch from `main` (e.g. `feat/recurring-forecast`).
2. Make the change, add/adjust tests, update the changelog.
3. Ensure the checks above pass locally.
4. Open a PR against `main` and fill out the template.

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/asachs01/homefinance/issues/new/choose).
For anything security- or privacy-sensitive, follow [SECURITY.md](SECURITY.md)
instead of opening a public issue.
