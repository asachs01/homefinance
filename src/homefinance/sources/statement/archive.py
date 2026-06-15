"""Copy source files into the local archive.

Default layout: ``<archive_dir>/<source_id>/<file_hash><original_ext>``.
The destination directory is created with mode 0o700 (consistent with the
0o700 stance the SP1 config-write helper takes). Any failure raises
``ArchiveFailed`` **before** the ingest orchestrator touches the DB.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from homefinance.sources.statement.parsers.base import ArchiveFailed


def archive_file(
    source: Path, *, source_id: str, file_hash: str, archive_dir: Path
) -> Path:
    source = Path(source)
    if not source.exists():
        raise ArchiveFailed(f"source file not found: {source}")

    dest_dir = Path(archive_dir) / source_id
    try:
        dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # ``mkdir(mode=...)`` honors umask; force-tighten after creation.
        os.chmod(dest_dir, 0o700)
    except OSError as e:
        raise ArchiveFailed(f"could not create archive dir {dest_dir}: {e}") from e

    dest = dest_dir / f"{file_hash}{source.suffix}"
    try:
        shutil.copy2(source, dest)
    except OSError as e:
        raise ArchiveFailed(f"could not copy {source} to {dest}: {e}") from e

    return dest
