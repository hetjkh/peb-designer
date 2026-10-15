"""Plate-size catalog for built-up I sections (PEB-style).

Sections are assembled only from stocked plate sizes (mm).
Limits (documented UI constraints):
  depth (overall) ≤ 2000 mm
  web thickness ≤ 40 mm
  flange width ≤ 750 mm
  flange thickness ≤ 40 mm

Web depth in the catalog is the *clear* web depth between flanges.
Overall depth D = d_clear + 2·tf.

Property formulas: standard I-section geometry (mm), converted to
cm² / cm⁴ / cm³ / cm / kg/m for the section database.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from itertools import product
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from app.database.sections import SteelSection
from app.paths import app_data_dir

PLATE_CATALOG_FILENAME = "plate_catalog.json"

MAX_OVERALL_DEPTH_MM = 2000.0
MAX_WEB_THICKNESS_MM = 40.0
MAX_FLANGE_WIDTH_MM = 750.0
MAX_FLANGE_THICKNESS_MM = 40.0

DEFAULT_WEB_DEPTHS = [
    250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900,
    950, 1000, 1050, 1100, 1150, 1200, 1250, 1300, 1350, 1400, 1450, 1500,
]
DEFAULT_WEB_THICKNESSES = [4, 5, 6, 7, 8, 9, 10, 12, 15, 16]
DEFAULT_FLANGE_WIDTHS = [
    125, 150, 175, 200, 225, 250, 275, 300, 325, 350, 375, 400, 425, 450, 500,
]
DEFAULT_FLANGE_THICKNESSES = [5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 35, 40]


@dataclass
class PlateCatalog:
    """Stocked plate sizes used to build built-up sections."""

    web_depths_mm: List[float] = field(
        default_factory=lambda: list(DEFAULT_WEB_DEPTHS)
    )
    web_thicknesses_mm: List[float] = field(
        default_factory=lambda: list(DEFAULT_WEB_THICKNESSES)
    )
    flange_widths_mm: List[float] = field(
        default_factory=lambda: list(DEFAULT_FLANGE_WIDTHS)
    )
    flange_thicknesses_mm: List[float] = field(
        default_factory=lambda: list(DEFAULT_FLANGE_THICKNESSES)
    )
    use_as_project_default: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PlateCatalog":
        data = data or {}
        return cls(
            web_depths_mm=_clean_list(data.get("web_depths_mm"), DEFAULT_WEB_DEPTHS),
            web_thicknesses_mm=_clean_list(
                data.get("web_thicknesses_mm"), DEFAULT_WEB_THICKNESSES
            ),
            flange_widths_mm=_clean_list(
                data.get("flange_widths_mm"), DEFAULT_FLANGE_WIDTHS
            ),
            flange_thicknesses_mm=_clean_list(
                data.get("flange_thicknesses_mm"), DEFAULT_FLANGE_THICKNESSES
            ),
            use_as_project_default=bool(data.get("use_as_project_default", True)),
        )

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.web_depths_mm:
            errors.append("Web depths list is empty.")
        if not self.web_thicknesses_mm:
            errors.append("Web thicknesses list is empty.")
        if not self.flange_widths_mm:
            errors.append("Flange widths list is empty.")
        if not self.flange_thicknesses_mm:
            errors.append("Flange thicknesses list is empty.")

        if any(d <= 0 or d > MAX_OVERALL_DEPTH_MM for d in self.web_depths_mm):
            errors.append(
                f"Web depths must be between 0 and {MAX_OVERALL_DEPTH_MM:g} mm "
                "(clear depth; overall depth also limited to this)."
            )
        if any(t <= 0 or t > MAX_WEB_THICKNESS_MM for t in self.web_thicknesses_mm):
            errors.append(f"Web thicknesses must be ≤ {MAX_WEB_THICKNESS_MM:g} mm.")
        if any(w <= 0 or w > MAX_FLANGE_WIDTH_MM for w in self.flange_widths_mm):
            errors.append(f"Flange widths must be ≤ {MAX_FLANGE_WIDTH_MM:g} mm.")
        if any(t <= 0 or t > MAX_FLANGE_THICKNESS_MM for t in self.flange_thicknesses_mm):
            errors.append(
                f"Flange thicknesses must be ≤ {MAX_FLANGE_THICKNESS_MM:g} mm."
            )
        return errors


def _clean_list(values, fallback: Sequence[float]) -> List[float]:
    if not values:
        return list(fallback)
    out: List[float] = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            out.append(f)
    return sorted(set(out)) or list(fallback)


def parse_mm_list(text: str, *, field_name: str) -> List[float]:
    """Parse comma-separated mm values."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required.")
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    values: List[float] = []
    for part in parts:
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError as exc:
            raise ValueError(
                f"{field_name}: invalid number '{part}'."
            ) from exc
    if not values:
        raise ValueError(f"{field_name} produced no values.")
    return sorted(set(values))


def format_mm_list(values: Sequence[float]) -> str:
    return ", ".join(
        str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}" for v in values
    )


