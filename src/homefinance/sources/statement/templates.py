"""Per-account parser templates.

Templates live at ``<config_dir>/templates/<source_id>.toml``. ``config_dir``
is normally the resolved Config.config_path.parent (i.e. ``~/.homefinance/``
or its XDG equivalent). The ingest orchestrator passes the directory in;
this module does not call ``load_config()`` itself so tests stay hermetic.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def templates_dir(config_dir: Path) -> Path:
    return Path(config_dir) / "templates"


def load_template(source_id: str, *, config_dir: Path) -> dict[str, Any] | None:
    """Load the TOML template for the given source_id, or None if absent."""
    path = templates_dir(config_dir) / f"{source_id}.toml"
    if not path.exists():
        return None
    return tomllib.loads(path.read_text())
