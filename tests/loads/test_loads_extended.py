"""Expanded load-engine checks."""

from __future__ import annotations

from app.core.assign import assign_defaults
from app.loads.engine import LoadEngineConfig, apply_loads, average_bay_spacing, design_wind_pressure_kn_m2


def test_self_weight_creates_dl_loads(assigned_model):
    dl = [m for m in assigned_model.member_loads if m.load_case_id == "DL" and "Self-weight" in m.description]
    assert dl
    assert all(m.fy_kn_m < 0 for m in dl)


def test_roof_live_on_rafters_only(assigned_model):
    ll = [m for m in assigned_model.member_loads if m.load_case_id == "LL"]
    assert ll
    for mload in ll:
        assert assigned_model.members[mload.member_id].member_type == "rafter"
        assert mload.fy_kn_m < 0


def test_wind_on_windward_columns(assigned_model):
    wl = [m for m in assigned_model.member_loads if m.load_case_id == "WL"]
    assert wl
    assert all(m.fx_kn_m > 0 for m in wl)
    for mload in wl:
        assert assigned_model.members[mload.member_id].member_type == "column"


def test_is800_combination_factors(assigned_model):
    c2 = assigned_model.combinations["C2"]
    assert c2.factors == {"DL": 1.5, "LL": 1.5}
    assert "IS 800:2007" in c2.source
    c5 = assigned_model.combinations["C5"]
    assert c5.factors["WL"] == 1.2


def test_wind_pressure_increases_with_speed():
    p1, _ = design_wind_pressure_kn_m2(33.0, 10.0)
    p2, _ = design_wind_pressure_kn_m2(50.0, 10.0)
    assert p2 > p1


def test_disable_wind(section_db, simple_geometry_model):
    model = simple_geometry_model
    assign_defaults(model)
    model.metadata["roof_loads"] = {"dead_kn_m2": 0.3, "collateral_kn_m2": 0, "live_kn_m2": 0.5}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 47.0}
    apply_loads(model, config=LoadEngineConfig(include_wind=False), section_db=section_db)
    assert not any(m.load_case_id == "WL" for m in model.member_loads)


def test_average_bay_spacing(assigned_model):
    assert average_bay_spacing(assigned_model) == 6.0
