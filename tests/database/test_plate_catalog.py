"""Tests for plate catalog and built-up library sync."""

from app.database.plate_catalog import (
    PlateCatalog,
    builtup_properties,
    format_mm_list,
    generate_builtup_library,
    parse_mm_list,
    save_plate_catalog,
    load_plate_catalog,
)
from app.database.sections import SectionDatabase


def test_parse_and_format_mm_list() -> None:
    vals = parse_mm_list("250, 300; 350", field_name="Web Depths")
    assert vals == [250.0, 300.0, 350.0]
    assert "250" in format_mm_list(vals)


def test_parse_mm_list_rejects_empty() -> None:
    try:
        parse_mm_list("  , , ", field_name="Web Depths")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Web Depths" in str(exc)


def test_catalog_validate_limits() -> None:
    cat = PlateCatalog(web_depths_mm=[2500])
    errors = cat.validate()
    assert any("Web depths" in e for e in errors)


def test_builtup_properties_overall_depth() -> None:
    sec = builtup_properties(500, 8, 250, 12)
    assert sec.designation_type == "BUILTUP"
    assert abs(sec.depth_mm - 524.0) < 1e-6  # 500 + 2*12
    assert "BU 524x250x8x12" == sec.name
    assert sec.area_cm2 > 0
    assert sec.ix_cm4 > 0


def test_generate_builtup_library_capped() -> None:
    cat = PlateCatalog()
    library = generate_builtup_library(cat, max_sections=80)
    assert 0 < len(library) <= 80
    assert all(s.designation_type == "BUILTUP" for s in library)


def test_replace_builtup_sync(tmp_path) -> None:
    db_path = tmp_path / "sections.db"
    db = SectionDatabase(db_path)
    before = [s for s in db.list_sections() if s.designation_type == "BUILTUP"]
    assert len(before) == 3  # seed

    cat = PlateCatalog(
        web_depths_mm=[400, 500],
        web_thicknesses_mm=[6, 8],
        flange_widths_mm=[200, 250],
        flange_thicknesses_mm=[10, 12],
    )
    n = db.sync_builtup_from_plate_catalog(cat)
    assert n > 0
    after = [s for s in db.list_sections() if s.designation_type == "BUILTUP"]
    assert len(after) == n
    assert all(s.name.startswith("BU ") for s in after)
    # ISMB rows preserved
    assert db.get("ISMB 400") is not None


def test_plate_catalog_persist(tmp_path) -> None:
    path = tmp_path / "plate_catalog.json"
    cat = PlateCatalog(web_depths_mm=[300, 400], use_as_project_default=False)
    save_plate_catalog(cat, path)
    loaded = load_plate_catalog(path)
    assert loaded.web_depths_mm == [300.0, 400.0]
    assert loaded.use_as_project_default is False
