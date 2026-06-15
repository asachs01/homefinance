"""Template-driven CSV parser. Stdlib only."""

from __future__ import annotations

import csv as _csv
from datetime import datetime
from pathlib import Path
from typing import Any

from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.parsers import register
from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ParseError,
    ResolvedAccount,
    TemplateNotFound,
)


class CSVParser:
    name = "csv"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".csv"

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        if template is None:
            raise TemplateNotFound(
                f"no column-mapping template for {account.source_id!r}; "
                f"create one at <config_dir>/templates/{account.source_id}.toml"
            )
        cols = template.get("columns") or {}
        opts = template.get("options") or {}
        date_fmt = opts.get("date_format", "%Y-%m-%d")
        sign = opts.get("sign", "natural")

        date_col = cols.get("date")
        amount_col = cols.get("amount")
        if not date_col or not amount_col:
            raise ParseError("template missing required columns: 'date' and 'amount' are mandatory")

        payee_col = cols.get("payee")
        memo_col = cols.get("memo")

        transactions: list[RemoteTransaction] = []
        with Path(path).open(newline="", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            if reader.fieldnames is None or date_col not in reader.fieldnames:
                raise ParseError(f"column {date_col!r} not found in CSV header")
            if amount_col not in reader.fieldnames:
                raise ParseError(f"column {amount_col!r} not found in CSV header")
            for i, row in enumerate(reader):
                try:
                    canonical_date = datetime.strptime(row[date_col], date_fmt).date().isoformat()
                except ValueError as e:
                    raise ParseError(f"row {i + 2}: bad date {row[date_col]!r}: {e}") from e
                amount_str = (row[amount_col] or "").replace(",", "").replace("$", "").strip()
                if not amount_str:
                    raise ParseError(f"row {i + 2}: empty amount")
                try:
                    amount_minor = round(float(amount_str) * 100)
                except ValueError as e:
                    raise ParseError(f"row {i + 2}: bad amount {amount_str!r}: {e}") from e
                if sign == "invert":
                    amount_minor = -amount_minor
                payee = (row.get(payee_col, "").strip() or None) if payee_col else None
                memo = (row.get(memo_col, "").strip() or None) if memo_col else None
                transactions.append(
                    RemoteTransaction(
                        external_id="",
                        account_external_id="account",
                        date=canonical_date,
                        amount_minor=amount_minor,
                        currency=account.currency,
                        payee=payee,
                        payee_external_id=None,
                        memo=memo,
                        category_external_id=None,
                        cleared=None,
                        approved=True,
                        flag_color=None,
                        import_id=None,
                        transfer_account_external_id=None,
                        deleted=False,
                    )
                )

        return ParsedStatement(
            statement_period_start=None,
            statement_period_end=None,
            opening_balance_minor=None,
            closing_balance_minor=None,
            transactions=tuple(transactions),
            source_format=cls.name,
            parser_metadata={"row_count": len(transactions)},
        )


# Register on import. The orchestrator imports this module lazily via the
# registry, so this side effect only fires when CSV is actually needed.
register(".csv", "homefinance.sources.statement.parsers.csv:CSVParser")
