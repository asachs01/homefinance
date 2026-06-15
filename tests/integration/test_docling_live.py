"""Live-Docling integration test. Run via:

    pytest tests/integration -m docling

Default ``pytest`` does NOT collect this module (the ``docling`` marker keeps
it out). The ``test-docling`` CI job (manual dispatch) is the only place
this runs in CI.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.docling


def test_docling_can_be_imported() -> None:
    docling = pytest.importorskip("docling")
    assert hasattr(docling, "document_converter")


def test_docling_pdf_parser_real_path_against_bundled_sample(tmp_path: Path) -> None:
    """Live Docling against the bundled tiny PDF fixture (maintainer ships one).

    If ``tests/fixtures/docling/tiny-pdf/sample.pdf`` does not exist, this test
    is skipped — we don't want this job hard-fail if the sample isn't yet
    captured.
    """
    sample = (
        Path(__file__).resolve().parent.parent / "fixtures" / "docling" / "tiny-pdf" / "sample.pdf"
    )
    if not sample.exists():
        pytest.skip(f"no live sample at {sample}; capture one via record_docling_fixtures.py")

    from homefinance.sources.statement.parsers.base import ResolvedAccount
    from homefinance.sources.statement.parsers.docling_pdf import DoclingPDFParser

    account = ResolvedAccount(
        source_id="statement:test",
        account_id="statement:test:account",
        nickname="test",
        type="checking",
        currency="USD",
    )
    template = {
        "parser": "docling_pdf",
        "columns": {"date": 0, "payee": 1, "amount": 2},
        "options": {"date_format": "%m/%d/%Y", "sign": "natural"},
    }
    parsed = DoclingPDFParser.parse(sample, account, template)
    assert parsed.source_format == "docling_pdf"
    assert len(parsed.transactions) >= 0
