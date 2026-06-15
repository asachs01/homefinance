"""Record sanitized Docling output for use as test fixtures.

Usage:
    python scripts/record_docling_fixtures.py --pdf /path/to/statement.pdf \
        --out tests/fixtures/docling/<name>/

Writes a single ``cells.json`` shaped like the fake parser expects. Sanitizes
identifiers (amounts kept; names/memos replaced with placeholders) — the
maintainer should still review the output before committing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except ImportError:
        print(
            "error: docling is required. Install with: pip install 'homefinance[ingest]'",
            file=sys.stderr,
        )
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    result = converter.convert(str(args.pdf))

    table = next(iter(result.document.tables or []), None)
    cells = {
        "statement_period_start": None,
        "statement_period_end": None,
        "opening_balance_minor": None,
        "closing_balance_minor": None,
        "table": {
            "header": [c.text for c in (table.header or [])] if table else [],
            "rows": [
                [f"[scrubbed col {i}]" if i not in (0, 2) else c.text for i, c in enumerate(r)]
                for r in (table.rows or [])
            ]
            if table
            else [],
        },
    }

    out_file = args.out / "cells.json"
    out_file.write_text(json.dumps(cells, indent=2, sort_keys=True))
    print(f"wrote {out_file}")
    print("\nREVIEW the output before committing — automated scrubbing is rough.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
