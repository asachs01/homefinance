"""OFX + QFX parser via ``ofxtools`` (lazy import; gated to [ingest] extra)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homefinance.sources.base import RemoteTransaction
from homefinance.sources.statement.parsers import register
from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ParseError,
    ResolvedAccount,
)


def _parse_with_ofxtools(path: Path, account: ResolvedAccount, format_name: str) -> ParsedStatement:
    # Lazy import so the lean install never touches ofxtools.
    try:
        from ofxtools.Parser import OFXTree
    except ImportError as e:
        raise ParseError(
            "ofxtools is required for OFX/QFX parsing. "
            "Install with: pip install 'homefinance[ingest]'"
        ) from e

    tree = OFXTree()
    try:
        tree.parse(str(path))
    except Exception as e:
        raise ParseError(f"could not parse {path} as {format_name}: {e}") from e
    ofx = tree.convert()

    statements = list(ofx.statements)
    if not statements:
        raise ParseError(f"no statement found in {path}")
    stmt = statements[0]

    txns: list[RemoteTransaction] = []
    for raw in stmt.transactions or []:
        amount = raw.trnamt
        amount_minor = round(float(amount) * 100)
        date_str = raw.dtposted.date().isoformat() if raw.dtposted else ""
        payee = (raw.name or "").strip() or None
        memo = (raw.memo or "").strip() or None
        if not date_str:
            raise ParseError(f"transaction missing date in {path}")
        txns.append(
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
                import_id=str(raw.fitid) if raw.fitid else None,
                transfer_account_external_id=None,
                deleted=False,
            )
        )

    ledger_bal = getattr(stmt, "ledgerbal", None)
    closing = round(float(ledger_bal.balamt) * 100) if ledger_bal is not None else None

    period_start = (
        stmt.transactions.dtstart.date().isoformat()
        if stmt.transactions and stmt.transactions.dtstart
        else None
    )
    period_end = (
        stmt.transactions.dtend.date().isoformat()
        if stmt.transactions and stmt.transactions.dtend
        else None
    )

    return ParsedStatement(
        statement_period_start=period_start,
        statement_period_end=period_end,
        opening_balance_minor=None,
        closing_balance_minor=closing,
        transactions=tuple(txns),
        source_format=format_name,
        parser_metadata={"row_count": len(txns)},
    )


class OFXParser:
    name = "ofx"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".ofx"

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        return _parse_with_ofxtools(Path(path), account, cls.name)


class QFXParser:
    name = "qfx"

    @classmethod
    def claims(cls, path: Path) -> bool:
        return Path(path).suffix.lower() == ".qfx"

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        return _parse_with_ofxtools(Path(path), account, cls.name)


register(".ofx", "homefinance.sources.statement.parsers.ofx:OFXParser")
register(".qfx", "homefinance.sources.statement.parsers.ofx:QFXParser")
