"""Application preferences (defaults for new projects).

Persisted as JSON under the user data directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import List, Optional

from app.core.models import SupportType
from app.paths import app_data_dir

PREFERENCES_FILENAME = "preferences.json"

DESIGN_CODES: List[str] = [
    "IS800-2007-LSD",
    "IS800-2007-WSD",
    "ASCE7-2016-LRFD-LL<=4.79kN/m2",
    "ASCE7-2016-LRFD-LL>4.79kN/m2",
    "ASCE7-2016-ASD",
    "ASCE7-2010-LRFD-LL<=4.79kN/m2",
    "ASCE7-2010-LRFD-LL>4.79kN/m2",
    "ASCE7-2010-ASD",
]

STAAD_VERSIONS: List[str] = [
    "STAAD.Pro CONNECT Edition",
    "STAAD.Pro V8i",
    "STAAD.Pro 2023",
    "STAAD.Pro 2024",
]


@dataclass
class AppPreferences:
    """Defaults applied when clearing / starting a new project."""

    design_code: str = "IS800-2007-LSD"
    roof_dead_kn_m2: float = 0.3
    roof_collateral_kn_m2: float = 0.15
    staad_version: str = "STAAD.Pro CONNECT Edition"
    purlin_spacing_m: float = 1.5
    girt_spacing_m: float = 1.5
    ext_col_base: str = "auto"  # auto | pinned | fixed
    ui_theme: str = "light"  # light | dark
    # Optional embedded plate catalog when "use as default for new projects"
    plate_catalog: Optional[dict] = None

    def support_type(self) -> SupportType:
        base = str(self.ext_col_base).lower()
        if base.startswith("fix"):
            return SupportType.FIXED
        if base.startswith("auto"):
            # Default recommendation without project dimensions: pinned
            return SupportType.PINNED
        return SupportType.PINNED

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppPreferences":
        known = {f.name for f in fields(cls)}
        cleaned = {k: v for k, v in (data or {}).items() if k in known}
        prefs = cls(**cleaned)
        if prefs.design_code not in DESIGN_CODES:
            prefs.design_code = DESIGN_CODES[0]
        if prefs.staad_version not in STAAD_VERSIONS:
            # Keep custom string if user edited; otherwise fall back
            if not prefs.staad_version:
                prefs.staad_version = STAAD_VERSIONS[0]
        base = str(prefs.ext_col_base).lower()
        if base.startswith("fix"):
            prefs.ext_col_base = "fixed"
        elif base.startswith("auto"):
            prefs.ext_col_base = "auto"
        else:
            prefs.ext_col_base = "pinned"
        theme = str(prefs.ui_theme or "light").lower()
        prefs.ui_theme = "dark" if theme.startswith("dark") else "light"
        return prefs


def preferences_path() -> Path:
    return app_data_dir() / PREFERENCES_FILENAME


def load_preferences(path: Optional[Path] = None) -> AppPreferences:
    file_path = path or preferences_path()
    if not file_path.exists():
        return AppPreferences()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return AppPreferences.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return AppPreferences()


def save_preferences(prefs: AppPreferences, path: Optional[Path] = None) -> Path:
    file_path = path or preferences_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(prefs.to_dict(), indent=2),
        encoding="utf-8",
    )
    return file_path


# Process-wide cache used by GUI / pipeline
_current: Optional[AppPreferences] = None


def get_preferences() -> AppPreferences:
    global _current
    if _current is None:
        _current = load_preferences()
    return _current


def set_preferences(prefs: AppPreferences, *, persist: bool = True) -> AppPreferences:
    global _current
    _current = prefs
    if persist:
        save_preferences(prefs)
    return _current
