"""Load-bearing test for SP2's C-10 constraint (lean install stays lean).

If a future top-level ``import docling`` ever sneaks into a parser module,
this test fails — forcing the import to move inside the method that needs it.
"""

import subprocess
import sys


def test_homefinance_does_not_import_docling_at_package_import_time() -> None:
    code = (
        "import sys, homefinance, homefinance.sources.statement, "
        "homefinance.sources.statement.parsers; "
        "leaks = [m for m in sys.modules "
        "         if m == 'docling' or m.startswith('docling.')]; "
        "assert leaks == [], f'Docling leaked: {leaks}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_homefinance_does_not_import_ofxtools_at_package_import_time() -> None:
    code = (
        "import sys, homefinance, homefinance.sources.statement, "
        "homefinance.sources.statement.parsers; "
        "leaks = [m for m in sys.modules "
        "         if m == 'ofxtools' or m.startswith('ofxtools.')]; "
        "assert leaks == [], f'ofxtools leaked: {leaks}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
