"""Tests for code / load combination and deflection limits."""

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    DeflectionLimits,
    FrameType,
    generate_peb_model,
)


def test_deflection_limits_defaults() -> None:
    d = DeflectionLimits()
    assert d.rafter_total_load_L_over == 120
    assert d.rafter_live_load_L_over == 180
    assert d.column_wind_crane_H_over == 75
    assert d.column_seismic_H_over == 75


def test_model_stores_load_combo_and_deflection() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(40.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([7.5] * 8),
        eave_height_m=6.5,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.CLEAR_SPAN,
        load_combination_type="ASCE7-2016-LRFD-LL<=4.79kN/m2",
        deflection_limits=DeflectionLimits(
            rafter_total_load_L_over=100,
            rafter_live_load_L_over=150,
            column_wind_crane_H_over=60,
            column_seismic_H_over=80,
        ),
    )
    model = generate_peb_model(params)
    assert model.metadata["load_combination_type"] == "ASCE7-2016-LRFD-LL<=4.79kN/m2"
    dl = model.metadata["deflection_limits"]
    assert dl["rafter_total_load_L_over"] == 100
    assert dl["column_seismic_H_over"] == 80
