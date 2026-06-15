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
from homefinance.sources.statement.ingest import (
    AccountAlreadyRegistered,
)
from homefinance.sources.statement.ingest import (
    confirm_batch as _confirm_batch,
)
from homefinance.sources.statement.ingest import (
    ingest_file as _ingest_file,
)
from homefinance.sources.statement.ingest import (
    list_batches as _list_batches,
)
from homefinance.sources.statement.ingest import (
    register_account as _register_statement_account,
)
from homefinance.sources.statement.ingest import (
    reject_batch as _reject_batch,
)
from homefinance.sources.statement.parsers.base import StatementIngestError
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
    # O_CREAT's mode arg only applies on *creation*. If `path` pre-existed at
    # a looser mode (e.g., 0o644), the file inode kept its prior bits. Enforce
    # 0o600 unconditionally so an upgrade from a permissive layout tightens.
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


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
        console.print("[yellow]No sources configured.[/] Run [bold]homefinance init[/] first.")
        return
    store = Store.open(cfg.db_path)
    rows = store.execute(
        "SELECT s.id AS source_id, s.kind, s.nickname, "
        "ss.last_sync_at, ss.server_knowledge, "
        "(SELECT reconciliation FROM sync_runs WHERE source_id = s.id "
        " ORDER BY id DESC LIMIT 1) AS last_recon, "
        "(SELECT COUNT(*) FROM statement_batches "
        " WHERE source_id = s.id AND review_status = 'pending') AS pending_batches "
        "FROM sources s "
        "LEFT JOIN sync_state ss ON ss.source_id = s.id "
        "ORDER BY s.id"
    ).fetchall()

    if not rows:
        console.print("[yellow]No sources configured.[/] Run [bold]homefinance init[/] first.")
        return

    table = Table(title="Sources")
    table.add_column("source_id")
    table.add_column("nickname")
    table.add_column("last sync")
    table.add_column("cursor", justify="right")
    table.add_column("reconciliation")
    table.add_column("pending", justify="right")
    for r in rows:
        table.add_row(
            r["source_id"],
            r["nickname"] or "-",
            r["last_sync_at"] or "(never)",
            str(r["server_knowledge"] or "-"),
            r["last_recon"] or "-",
            str(r["pending_batches"] or "-"),
        )
    console.print(table)


