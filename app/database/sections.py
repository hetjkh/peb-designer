"""SQLite steel section database (ISMB + simple built-up seed data).

Property values are typical published ISMB table values (mm, cm⁴, cm³, kg/m).
Source reference: Indian Standard rolled-section property tables
(SP 6 / manufacturer ISMB tables). Verify against your approved section book
before use in real design.

Units stored:
  depth, width, tw, tf — mm
  area — cm²
  ix, iy — cm⁴
  zx, zy — cm³
  rx, ry — cm
  mass — kg/m
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from app.paths import app_data_dir, bundled_data_dir

DEFAULT_DB_PATH = app_data_dir() / "sections.db"
BUNDLED_SEED_DB = bundled_data_dir() / "sections.db"


@dataclass(frozen=True)
class SteelSection:
    name: str
    designation_type: str  # ISMB | BUILTUP
    depth_mm: float
    width_mm: float
    tw_mm: float
    tf_mm: float
    area_cm2: float
    ix_cm4: float
    iy_cm4: float
    zx_cm3: float
    zy_cm3: float
    rx_cm: float
    ry_cm: float
    mass_kg_m: float
    source: str = "ISMB published tables / seed data"


# Seed: common ISMB sections (approximate standard table values)
ISMB_SEED: List[SteelSection] = [
    SteelSection("ISMB 150", "ISMB", 150, 80, 4.8, 7.6, 19.0, 718, 46.8, 96.0, 11.7, 6.15, 1.57, 14.9),
    SteelSection("ISMB 175", "ISMB", 175, 90, 5.1, 8.1, 22.1, 1096, 64.2, 125.0, 14.3, 7.04, 1.70, 17.3),
    SteelSection("ISMB 200", "ISMB", 200, 100, 5.4, 8.5, 26.4, 1696, 92.6, 169.0, 18.5, 8.01, 1.87, 20.7),
    SteelSection("ISMB 250", "ISMB", 250, 125, 6.1, 8.2, 38.2, 3820, 160, 306, 25.6, 10.0, 2.05, 30.0),
    SteelSection("ISMB 300", "ISMB", 300, 140, 6.7, 10.6, 48.1, 7333, 289, 489, 41.3, 12.3, 2.45, 37.7),
    SteelSection("ISMB 350", "ISMB", 350, 140, 8.1, 14.2, 66.0, 13630, 365, 779, 52.1, 14.4, 2.35, 51.8),
    SteelSection("ISMB 400", "ISMB", 400, 140, 8.9, 16.0, 78.5, 20460, 422, 1020, 60.2, 16.1, 2.32, 61.6),
    SteelSection("ISMB 450", "ISMB", 450, 150, 9.4, 17.4, 92.3, 30390, 543, 1350, 72.4, 18.2, 2.42, 72.4),
    SteelSection("ISMB 500", "ISMB", 500, 180, 10.2, 17.2, 111.0, 45220, 822, 1810, 91.3, 20.2, 2.72, 86.9),
    SteelSection("ISMB 600", "ISMB", 600, 210, 12.0, 20.8, 156.0, 91810, 1380, 3060, 131, 24.2, 2.97, 123.0),
    # Simple built-up I seed (example PEB-style plates) — illustrative only
    SteelSection("BU 400x200x6x10", "BUILTUP", 400, 200, 6.0, 10.0, 63.6, 17800, 667, 890, 66.7, 16.7, 3.24, 49.9),
    SteelSection("BU 500x250x8x12", "BUILTUP", 500, 250, 8.0, 12.0, 98.2, 40800, 1560, 1630, 125, 20.4, 3.99, 77.1),
    SteelSection("BU 600x300x8x16", "BUILTUP", 600, 300, 8.0, 16.0, 142.0, 86500, 3600, 2880, 240, 24.7, 5.03, 111.0),
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS sections (
    name TEXT PRIMARY KEY,
    designation_type TEXT NOT NULL,
    depth_mm REAL NOT NULL,
    width_mm REAL NOT NULL,
    tw_mm REAL NOT NULL,
    tf_mm REAL NOT NULL,
    area_cm2 REAL NOT NULL,
    ix_cm4 REAL NOT NULL,
    iy_cm4 REAL NOT NULL,
    zx_cm3 REAL NOT NULL,
    zy_cm3 REAL NOT NULL,
    rx_cm REAL NOT NULL,
    ry_cm REAL NOT NULL,
    mass_kg_m REAL NOT NULL,
    source TEXT NOT NULL
);
"""


