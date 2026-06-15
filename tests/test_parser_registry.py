import sys
from pathlib import Path

import pytest

from homefinance.sources.statement.parsers import (
    _REGISTRY,
    find_parser,
)
from homefinance.sources.statement.parsers.base import NoSuitableParser


def test_find_parser_raises_when_registry_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "homefinance.sources.statement.parsers._REGISTRY",
        [],
    )
    p = tmp_path / "x.csv"
    p.write_text("")
    with pytest.raises(NoSuitableParser, match="no parser"):
        find_parser(p)


def test_find_parser_dispatches_by_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Stand up a stub parser module on the fly.
    stub = type(sys)("_test_stub_parser")

    class StubParser:
        name = "stub"

        @classmethod
        def claims(cls, path: Path) -> bool:
            return path.suffix == ".stub"

        @classmethod
        def parse(cls, path, account, template):  # pragma: no cover
            ...

    stub.StubParser = StubParser
    monkeypatch.setitem(sys.modules, "_test_stub_parser", stub)
    monkeypatch.setattr(
        "homefinance.sources.statement.parsers._REGISTRY",
        [(".stub", "_test_stub_parser:StubParser")],
    )

    p = tmp_path / "f.stub"
    p.write_text("")
    parser_cls = find_parser(p)
    assert parser_cls is StubParser


def test_registry_contains_csv_after_csv_module_imported() -> None:
    # Once Task 7's CSV parser module is imported, it registers itself.
    import homefinance.sources.statement.parsers.csv  # noqa: F401

    assert (".csv", "homefinance.sources.statement.parsers.csv:CSVParser") in _REGISTRY
