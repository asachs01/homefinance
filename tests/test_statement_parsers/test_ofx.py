from pathlib import Path

from homefinance.sources.statement.parsers.base import ResolvedAccount
from homefinance.sources.statement.parsers.ofx import OFXParser, QFXParser

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "statement"


def _account() -> ResolvedAccount:
    return ResolvedAccount(
        source_id="statement:test",
        account_id="statement:test:account",
        nickname="test",
        type="checking",
        currency="USD",
    )


def test_ofx_claims_ofx_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.OFX"
    p.write_text("")
    assert OFXParser.claims(p) is True
    assert OFXParser.claims(tmp_path / "x.qfx") is False


def test_qfx_claims_qfx_extension(tmp_path: Path) -> None:
    assert QFXParser.claims(tmp_path / "x.qfx") is True
    assert QFXParser.claims(tmp_path / "x.ofx") is False


def test_parse_tiny_ofx_no_template_needed() -> None:
    parsed = OFXParser.parse(FIX / "tiny.ofx", _account(), template=None)
    assert parsed.source_format == "ofx"
    assert len(parsed.transactions) == 2
    first = parsed.transactions[0]
    assert first.date == "2026-06-01"
    assert first.amount_minor == -4567
    assert first.payee == "Trader Joe's"
    assert first.memo == "weekly shop"


def test_parse_qfx_same_as_ofx() -> None:
    parsed = QFXParser.parse(FIX / "tiny.qfx", _account(), template=None)
    assert parsed.source_format == "qfx"
    assert len(parsed.transactions) == 2
