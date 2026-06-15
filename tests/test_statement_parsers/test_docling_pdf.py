import json
import sys
from pathlib import Path

import pytest

from homefinance.sources.statement.parsers.base import (
    ParsedStatement,
    ResolvedAccount,
    TemplateNotFound,
)
from homefinance.sources.statement.parsers.docling_pdf import (
    DoclingPDFParser,
    FakeDoclingPDFParser,
    _map_cells_to_transactions,
)

CELLS = Path(__file__).resolve().parent.parent / "fixtures" / "docling" / "tiny-pdf" / "cells.json"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:wells",
        account_id="statement:wells:account",
        nickname="wells",
        type="checking",
        currency="USD",
    )


def _template() -> dict:
    return {
        "parser": "docling_pdf",
        "table": {"header_match": ["Date", "Description", "Amount"]},
        "columns": {"date": 0, "payee": 1, "amount": 2},
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }


def test_claims_pdf_by_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.PDF"
    p.write_bytes(b"%PDF-1.4")
    assert DoclingPDFParser.claims(p) is True
    assert DoclingPDFParser.claims(tmp_path / "x.csv") is False


def test_map_cells_produces_transactions() -> None:
    cells = json.loads(CELLS.read_text())
    parsed = _map_cells_to_transactions(cells, _account(), _template())
    assert isinstance(parsed, ParsedStatement)
    assert parsed.source_format == "docling_pdf"
    assert len(parsed.transactions) == 3
    assert parsed.transactions[0].date == "2026-06-01"
    assert parsed.transactions[0].amount_minor == -4567
    assert parsed.opening_balance_minor == 1234560
    assert parsed.closing_balance_minor == 1100000


def test_map_cells_without_template_raises() -> None:
    cells = json.loads(CELLS.read_text())
    with pytest.raises(TemplateNotFound):
        _map_cells_to_transactions(cells, _account(), None)


def test_fake_parser_reads_json_fixture() -> None:
    parsed = FakeDoclingPDFParser.parse(CELLS, _account(), _template())
    assert len(parsed.transactions) == 3
    assert parsed.transactions[1].payee == "Shell"


def test_docling_pdf_module_does_not_import_docling_at_import_time() -> None:
    # Reload the module to test fresh
    mod = "homefinance.sources.statement.parsers.docling_pdf"
    if mod in sys.modules:
        del sys.modules[mod]

    def _docling_pkg_modules() -> set[str]:
        # Match the docling package proper, not our own ``docling_pdf`` module.
        return {m for m in sys.modules if m == "docling" or m.startswith("docling.")}

    leaks_before = _docling_pkg_modules()
    import homefinance.sources.statement.parsers.docling_pdf  # noqa: F401
    leaks_after = _docling_pkg_modules()
    assert leaks_after - leaks_before == set(), \
        f"importing docling_pdf eagerly loaded docling: {leaks_after - leaks_before}"
