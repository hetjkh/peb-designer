"""Database search / list coverage."""

from __future__ import annotations

import pytest

from app.database.materials import get_material
from app.database.sections import SectionDatabase, default_section_for_type


def test_search_ismb(section_db: SectionDatabase):
    hits = section_db.search("ISMB 4")
    assert any(s.name == "ISMB 400" for s in hits)


def test_list_by_type(section_db: SectionDatabase):
    ismb = section_db.list_sections("ISMB")
    built = section_db.list_sections("BUILTUP")
    assert ismb
    assert built
    assert all(s.designation_type == "ISMB" for s in ismb)


def test_unknown_section_raises(section_db: SectionDatabase):
    with pytest.raises(KeyError):
        section_db.get("NOT_A_SECTION")


def test_unknown_material_raises():
    with pytest.raises(KeyError):
        get_material("NOTREAL")


def test_default_section_mapping():
    assert "ISMB" in default_section_for_type("column")
    assert "ISMB" in default_section_for_type("rafter")