@app.command()
def init(
    token: str | None = typer.Option(
        None,
        "--token",
        envvar="HOMEFINANCE_YNAB_TOKEN",
        help="YNAB Personal Access Token. If omitted, prompted interactively.",
    ),
    budget_ids: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--budget",
        "-b",
        help="Budget IDs to track. May be repeated. If omitted, prompted.",
    ),
    nicknames: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--nickname",
        "-n",
        help="Nicknames matching --budget order. Defaults to budget name slug.",
    ),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip the post-setup sync."),
    save_token_to_file: bool = typer.Option(
        False,
        "--save-token-to-file",
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
        None,
        "--source",
        "-s",
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
        err_console.print("[red]No budgets configured.[/] Run [bold]homefinance init[/].")
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


@ynab_app.command("add-budget")
def ynab_add_budget(
    budget_id: str = typer.Option(..., "--budget-id", help="YNAB budget ID."),
    nickname: str | None = typer.Option(None, "--nickname"),
) -> None:
    """Register an additional YNAB budget in config.toml."""
    cfg = load_config()
    if any(b.budget_id == budget_id for b in cfg.ynab.budgets):
        err_console.print(f"[red]Budget {budget_id!r} is already registered.[/]")
        raise typer.Exit(code=1)
    new_list = [*cfg.ynab.budgets, YNABBudget(budget_id=budget_id, nickname=nickname)]
    _secure_write_config(cfg.config_path, _render_config_toml(new_list, include_token=None))
    console.print(f"[green]Added[/] budget {budget_id} (nickname: {nickname or '-'})")


@ynab_app.command("remove-budget")
def ynab_remove_budget(
    budget_id: str = typer.Option(..., "--budget-id"),
) -> None:
    """Remove a YNAB budget from config.toml. Does not delete its data from the DB."""
    cfg = load_config()
    new_list = [b for b in cfg.ynab.budgets if b.budget_id != budget_id]
    if len(new_list) == len(cfg.ynab.budgets):
        err_console.print(f"[red]Budget {budget_id!r} not found in config.[/]")
        raise typer.Exit(code=1)
    _secure_write_config(cfg.config_path, _render_config_toml(new_list, include_token=None))
    console.print(
        f"[yellow]Removed[/] budget {budget_id} from config. Existing data in the DB is preserved."
    )


accounts_app = typer.Typer(help="Manage local accounts (e.g., statement-fed).")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("add")
def accounts_add(
    nickname: str = typer.Option(..., "--nickname", "-n"),
    account_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="checking | savings | credit_card | investment | loan | cash | other",
    ),
    currency: str = typer.Option("USD", "--currency"),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    """Register a statement-fed account in the local store."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)
    try:
        ra = _register_statement_account(
            store,
            nickname=nickname,
            type=account_type,
            currency=currency,
            display_name=display_name,
        )
    except AccountAlreadyRegistered as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Added[/] {ra.source_id} (type: {ra.type}, currency: {ra.currency})")


def _render_preview(preview: object) -> Table:
    """Render a BatchPreview as a small Rich table for inline confirmation."""
    from homefinance.sources.statement.ingest import BatchPreview

    p = preview if isinstance(preview, BatchPreview) else None
    assert p is not None
    summary = Table(title=f"Batch #{p.batch_id} — {p.source_id}")
    summary.add_column("field")
    summary.add_column("value")
    summary.add_row("transactions", str(p.txn_count))
    summary.add_row(
        "period",
        f"{p.statement_period_start or '?'} → {p.statement_period_end or '?'}",
    )
    summary.add_row(
        "reconciliation",
        f"{p.reconciliation_status}"
        + (f" (drift: {p.drift_minor / 100:+.2f})" if p.drift_minor else ""),
    )
    return summary


@app.command()
def ingest(
    path: str = typer.Argument(...),
    account: str = typer.Option(..., "--account", "-a"),
    no_archive: bool = typer.Option(False, "--no-archive"),
    no_prompt: bool = typer.Option(False, "--no-prompt"),
    reingest: bool = typer.Option(False, "--reingest"),
) -> None:
    """Parse + stage a statement file; prompt to confirm or reject."""
    cfg = load_config()
    if not cfg.db_path.exists():
        migrate(cfg.db_path)
    store = Store.open(cfg.db_path)

    try:
        preview = _ingest_file(
            store,
            path=Path(path),
            account_nickname=account,
            config_dir=cfg.config_path.parent,
            archive_dir=cfg.config_path.parent / "archive",
            archive=not no_archive,
            allow_reingest=reingest,
        )
    except StatementIngestError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None

    console.print(_render_preview(preview))

    if no_prompt:
        console.print(
            f"[yellow]Staged[/] batch_id={preview.batch_id} "
            "(pending review). Confirm with: "
            f"[bold]homefinance batch confirm {preview.batch_id}[/]"
        )
        return

    choice = typer.prompt("Confirm? [y/N/show-more]", default="N").strip().lower()
    if choice == "show-more":
        for t in preview.first_transactions:
            console.print(
                f"  {t.date}  {t.amount_minor / 100:+9.2f}  {t.payee or '-'}  {t.memo or ''}"
            )
        choice = typer.prompt("Confirm? [y/N]", default="N").strip().lower()
    if choice == "y":
        _confirm_batch(store, preview.batch_id)
        console.print(f"[green]Confirmed[/] batch #{preview.batch_id}.")
    else:
        _reject_batch(store, preview.batch_id)
        console.print(f"[yellow]Rejected[/] batch #{preview.batch_id}.")


@app.command()
def batches(
    pending: bool = typer.Option(True, "--pending"),
    confirmed: bool = typer.Option(False, "--confirmed"),
    rejected: bool = typer.Option(False, "--rejected"),
    all_: bool = typer.Option(False, "--all"),
    source: str | None = typer.Option(None, "--source"),
) -> None:
    """List statement batches in the local store."""
    del pending  # default-on flag; selection logic below honors the others first
    cfg = load_config()
    if not cfg.db_path.exists():
        console.print("[yellow]No database. Nothing to list.[/]")
        return
    store = Store.open(cfg.db_path)

    if all_:
        status = None
    elif rejected:
        status = "rejected"
    elif confirmed:
        status = "confirmed"
    else:
        status = "pending"

    rows = _list_batches(store, source_id=source, review_status=status)
    if not rows:
        label = "any" if status is None else status
        console.print(f"[yellow]No {label} batches.[/]")
        return

    table = Table(title=f"Statement Batches ({status or 'all'})")
    table.add_column("batch_id", justify="right")
    table.add_column("source", no_wrap=True)
    table.add_column("parsed_at", no_wrap=True)
    table.add_column("count", justify="right")
    table.add_column("reconciliation")
    table.add_column("status")
    for r in rows:
        recon = r["reconciliation_status"]
        if r["drift_minor"]:
            recon += f" ({r['drift_minor'] / 100:+.2f})"
        table.add_row(
            str(r["id"]),
            r["source_id"],
            r["parsed_at"],
            str(r["txn_count"]),
            recon,
            r["review_status"],
        )
    console.print(table)


batch_app = typer.Typer(help="Per-batch operations.")
app.add_typer(batch_app, name="batch")


@batch_app.command("confirm")
def batch_confirm_cmd(batch_id: int) -> None:
    """Confirm a pending batch."""
    cfg = load_config()
    store = Store.open(cfg.db_path)
    try:
        _confirm_batch(store, batch_id)
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Confirmed[/] batch #{batch_id}.")


@batch_app.command("reject")
def batch_reject_cmd(batch_id: int) -> None:
    """Reject a pending batch (deletes its staged transactions)."""
    cfg = load_config()
    store = Store.open(cfg.db_path)
    try:
        _reject_batch(store, batch_id)
    except ValueError as e:
        err_console.print(f"[red]{e}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[yellow]Rejected[/] batch #{batch_id}.")
