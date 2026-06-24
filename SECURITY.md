# Security Policy

`homefinance` handles sensitive personal financial data. Security and privacy
reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue for security or privacy vulnerabilities.**

Instead, report privately via either:

- GitHub's [private vulnerability reporting](https://github.com/asachs01/homefinance/security/advisories/new)
  (Security → Report a vulnerability), or
- Email **aaron@wyretechnology.com** with the details.

Please include:

- A description of the issue and its impact.
- Steps to reproduce (with **synthetic** data only — never real account
  information or tokens).
- Affected version / commit, and any suggested remediation.

You can expect an initial acknowledgement within a few days. Once resolved, we're
happy to credit you in the release notes if you'd like.

## Scope & design posture

`homefinance` is **local-first** by design — this shapes what counts as a
vulnerability:

- All data lives locally (`~/.homefinance/`). The only outbound network call is
  read-only access to `api.ynab.com`.
- YNAB access is **read-only**; there is no write path to your budget.
- There is **no telemetry**, analytics, or remote logging.
- The YNAB Personal Access Token is a secret: it belongs in `~/.homefinance/config.toml`
  or the `HOMEFINANCE_YNAB_TOKEN` environment variable — never in the repo.

Examples of in-scope reports: a token or financial data being logged, written to
an unexpected location, or transmitted off-machine; a parser that can be coerced
into reading/writing outside the data directory; or any path that exposes one
user's data to another.

## Supported versions

This project is pre-1.0; security fixes are applied to the latest `main`. Please
make sure you can reproduce on the current `main` before reporting.
