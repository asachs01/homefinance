"""``homefinance`` — the local CLI.

Two commands ship in Task 17 (``db-path``, ``status``). ``init``, ``sync``,
and the ``ynab`` subcommands land in Tasks 18-20.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from homefinance.config import load_config
from homefinance.db.store import Store
from homefinance.sources.ynab.client import YNABClient

app = typer.Typer(
    help="homefinance — open-source, local-first home financial analysis.",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _make_client(token: str) -> YNABClient:
    """Factory so tests can monkeypatch in a FakeYNABClient."""
    return YNABClient(token=token)


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


# Placeholders for Tasks 18-20 so `homefinance --help` lists them; the actual
# implementations replace these in later tasks.

@app.command()
def init() -> None:
    """Interactive first-run setup. Implemented in Task 18."""
    raise typer.Exit(code=2)  # placeholder; tests in Task 18 cover real behavior


@app.command()
def sync(source: str | None = typer.Option(None, "--source", "-s")) -> None:
    """Sync one or all sources. Implemented in Task 19."""
    raise typer.Exit(code=2)


ynab_app = typer.Typer(help="YNAB budget management.")
app.add_typer(ynab_app, name="ynab")
