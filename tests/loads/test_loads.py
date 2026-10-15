"""Tests for load engine and wind pressure."""

import pytest

from app.core.assign import assign_defaults
from app.geometry.peb_frame import building_from_simple, generate_peb_model
from app.loads.engine import apply_loads, design_wind_pressure_kn_m2


def test_wind_pressure_formula() -> None:
    pz, meta = design_wind_pressure_kn_m2(47.0, 10.0)
    assert meta["Vz"] == pytest.approx(47.0)
    assert pz == pytest.approx(0.6 * 47.0**2 / 1000.0)


def test_apply_loads_creates_combos() -> None:
    model = generate_peb_model(building_from_simple(20, 12, 8, 10, 6))
    assign_defaults(model)
    model.metadata["roof_loads"] = {
        "dead_kn_m2": 0.3,
        "collateral_kn_m2": 0.15,
        "live_kn_m2": 0.75,
    }
    model.metadata["wind_seismic"] = {"wind_speed_mps": 47.0}
    apply_loads(model)
    assert "DL" in model.load_cases
    assert "LL" in model.load_cases
    assert "WL" in model.load_cases
    assert len(model.combinations) >= 5
    assert any(ml.load_case_id == "DL" for ml in model.member_loads)
    assert any(ml.load_case_id == "LL" for ml in model.member_loads)