def plate_catalog_path() -> Path:
    return app_data_dir() / PLATE_CATALOG_FILENAME


def load_plate_catalog(path: Optional[Path] = None) -> PlateCatalog:
    file_path = path or plate_catalog_path()
    if not file_path.exists():
        return PlateCatalog()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return PlateCatalog.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return PlateCatalog()


def save_plate_catalog(catalog: PlateCatalog, path: Optional[Path] = None) -> Path:
    file_path = path or plate_catalog_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(catalog.to_dict(), indent=2), encoding="utf-8")
    return file_path


_current_catalog: Optional[PlateCatalog] = None


def get_plate_catalog() -> PlateCatalog:
    global _current_catalog
    if _current_catalog is None:
        _current_catalog = load_plate_catalog()
    return _current_catalog


def set_plate_catalog(catalog: PlateCatalog, *, persist: bool = True) -> PlateCatalog:
    global _current_catalog
    _current_catalog = catalog
    if persist:
        save_plate_catalog(catalog)
    return _current_catalog


def builtup_properties(
    d_clear_mm: float,
    tw_mm: float,
    bf_mm: float,
    tf_mm: float,
) -> SteelSection:
    """Compute I-section properties from clear web depth and plate sizes."""
    hw = d_clear_mm
    D = hw + 2.0 * tf_mm
    if D > MAX_OVERALL_DEPTH_MM + 1e-9:
        raise ValueError(
            f"Overall depth {D:g} mm exceeds limit {MAX_OVERALL_DEPTH_MM:g} mm."
        )
    if tw_mm > MAX_WEB_THICKNESS_MM or bf_mm > MAX_FLANGE_WIDTH_MM or tf_mm > MAX_FLANGE_THICKNESS_MM:
        raise ValueError("Plate size exceeds catalog limits.")

    # Areas mm²
    a_web = hw * tw_mm
    a_fl = bf_mm * tf_mm
    A = a_web + 2.0 * a_fl

    # Ix about major axis (mm⁴)
    ix_web = tw_mm * hw**3 / 12.0
    y_fl = hw / 2.0 + tf_mm / 2.0
    ix_fl = (bf_mm * tf_mm**3) / 12.0 + a_fl * y_fl**2
    Ix = ix_web + 2.0 * ix_fl

    # Iy about minor axis (mm⁴)
    iy_web = hw * tw_mm**3 / 12.0
    iy_fl = (tf_mm * bf_mm**3) / 12.0
    Iy = iy_web + 2.0 * iy_fl

    Zx = Ix / (D / 2.0) if D > 0 else 0.0
    Zy = Iy / (bf_mm / 2.0) if bf_mm > 0 else 0.0
    rx = math.sqrt(Ix / A) if A > 0 else 0.0
    ry = math.sqrt(Iy / A) if A > 0 else 0.0
    mass = A * 0.00785  # kg/m

    name = f"BU {int(round(D))}x{int(round(bf_mm))}x{int(round(tw_mm))}x{int(round(tf_mm))}"
    return SteelSection(
        name=name,
        designation_type="BUILTUP",
        depth_mm=D,
        width_mm=bf_mm,
        tw_mm=tw_mm,
        tf_mm=tf_mm,
        area_cm2=A / 100.0,
        ix_cm4=Ix / 1.0e4,
        iy_cm4=Iy / 1.0e4,
        zx_cm3=Zx / 1.0e3,
        zy_cm3=Zy / 1.0e3,
        rx_cm=rx / 10.0,
        ry_cm=ry / 10.0,
        mass_kg_m=mass,
        source="Built from plate catalog (clear web depth)",
    )


def generate_builtup_library(
    catalog: PlateCatalog,
    *,
    max_sections: int = 450,
) -> List[SteelSection]:
    """Build a practical library of BU sections from stocked plates.

    Full cartesian product is huge; we keep flange widths near 0.35D–0.65D
    and sample thicknesses to stay under max_sections.
    """
    errors = catalog.validate()
    if errors:
        raise ValueError("; ".join(errors))

    tws = list(catalog.web_thicknesses_mm)
    tfs = list(catalog.flange_thicknesses_mm)
    # Sample if lists are large
    if len(tws) > 6:
        tws = tws[::2]
    if len(tfs) > 8:
        tfs = tfs[::2]

    sections: List[SteelSection] = []
    seen = set()
    for d_clear, tw, tf, bf in product(
        catalog.web_depths_mm, tws, tfs, catalog.flange_widths_mm
    ):
        D = d_clear + 2.0 * tf
        if D > MAX_OVERALL_DEPTH_MM:
            continue
        if not (0.35 * D <= bf <= 0.65 * D):
            continue
        try:
            sec = builtup_properties(d_clear, tw, bf, tf)
        except ValueError:
            continue
        if sec.name in seen:
            continue
        seen.add(sec.name)
        sections.append(sec)
        if len(sections) >= max_sections:
            break

    sections.sort(key=lambda s: (s.depth_mm, s.width_mm, s.tw_mm, s.tf_mm))
    return sections
