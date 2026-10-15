"""Expanded IS 800 design checks."""

from __future__ import annotations

from app.analysis.engine import DirectStiffness2DEngine
from app.core.assign import assign_defaults
from app.design.is800 import design_member, design_model
from app.loads.engine import apply_loads


REQUIRED_CHECKS = {"Tension", "Compression", "Bending", "Shear", "Combined", "Slenderness"}


def test_design_all_primary_members(assigned_model, section_db):
    assigned_model.analysis = DirectStiffness2DEngine(section_db=section_db).analyze(assigned_model)
    results = design_model(assigned_model, section_db=section_db)
    assert results
    for mid, res in results.items():
        names = {c.name for c in res.checks}
        assert REQUIRED_CHECKS <= names
        assert res.status in ("PASS", "FAIL")
        assert res.max_utilization >= 0
        assert res.section
        assert res.material


def test_undersized_section_tends_to_fail(simple_geometry_model, section_db):
    model = simple_geometry_model
    assign_defaults(
        model,
        column_section="ISMB 150",
        rafter_section="ISMB 150",
        material="E250",
    )
    model.metadata["roof_loads"] = {"dead_kn_m2": 1.0, "collateral_kn_m2": 0.5, "live_kn_m2": 1.5}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 55.0}
    apply_loads(model, section_db=section_db)
    model.analysis = DirectStiffness2DEngine(section_db=section_db).analyze(model)
    assert model.analysis.status == "ok"
    results = design_model(model, section_db=section_db)
    # Expect at least some FAIL under heavy load + tiny sections
    assert any(r.status == "FAIL" for r in results.values())


def test_missing_section_design_is_na(simple_geometry_model, section_db):
    model = simple_geometry_model
    # leave members without section
    model.analysis = None
    mid = next(iter(model.members))
    res = design_member(model, mid, section_db=section_db)
    assert res.status == "N/A"
