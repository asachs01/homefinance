"""``StatementParser`` Protocol + ``ParsedStatement`` dataclass + exception classes.

Pure interface layer. No I/O. Mirrors how SP1's ``sources/base.py`` staged
the ``AccountSource`` seam before any concrete implementations landed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from homefinance.sources.base import RemoteTransaction

# ---------------------------------------------------------------------------
# Exceptions — each has a stable ``code`` so MCP callers can branch on it.


class StatementIngestError(Exception):
    """Base class for any ingest-side failure. Carries a stable ``code``."""

    code: str = "statement_ingest_error"


class AccountNotConfigured(StatementIngestError):
    code = "account_not_configured"


class NoSuitableParser(StatementIngestError):
    code = "no_suitable_parser"


class TemplateNotFound(StatementIngestError):
    code = "template_not_found"


class ParseError(StatementIngestError):
    code = "parse_error"


class ArchiveFailed(StatementIngestError):
    code = "archive_failed"


class FileAlreadyIngested(StatementIngestError):
    code = "file_already_ingested"


# ---------------------------------------------------------------------------
# Data shapes


@dataclass(frozen=True, slots=True)
class ResolvedAccount:
    """Snapshot of the canonical account a statement is being ingested for."""

    source_id: str  # e.g. "statement:citi-cc"
    account_id: str  # e.g. "statement:citi-cc:account"
    nickname: str
    type: str  # canonical: checking | savings | credit_card | ...
    currency: str


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    """Everything a parser produced from one file."""

    statement_period_start: str | None  # YYYY-MM-DD
    statement_period_end: str | None
    opening_balance_minor: int | None
    closing_balance_minor: int | None
    transactions: tuple[RemoteTransaction, ...]
    source_format: str  # parser.name (e.g. "csv", "docling_pdf")
    parser_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol


@runtime_checkable
class StatementParser(Protocol):
    """A file-format-specific parser. Lazy-imported by the registry."""

    name: str  # 'csv' | 'ofx' | 'qfx' | 'docling_pdf'

    @classmethod
    def claims(cls, path: Path) -> bool:
        """True if this parser thinks it can handle this file (extension +
        light magic-byte sniffing). MUST NOT do expensive parsing here."""
        ...

    @classmethod
    def parse(
        cls,
        path: Path,
        account: ResolvedAccount,
        template: dict[str, Any] | None,
    ) -> ParsedStatement:
        """Parse the file. Raises ``ParseError``, ``TemplateNotFound``, etc."""
        ...
