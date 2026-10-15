"""Expanded STAAD export checks."""

from __future__ import annotations

from app.analysis.engine import DirectStiffness2DEngine
from app.design.is800 import design_model
from app.export.staad import build_staad_std_text


def test_export_includes_properties_loads_combos(assigned_model, section_db, tmp_path):
    text = build_staad_std_text(assigned_model)
    assert "MEMBER PROPERTY INDIAN" in text
    assert "ISMB" in text
    assert "LOAD" in text
    assert "LOAD COMB" in text
    assert "SUPPORTS" in text
    assert "PINNED" in text
    path = tmp_path / "out.std"
    path.write_text(text, encoding="utf-8")
    assert path.stat().st_size > 200


def test_export_joint_member_counts(assigned_model):
    text = build_staad_std_text(assigned_model)
    joints = text.split("JOINT COORDINATES")[1].split("MEMBER INCIDENCES")[0]
    members = text.split("MEMBER INCIDENCES")[1].split("MEMBER PROPERTY")[0]
    assert joints.count(";") == len(assigned_model.nodes)
    assert members.count(";") == len(assigned_model.members)


def test_staad_matches_analyzed_model(assigned_model, section_db):
    assigned_model.analysis = DirectStiffness2DEngine(section_db=section_db).analyze(assigned_model)
    design_model(assigned_model, section_db=section_db)
    text = build_staad_std_text(assigned_model)
    # Geometry identity: every node id appears
    for nid in assigned_model.nodes:
        assert f"\n{nid} " in text or text.startswith(f"{nid} ") or f"JOINT COORDINATES\n{nid} " in text
    for mid in assigned_model.members:
        assert str(mid) in text
