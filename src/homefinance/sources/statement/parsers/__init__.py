"""Parser registry and dispatch.

Each parser registers itself by appending a ``(extension, dotted_path)``
tuple to ``_REGISTRY``. ``find_parser()`` walks the registry, importing the
target module lazily — the lean install (``pip install homefinance``) never
transitively loads ``docling`` or ``ofxtools``.

Dotted path format: ``module.path:ClassName`` (matches Python entry-point
conventions).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import cast

from homefinance.sources.statement.parsers.base import (
    NoSuitableParser,
    StatementParser,
)

# Populated by each parser module via ``register(extension, dotted_path)``
# in subsequent tasks. Tests may monkeypatch this list.
_REGISTRY: list[tuple[str, str]] = []


def register(extension: str, dotted_path: str) -> None:
    """Register a parser for files with the given extension.

    Idempotent: re-registering the same (extension, path) pair is a no-op
    so re-imports during testing don't double-register.
    """
    pair = (extension.lower(), dotted_path)
    if pair not in _REGISTRY:
        _REGISTRY.append(pair)


def find_parser(path: Path) -> type[StatementParser]:
    """Return the parser class that claims this file, or raise NoSuitableParser."""
    ext = Path(path).suffix.lower()
    for parser_ext, dotted in _REGISTRY:
        if ext != parser_ext:
            continue
        module_name, _, cls_name = dotted.partition(":")
        module = importlib.import_module(module_name)
        cls = cast(type[StatementParser], getattr(module, cls_name))
        if cls.claims(Path(path)):
            return cls
    raise NoSuitableParser(
        f"no parser knows {str(path)!r} (saw extension {ext!r}). "
        "Supported: csv, ofx, qfx, pdf."
    )
