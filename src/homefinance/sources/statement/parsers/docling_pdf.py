"""Docling-based PDF parser.

The real ``DoclingPDFParser.parse()`` lazy-imports ``docling`` only when
actually dispatched. The post-Docling logic — taking a ``cells`` dict
(header + rows + balances) and producing a ``ParsedStatement`` — lives in
the free function ``_map_cells_to_transactions``. Tests bypass Docling via
``FakeDoclingPDFParser`` which loads pre-captured ``cells.json`` directly.

CI never imports ``docling``; see the lazy-import enforcement test in
``tests/test_lazy_import.py``.
"""

from __future__ import annotations

import json
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


def _map_cells_to_transactions(
    cells: dict[str, Any],
    account: ResolvedAccount,
    template: dict[str, Any] | None,
) -> ParsedStatement:
    if template is None:
        raise TemplateNotFound(
            f"no layout template for {account.source_id!r}; "
            f"create one at <config_dir>/templates/{account.source_id}.toml"
        )

    cols = template.get("columns") or {}
    opts = template.get("options") or {}
    date_fmt = opts.get("date_format", "%Y-%m-%d")
    sign = opts.get("sign", "natural")

    table = cells.get("table") or {}
    rows = table.get("rows") or []

    if "date" not in cols or "amount" not in cols:
        raise ParseError("template missing required column indices: 'date' and 'amount'")
    date_idx = int(cols["date"])
    amount_idx = int(cols["amount"])
    payee_idx = cols.get("payee")
    memo_idx = cols.get("memo")
    sign_mul = -1 if sign == "invert" else 1

    def _opt(row: list[Any], idx: int | None) -> str | None:
        if idx is None or len(row) <= idx:
            return None
        return str(row[idx]).strip() or None

    transactions: list[RemoteTransaction] = []
    for i, row in enumerate(rows):
        try:
            date_str = datetime.strptime(row[date_idx], date_fmt).date().isoformat()
        except (IndexError, ValueError) as e:
            raise ParseError(f"row {i}: bad date {row[date_idx]!r}: {e}") from e
        amount_str = str(row[amount_idx]).replace(",", "").replace("$", "").strip()
        try:
            amount_minor = round(float(amount_str) * 100) * sign_mul
        except ValueError as e:
            raise ParseError(f"row {i}: bad amount {amount_str!r}: {e}") from e

        payee = _opt(row, payee_idx)
        memo = _opt(row, memo_idx)

        transactions.append(
            RemoteTransaction(
                external_id="",
                account_external_id="account",
                date=date_str,
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
        statement_period_start=cells.get("statement_period_start"),
        statement_period_end=cells.get("statement_period_end"),
        opening_balance_minor=cells.get("opening_balance_minor"),
        closing_balance_minor=cells.get("closing_balance_minor"),
        transactions=tuple(transactions),
        source_format="docling_pdf",
        parser_metadata={"row_count": len(transactions)},
    )


def _extract_cells_with_docling(path: Path) -> dict[str, Any]:
    """Real Docling path. Imports docling lazily."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:
        raise ParseError(
            "docling is required for PDF parsing. "
            "Install with: pip install 'homefinance[ingest]'"
        ) from e

    converter = DocumentConverter()
    result = converter.convert(str(path))
    # TODO(T22): replace ``Any`` with the real Docling ``TableItem`` type once
    # the integration test exercises this path against the live API.
    table: Any = next(iter(result.document.tables or []), None)
    return {
        "statement_period_start": None,
        "statement_period_end": None,
        "opening_balance_minor": None,
        "closing_balance_minor": None,
        "table": {
            "header": [c.text for c in table.header] if table and table.header else [],
            "rows": [[c.text for c in r] for r in (table.rows or [])] if table else [],
        },
    }


class DoclingPDFParser:
    name = "docling_pdf"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        cells = _extract_cells_with_docling(path)
        return _map_cells_to_transactions(cells, account, template)


class FakeDoclingPDFParser:
    """Test double: reads a pre-captured ``cells.json`` and runs the same
    post-Docling mapping logic as the real parser."""

    name = "docling_pdf"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return path.suffix.lower() in {".pdf", ".json"}

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        cells = json.loads(path.read_text())
        return _map_cells_to_transactions(cells, account, template)


register(".pdf", "homefinance.sources.statement.parsers.docling_pdf:DoclingPDFParser")
