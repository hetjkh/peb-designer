"""Section assignment and support generation."""

from __future__ import annotations

from app.core.assign import assign_defaults
from app.core.models import SupportType
from app.geometry.peb_frame import building_from_simple, generate_peb_model


def test_assign_defaults_sets_sections_and_materials(simple_geometry_model):
    model = simple_geometry_model
    assign_defaults(
        model,
        column_section="ISMB 500",
        rafter_section="ISMB 450",
        material="E250",
        support_type=SupportType.PINNED,
    )
    cols = [m for m in model.members.values() if m.member_type == "column"]
    rafts = [m for m in model.members.values() if m.member_type == "rafter"]
    assert cols and all(m.section == "ISMB 500" and m.material == "E250" for m in cols)
    assert rafts and all(m.section == "ISMB 450" and m.material == "E250" for m in rafts)
    assert model.supports
    assert all(s.support_type == SupportType.PINNED for s in model.supports.values())


def test_assign_fixed_supports():
    model = generate_peb_model(building_from_simple(20, 6, 8, 10, 6))
    assign_defaults(model, support_type=SupportType.FIXED)
    assert model.supports
    assert all(s.support_type == SupportType.FIXED and s.rz for s in model.supports.values())


def test_supports_only_at_base_level():
    model = generate_peb_model(building_from_simple(20, 6, 8, 10, 6))
    assign_defaults(model)
    ffl = float(model.metadata.get("ffl_level_m", 0) or 0)
    for sid in model.supports:
        assert abs(model.nodes[sid].y - ffl) <= 1e-9
