from pathlib import Path

import pytest

from homefinance.sources.statement.parsers.base import (
    ParseError,
    ResolvedAccount,
    TemplateNotFound,
)
from homefinance.sources.statement.parsers.csv import CSVParser

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "statement"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:citi-cc",
        account_id="statement:citi-cc:account",
        nickname="citi-cc",
        type="credit_card",
        currency="USD",
    )


def _natural_template() -> dict:
    return {
        "parser": "csv",
        "columns": {
            "date": "Transaction Date",
            "amount": "Amount",
            "payee": "Description",
            "memo": "Notes",
        },
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }


def test_claims_csv_by_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.CSV"
    p.write_text("")
    assert CSVParser.claims(p) is True
    assert CSVParser.claims(tmp_path / "x.pdf") is False


def test_parse_tiny_csv_with_template() -> None:
    parsed = CSVParser.parse(FIX / "tiny.csv", _account(), _natural_template())
    assert parsed.source_format == "csv"
    assert len(parsed.transactions) == 3
    first = parsed.transactions[0]
    assert first.date == "2026-06-01"
    assert first.amount_minor == -4567
    assert first.payee == "Trader Joe's"
    assert first.memo == "weekly shop"
    # Whitespace stripped on payee:
    assert parsed.transactions[2].payee == "Payment"


def test_parse_without_template_raises() -> None:
    with pytest.raises(TemplateNotFound):
        CSVParser.parse(FIX / "tiny.csv", _account(), None)


def test_parse_missing_required_column_raises() -> None:
    template = _natural_template()
    template["columns"]["amount"] = "DoesNotExist"
    with pytest.raises(ParseError, match=r"column.*DoesNotExist"):
        CSVParser.parse(FIX / "tiny.csv", _account(), template)


def test_sign_invert_flips_amounts() -> None:
    template = _natural_template()
    template["options"]["sign"] = "invert"
    parsed = CSVParser.parse(FIX / "tiny.csv", _account(), template)
    # Originally -45.67 -> +45.67 after invert.
    assert parsed.transactions[0].amount_minor == 4567
