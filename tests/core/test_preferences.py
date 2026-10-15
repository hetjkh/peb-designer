"""Tests for application preferences."""

from __future__ import annotations

from pathlib import Path

from app.core.models import SupportType
from app.core.preferences import (
    AppPreferences,
    load_preferences,
    save_preferences,
    set_preferences,
)
from app.core.pipeline import PipelineOptions, run_pipeline
from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    RoofLoadsInput,
    WindSeismicInput,
)


def test_preferences_roundtrip(tmp_path: Path):
    path = tmp_path / "preferences.json"
    prefs = AppPreferences(
        design_code="IS800-2007-WSD",
        roof_dead_kn_m2=5.0,
        roof_collateral_kn_m2=2.0,
        staad_version="STAAD.Pro CONNECT Edition",
        purlin_spacing_m=1.5,
        girt_spacing_m=1.5,
        ext_col_base="fixed",
    )
    save_preferences(prefs, path)
    loaded = load_preferences(path)
    assert loaded.design_code == "IS800-2007-WSD"
    assert loaded.roof_dead_kn_m2 == 5.0
    assert loaded.roof_collateral_kn_m2 == 2.0
    assert loaded.support_type() == SupportType.FIXED
    assert loaded.purlin_spacing_m == 1.5


def test_preferences_invalid_code_falls_back(tmp_path: Path):
    path = tmp_path / "preferences.json"
    path.write_text('{"design_code": "NOT-A-CODE", "ext_col_base": "PINNED"}', encoding="utf-8")
    loaded = load_preferences(path)
    assert loaded.design_code == "IS800-2007-LSD"
    assert loaded.ext_col_base == "pinned"


def test_pipeline_writes_preference_metadata(tmp_path: Path, section_db):
    prefs = AppPreferences(
        design_code="IS800-2007-LSD",
        roof_dead_kn_m2=0.4,
        roof_collateral_kn_m2=0.2,
        staad_version="STAAD.Pro 2024",
        purlin_spacing_m=1.2,
        girt_spacing_m=1.8,
        ext_col_base="pinned",
    )
    set_preferences(prefs, persist=False)

    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=12.0,
        sidewall_spacings_m=(6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.SINGLE_GABLE,
        roof_loads=RoofLoadsInput(0.4, 0.2, 0.75),
        wind_seismic=WindSeismicInput(wind_speed_mps=40.0, load_combination_label=prefs.design_code),
    )
    result = run_pipeline(
        params,
        options=PipelineOptions(
            run_analysis=False,
            run_design=False,
            design_code=prefs.design_code,
            staad_version=prefs.staad_version,
            purlin_spacing_m=prefs.purlin_spacing_m,
            girt_spacing_m=prefs.girt_spacing_m,
        ),
        section_db=section_db,
    )
    assert result.model.metadata["design_code"] == "IS800-2007-LSD"
    assert result.model.metadata["staad_version"] == "STAAD.Pro 2024"
    assert result.model.metadata["purlin_spacing_m"] == 1.2
    assert "Design code:" in result.staad_text
    assert "STAAD.Pro 2024" in result.staad_text
    assert "Purlin spacing" in result.staad_text