class SectionDatabase:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._use_bundled_seed = path is None
        self.path = Path(path) if path else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure(self) -> None:
        # Prefer copying a bundled DB if present and user DB missing
        if self._use_bundled_seed and not self.path.exists() and BUNDLED_SEED_DB.exists():
            import shutil

            self.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BUNDLED_SEED_DB, self.path)

        with self._connect() as conn:
            conn.executescript(SCHEMA)
            count = conn.execute("SELECT COUNT(*) AS c FROM sections").fetchone()["c"]
            if count == 0:
                self._insert_many(conn, ISMB_SEED)

    def _insert_many(self, conn: sqlite3.Connection, sections: Iterable[SteelSection]) -> None:
        conn.executemany(
            """
            INSERT OR REPLACE INTO sections (
                name, designation_type, depth_mm, width_mm, tw_mm, tf_mm,
                area_cm2, ix_cm4, iy_cm4, zx_cm3, zy_cm3, rx_cm, ry_cm,
                mass_kg_m, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s.name,
                    s.designation_type,
                    s.depth_mm,
                    s.width_mm,
                    s.tw_mm,
                    s.tf_mm,
                    s.area_cm2,
                    s.ix_cm4,
                    s.iy_cm4,
                    s.zx_cm3,
                    s.zy_cm3,
                    s.rx_cm,
                    s.ry_cm,
                    s.mass_kg_m,
                    s.source,
                )
                for s in sections
            ],
        )

    def get(self, name: str) -> SteelSection:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sections WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Section not found: {name}")
        return self._row_to_section(row)

    def list_sections(self, designation_type: Optional[str] = None) -> List[SteelSection]:
        with self._connect() as conn:
            if designation_type:
                rows = conn.execute(
                    "SELECT * FROM sections WHERE designation_type = ? ORDER BY depth_mm, name",
                    (designation_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sections ORDER BY designation_type, depth_mm, name"
                ).fetchall()
        return [self._row_to_section(r) for r in rows]

    def search(self, query: str) -> List[SteelSection]:
        q = f"%{query.strip()}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sections WHERE name LIKE ? ORDER BY depth_mm",
                (q,),
            ).fetchall()
        return [self._row_to_section(r) for r in rows]

    def delete_by_type(self, designation_type: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM sections WHERE designation_type = ?",
                (designation_type,),
            )
            return int(cur.rowcount or 0)

    def replace_builtup(self, sections: Iterable[SteelSection]) -> int:
        """Replace all BUILTUP rows with the given library."""
        secs = list(sections)
        with self._connect() as conn:
            conn.execute("DELETE FROM sections WHERE designation_type = ?", ("BUILTUP",))
            if secs:
                self._insert_many(conn, secs)
        return len(secs)

    def sync_builtup_from_plate_catalog(self, catalog=None) -> int:
        from app.database.plate_catalog import (
            generate_builtup_library,
            get_plate_catalog,
        )

        catalog = catalog or get_plate_catalog()
        library = generate_builtup_library(catalog)
        return self.replace_builtup(library)

    @staticmethod
    def _row_to_section(row: sqlite3.Row) -> SteelSection:
        return SteelSection(
            name=row["name"],
            designation_type=row["designation_type"],
            depth_mm=row["depth_mm"],
            width_mm=row["width_mm"],
            tw_mm=row["tw_mm"],
            tf_mm=row["tf_mm"],
            area_cm2=row["area_cm2"],
            ix_cm4=row["ix_cm4"],
            iy_cm4=row["iy_cm4"],
            zx_cm3=row["zx_cm3"],
            zy_cm3=row["zy_cm3"],
            rx_cm=row["rx_cm"],
            ry_cm=row["ry_cm"],
            mass_kg_m=row["mass_kg_m"],
            source=row["source"],
        )


def default_section_for_type(member_type: str) -> str:
    """Sensible starter sections by member role (not optimized)."""
    mapping = {
        "column": "ISMB 400",
        "rafter": "ISMB 350",
        "mezzanine_beam": "ISMB 250",
        "mezzanine_column": "ISMB 200",
        "generic": "ISMB 300",
    }
    return mapping.get(member_type, "ISMB 300")
