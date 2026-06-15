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

# Column indices to preserve verbatim; all others are replaced with placeholders.
# Matches the default docling_pdf template's columns (date, amount).
KEEP_COLUMNS = (0, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        from homefinance.sources.statement.parsers.docling_pdf import (
            _extract_cells_with_docling,
        )
    except ImportError:
        print(
            "error: docling is required. Install with: pip install 'homefinance[ingest]'",
            file=sys.stderr,
        )
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    cells = _extract_cells_with_docling(args.pdf)

    # Scrub on top of the extractor's output so the script can't drift from
    # the parser's actual cells.json contract.
    rows = cells["table"]["rows"]
    cells["table"]["rows"] = [
        [cell if i in KEEP_COLUMNS else f"[scrubbed col {i}]" for i, cell in enumerate(row)]
        for row in rows
    ]

    out_file = args.out / "cells.json"
    out_file.write_text(json.dumps(cells, indent=2, sort_keys=True))
    print(f"wrote {out_file}")
    print("\nREVIEW the output before committing — automated scrubbing is rough.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
