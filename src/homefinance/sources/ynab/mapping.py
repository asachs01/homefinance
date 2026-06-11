"""YNAB → canonical mapping. Pure functions; no I/O.

This is the only place in the codebase that converts YNAB's wire format
(milliunits) to our canonical minor units (cents). Floats never enter the store.
"""

from __future__ import annotations


def to_minor_units(milliunits: int) -> int:
    """Convert signed YNAB milliunits to signed minor units (cents).

    Raises ``ValueError`` if the input is not a multiple of 10 — real YNAB
    transactions are always whole cents, so sub-cent values indicate either
    a bug upstream or a corner case we want to surface loudly rather than
    silently round.
    """
    if milliunits % 10 != 0:
        raise ValueError(f"non-cent milliunit value: {milliunits}")
    return milliunits // 10
