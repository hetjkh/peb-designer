"""Tests for section database and materials."""

from app.database.materials import get_material, list_materials
from app.database.sections import SectionDatabase


def test_materials_seed() -> None:
    mats = list_materials()
    assert len(mats) >= 3
    e350 = get_material("E350")
    assert e350.fy_mpa == 350


def test_section_db_seed(tmp_path) -> None:
    db = SectionDatabase(tmp_path / "sections.db")
    secs = db.list_sections()
    assert len(secs) >= 10
    ismb400 = db.get("ISMB 400")
    assert ismb400.depth_mm == 400
    assert ismb400.mass_kg_m > 0
