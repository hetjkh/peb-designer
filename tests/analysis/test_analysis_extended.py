"""Expanded analysis engine checks."""

from __future__ import annotations

from app.analysis.engine import DirectStiffness2DEngine, OpenSeesEngine, get_default_engine
from app.core.models import SupportType
from app.core.assign import assign_defaults
from app.loads.engine import apply_loads


def test_default_engine_is_direct_stiffness():
    assert isinstance(get_default_engine(), DirectStiffness2DEngine)


def test_opensees_engine_reports_unavailable_or_stub():
    result = OpenSeesEngine().analyze(__import__("app.core.models", fromlist=["StructuralModel"]).StructuralModel())
    assert result.status == "error"
    assert "OpenSees" in result.message or "empty" in result.message.lower() or "not" in result.message.lower()


def test_analysis_produces_forces_for_all_combos(assigned_model, section_db):
    engine = DirectStiffness2DEngine(section_db=section_db)
    result = engine.analyze(assigned_model)
    assert result.status == "ok", result.message
    combo_ids = set(assigned_model.combinations)
    force_combos = {f.combination_id for f in result.member_forces}
    assert combo_ids <= force_combos


def test_analysis_displacements_are_finite(assigned_model, section_db):
    result = DirectStiffness2DEngine(section_db=section_db).analyze(assigned_model)
    assert result.status == "ok"
    for d in result.displacements:
        assert abs(d.ux_m) < 1.0
        assert abs(d.uy_m) < 1.0


def test_supported_nodes_have_near_zero_translation(assigned_model, section_db):
    result = DirectStiffness2DEngine(section_db=section_db).analyze(assigned_model)
    support_ids = set(assigned_model.supports)
    # Check one combination
    for d in result.displacements:
        if d.node_id in support_ids and d.combination_id == "C2":
            assert abs(d.ux_m) < 1e-8
            assert abs(d.uy_m) < 1e-8


def test_empty_model_analysis_errors(section_db):
    from app.core.models import StructuralModel

    result = DirectStiffness2DEngine(section_db=section_db).analyze(StructuralModel())
    assert result.status == "error"


def test_fixed_base_also_solves(simple_geometry_model, section_db):
    model = simple_geometry_model
    assign_defaults(model, support_type=SupportType.FIXED)
    model.metadata["roof_loads"] = {"dead_kn_m2": 0.3, "collateral_kn_m2": 0, "live_kn_m2": 0.5}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 40.0}
    apply_loads(model, section_db=section_db)
    result = DirectStiffness2DEngine(section_db=section_db).analyze(model)
    assert result.status == "ok", result.message
