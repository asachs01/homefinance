"""Shared pytest fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tiny_fixtures_dir() -> Path:
    return FIXTURES / "ynab" / "tiny"
