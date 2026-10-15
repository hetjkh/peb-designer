"""Resolve resource paths for development and frozen (PyInstaller) builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Root that contains the `app` package / bundled resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    """Writable per-user data directory (sections DB, exports cache)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / "PEBDesigner"
    else:
        path = Path.home() / ".peb-designer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_data_dir() -> Path:
    return package_root() / "data"
