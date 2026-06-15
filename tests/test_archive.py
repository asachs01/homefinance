import os
import stat
from pathlib import Path

import pytest

from homefinance.sources.statement.archive import archive_file
from homefinance.sources.statement.parsers.base import ArchiveFailed


def test_archive_file_copies_into_hash_named_path(tmp_path: Path) -> None:
    src = tmp_path / "statement.csv"
    src.write_text("some content")
    archive_root = tmp_path / "archive"

    dst = archive_file(
        src,
        source_id="statement:citi-cc",
        file_hash="abc123",
        archive_dir=archive_root,
    )
    assert dst == archive_root / "statement:citi-cc" / "abc123.csv"
    assert dst.exists()
    assert dst.read_text() == "some content"


def test_archive_file_creates_parent_dir_with_0o700(tmp_path: Path) -> None:
    src = tmp_path / "x.csv"
    src.write_text("hello")
    archive_root = tmp_path / "archive"

    dst = archive_file(
        src,
        source_id="statement:citi-cc",
        file_hash="abc",
        archive_dir=archive_root,
    )
    parent_mode = stat.S_IMODE(os.stat(dst.parent).st_mode)
    assert parent_mode == 0o700


def test_archive_file_raises_on_missing_source(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    with pytest.raises(ArchiveFailed):
        archive_file(
            tmp_path / "missing.csv",
            source_id="statement:s",
            file_hash="h",
            archive_dir=archive_root,
        )


def test_archive_file_preserves_original_extension(tmp_path: Path) -> None:
    pdf = tmp_path / "statement.PDF"  # uppercase
    pdf.write_bytes(b"%PDF-1.4 ...")
    dst = archive_file(
        pdf,
        source_id="statement:wells",
        file_hash="h",
        archive_dir=tmp_path / "archive",
    )
    assert dst.suffix == ".PDF"  # preserve case
