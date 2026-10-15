"""Tests for STAAD.Pro .std export."""

from __future__ import annotations

from pathlib import Path

from app.core.assign import assign_defaults
from app.export.staad import export_staad_std, staad_std_text
from app.geometry.peb_frame import building_from_simple, generate_peb_model
from app.loads.engine import apply_loads


def _sample_model():
    model = generate_peb_model(building_from_simple(20.0, 12.0, 8.0, 10.0, 6.0))
    assign_defaults(model)
    model.metadata["roof_loads"] = {"dead_kn_m2": 0.3, "collateral_kn_m2": 0.0, "live_kn_m2": 0.5}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 44.0}
    apply_loads(model)
    return model


def test_staad_export_contains_joints_and_members(tmp_path: Path) -> None:
    model = _sample_model()
    path = export_staad_std(model, tmp_path / "warehouse.std")
    text = path.read_text(encoding="utf-8")

    assert text.startswith("STAAD SPACE")
    assert "UNIT METER KN" in text
    assert "JOINT COORDINATES" in text
    assert "MEMBER INCIDENCES" in text
    assert "SUPPORTS" in text
    assert "PINNED" in text
    assert "FINISH" in text
    assert path.exists()


def test_staad_joint_count_matches_model() -> None:
    model = _sample_model()
    text = staad_std_text(model)
    joint_section = text.split("JOINT COORDINATES")[1].split("MEMBER INCIDENCES")[0]
    member_section = text.split("MEMBER INCIDENCES")[1].split("MEMBER PROPERTY")[0]
    assert joint_section.count(";") == len(model.nodes)
    assert member_section.count(";") == len(model.members)
