"""``homefinance`` — the local CLI.

Two commands ship in Task 17 (``db-path``, ``status``). ``init``, ``sync``,
and the ``ynab`` subcommands land in Tasks 18-20.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import cast

import typer
from rich.console import Console
from rich.table import Table

from homefinance.config import YNABBudget, load_config
from homefinance.db.migrate import migrate
from homefinance.db.store import Store
from homefinance.sources.base import AccountSource
from homefinance.sources.ynab.client import YNABClient
from homefinance.sources.ynab.source import YNABAccountSource
from homefinance.sources.ynab.sync import run_sync

app = typer.Typer(
    help="homefinance — open-source, local-first home financial analysis.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _make_client(token: str) -> YNABClient:
    """Factory so tests can monkeypatch in a FakeYNABClient."""
    return YNABClient(token=token)


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _secure_write_config(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` with file mode 0o600 and parent dir 0o700.

    Creates parents as needed; tightens permissions on existing parent dirs.
    Used for any file that may contain credentials (currently the YNAB
    config TOML).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Tighten permissions on the parent directory (idempotent; does nothing
    # if already 0o700 or stricter). Best-effort on systems that don't
    # support chmod (e.g., Windows).
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def _render_config_toml(budgets: list[YNABBudget], include_token: str | None) -> str:
    lines: list[str] = []
    if include_token:
        lines += ["[ynab]", f'token = "{_toml_escape(include_token)}"', ""]
    for b in budgets:
        lines += [
            "[[ynab.budgets]]",
            f'budget_id = "{_toml_escape(b.budget_id)}"',
        ]
        if b.nickname:
            lines.append(f'nickname = "{_toml_escape(b.nickname)}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@app.command("db-path")
def db_path() -> None:
    """Print the resolved database path."""
    cfg = load_config()
    # Use plain print to avoid Rich's soft-wrap inserting newlines into long paths.
    print(str(cfg.db_path))


@app.command()
def status() -> None:
    """Show configured sources and their last-sync state."""
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print(
            "[yellow]No sources configured.[/] Run [bold]homefinance init[/] first."
        )
        return
    store = Store.open(cfg.db_path)
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_recon "
        "FROM sources s "
        "LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    if not rows:
        console.print(
            "[yellow]No sources configured.[/] Run [bold]homefinance init[/] first."
        )
        return

    table = Table(title="Sources")
    table.add_column("source_id")
    table.add_column("nickname")
    table.add_column("last sync")
    table.add_column("cursor", justify="right")
    table.add_column("reconciliation")
    for r in rows:
        table.add_row(
            r["source_id"],
            r["nickname"] or "-",
            r["last_sync_at"] or "(never)",
            str(r["server_knowledge"] or "-"),
            r["last_recon"] or "-",
        )
    console.print(table)


@app.command()
def init(
    token: str | None = typer.Option(
        None, "--token",
        envvar="HOMEFINANCE_YNAB_TOKEN",
        help="YNAB Personal Access Token. If omitted, prompted interactively.",
    ),
    budget_ids: list[str] | None = typer.Option(  # noqa: B008
        None, "--budget", "-b",
        help="Budget IDs to track. May be repeated. If omitted, prompted.",
    ),
    nicknames: list[str] | None = typer.Option(  # noqa: B008
        None, "--nickname", "-n",
        help="Nicknames matching --budget order. Defaults to budget name slug.",
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the post-setup sync."
    ),
    save_token_to_file: bool = typer.Option(
        False, "--save-token-to-file",
        help="Persist the token to config.toml (default: keep it in env only).",
    ),
) -> None:
    """First-run setup: write config, register budgets, migrate DB, optionally sync."""
    cfg = load_config()

    # 1. Resolve token (prompt only if neither flag nor env supplied it).
    effective_token = token
    if effective_token is None:
        effective_token = typer.prompt("YNAB Personal Access Token", hide_input=True)

    client = _make_client(effective_token)
    available = client.get_budgets().data.budgets
    if not available:
        err_console.print("[red]No YNAB budgets found for this token.[/]")
        raise typer.Exit(code=1)

    # 2. Pick budgets.
    if not budget_ids:
        console.print("Available budgets:")
        for i, b in enumerate(available):
            console.print(f"  [{i}] {b.name}  ({b.id})")
        raw = typer.prompt("Comma-separated indices to track", default="0")
        try:
            idx = [int(x.strip()) for x in raw.split(",")]
            budget_ids = [available[i].id for i in idx]
        except (ValueError, IndexError):
            err_console.print("[red]Invalid selection.[/]")
            raise typer.Exit(code=1) from None

    if nicknames and len(nicknames) != len(budget_ids):
        err_console.print("[red]--nickname count must match --budget count.[/]")
        raise typer.Exit(code=1)

    by_id = {b.id: b for b in available}
    selected: list[YNABBudget] = []
    for i, bid in enumerate(budget_ids):
        if bid not in by_id:
            err_console.print(f"[red]Budget {bid!r} not found in this YNAB account.[/]")
            raise typer.Exit(code=1)
        nick = nicknames[i] if nicknames else by_id[bid].name.lower().replace(" ", "-")
        selected.append(YNABBudget(budget_id=bid, nickname=nick))

    # 3. Write config + migrate.
    toml = _render_config_toml(
        selected, include_token=effective_token if save_token_to_file else None
    )
    _secure_write_config(cfg.config_path, toml)
    migrate(cfg.db_path)
    console.print(f"[green]Config written:[/] {cfg.config_path}")
    console.print(f"[green]Database ready:[/] {cfg.db_path}")

    if no_sync:
        return

    # 4. First sync per budget.
    store = Store.open(cfg.db_path)
    for sb in selected:
        source = YNABAccountSource(sb.budget_id, client, nickname=sb.nickname)
        result = run_sync(cast(AccountSource, source), store)
        console.print(
            f"[green]Synced[/] {sb.nickname}: "
            f"{result.txns_inserted} new, {result.txns_updated} updated, "
            f"{result.txns_deleted} deleted; reconciliation={result.reconciliation}"
        )


@app.command()
def sync(
    source: str | None = typer.Option(
        None, "--source", "-s",
        help="Sync only the named source_id (e.g., ynab:abc). Default: all.",
    ),
) -> None:
    """Sync one or all configured budgets."""
    cfg = load_config()
    if cfg.ynab_token is None:
        err_console.print(
            "[red]No YNAB token configured.[/] Set "
            "[bold]HOMEFINANCE_YNAB_TOKEN[/] or add [bold][ynab].token[/] to "
            f"{cfg.config_path}."
        )
        raise typer.Exit(code=1)
    if not cfg.ynab.budgets:
        err_console.print(
            "[red]No budgets configured.[/] Run [bold]homefinance init[/]."
        )
        raise typer.Exit(code=1)

    client = _make_client(cfg.ynab_token.get_secret_value())
    store = Store.open(cfg.db_path)

    targets = cfg.ynab.budgets
    if source is not None:
        targets = [b for b in cfg.ynab.budgets if f"ynab:{b.budget_id}" == source]
        if not targets:
            err_console.print(f"[red]Source {source!r} not found in config.[/]")
            raise typer.Exit(code=1)

    for b in targets:
        src = YNABAccountSource(b.budget_id, client, nickname=b.nickname)
        result = run_sync(cast(AccountSource, src), store)
        console.print(
            f"[green]Synced[/] {b.nickname or b.budget_id}: "
            f"{result.txns_inserted} new, {result.txns_updated} updated, "
            f"{result.txns_deleted} deleted; reconciliation={result.reconciliation}"
        )


ynab_app = typer.Typer(help="YNAB budget management.")
app.add_typer(ynab_app, name="ynab")
