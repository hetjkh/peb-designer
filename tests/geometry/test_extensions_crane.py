"""Roof monitor and EOT crane geometry / metadata."""

from __future__ import annotations

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    CraneInput,
    FrameType,
    RoofMonitorInput,
    generate_peb_model,
    validate_building_input,
)


def _base(**kwargs):
    defaults = dict(
        width_spans_m=(40.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([7.5] * 8),
        eave_height_m=6.5,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.CLEAR_SPAN,
    )
    defaults.update(kwargs)
    return BuildingGeometryInput(**defaults)


def test_roof_monitor_metadata():
    rm = RoofMonitorInput(
        enabled=True, throat_width_m=3.0, height_m=1.5, extension_m=0.75
    )
    model = generate_peb_model(_base(roof_monitor=rm))
    meta = model.metadata["roof_monitor"]
    assert meta["enabled"] is True
    assert meta["throat_width_m"] == 3.0
    assert meta["height_m"] == 1.5
    assert meta["extension_m"] == 0.75


def test_crane_effective_height():
    crane = CraneInput(
        enabled=True,
        name="Crane 1",
        capacity_kn=50,
        hook_height_m=4.5,
        runway_height_m=0.0,
    )
    assert crane.effective_height_m == 4.5
    model = generate_peb_model(_base(crane=crane))
    assert model.metadata["crane"]["enabled"] is True
    assert model.metadata["crane"]["effective_height_m"] == 4.5


def test_crane_too_high_rejected():
    crane = CraneInput(enabled=True, hook_height_m=7.0, runway_height_m=7.0)
    errs = validate_building_input(_base(crane=crane))
    assert any("Crane" in e for e in errs)


def test_monitor_throat_too_wide():
    rm = RoofMonitorInput(enabled=True, throat_width_m=50.0, height_m=1.5)
    errs = validate_building_input(_base(roof_monitor=rm))
    assert any("throat" in e.lower() for e in errs)
