"""Tests for STAAD .std import into StructuralModel / 3D."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.assign import assign_defaults
from app.core.pipeline import PipelineOptions, run_pipeline
from app.export.staad import export_staad_std
from app.export.staad_import import import_staad_std, parse_staad_std
from app.geometry.peb_frame import RoofLoadsInput, WindSeismicInput, building_from_simple
from app.geometry.peb_frame import BuildingGeometryInput, FrameType


MINIMAL_STD = """
STAAD SPACE
UNIT METER KN
JOINT COORDINATES
1 0 0 0; 2 0 8 0; 3 10 9 0; 4 20 8 0; 5 20 0 0;
MEMBER INCIDENCES
1 1 2; 2 2 3; 3 3 4; 4 4 5;
SUPPORTS
1 5 PINNED
MEMBER PROPERTY INDIAN
1 4 TABLE ST ISMB 400
2 3 TABLE ST ISMB 350
FINISH
"""


def test_parse_minimal_std():
    model = parse_staad_std(MINIMAL_STD, source="memory")
    assert len(model.nodes) == 5
    assert len(model.members) == 4
    assert 1 in model.supports and 5 in model.supports
    assert model.members[1].section == "ISMB 400"
    assert model.members[2].section == "ISMB 350"
    assert model.members[1].member_type == "column"
    assert model.members[2].member_type == "rafter"


def test_parse_range_supports_and_properties():
    text = """
STAAD SPACE
UNIT METER KN
JOINT COORDINATES
1 0 0 0; 2 0 5 0; 3 5 5 0; 4 5 0 0;
MEMBER INCIDENCES
1 1 2; 2 2 3; 3 3 4;
SUPPORTS
1 TO 4 PINNED
MEMBER PROPERTY INDIAN
1 TO 3 TABLE ST ISMB 300
FINISH
"""
    model = parse_staad_std(text)
    assert len(model.supports) == 4
    assert all(m.section == "ISMB 300" for m in model.members.values())


def test_import_file(tmp_path: Path):
    path = tmp_path / "sample.std"
    path.write_text(MINIMAL_STD, encoding="utf-8")
    model = import_staad_std(path)
    assert len(model.nodes) == 5
    assert model.metadata.get("imported_from")


def test_roundtrip_export_import(tmp_path: Path, section_db):
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=12.0,
        sidewall_spacings_m=(6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.SINGLE_GABLE,
        roof_loads=RoofLoadsInput(0.3, 0.0, 0.5),
        wind_seismic=WindSeismicInput(wind_speed_mps=40.0),
    )
    result = run_pipeline(
        params,
        options=PipelineOptions(run_analysis=False, run_design=False),
        section_db=section_db,
    )
    out = tmp_path / "roundtrip.std"
    export_staad_std(result.model, out)
    imported = import_staad_std(out)

    assert len(imported.nodes) == len(result.model.nodes)
    assert len(imported.members) == len(result.model.members)
    # Coordinates match
    for nid, node in result.model.nodes.items():
        imp = imported.nodes[nid]
        assert imp.x == pytest.approx(node.x)
        assert imp.y == pytest.approx(node.y)
        assert imp.z == pytest.approx(node.z)


def test_missing_joints_raises():
    with pytest.raises(ValueError, match="JOINT"):
        parse_staad_std("STAAD SPACE\nFINISH\n")
