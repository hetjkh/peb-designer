"""Geometry validation edge cases."""

from __future__ import annotations

import pytest

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    MezzanineInput,
    CraneInput,
    generate_peb_model,
    validate_building_input,
)
from app.geometry.spacing import parse_spacing_list
from app.geometry.validation import ValidationError, validate_geometry_input


def test_spacing_invalid_token():
    with pytest.raises(ValueError, match="invalid"):
        parse_spacing_list("abc", field_name="Width")


def test_spacing_zero_rejected():
    with pytest.raises(ValueError):
        parse_spacing_list("0", field_name="Width")


def test_legacy_validation_zero_span():
    errs = validate_geometry_input(0, 60, 8, 10, 6)
    assert any("Span" in e for e in errs)


def test_building_validation_pitch_out_of_range():
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([6.0] * 10),
        eave_height_m=8.0,
        roof_pitch_1_to_n=100.0,
    )
    errs = validate_building_input(params)
    assert any("pitch" in e.lower() for e in errs)


def test_mezzanine_validation():
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=24.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        mezzanine=MezzanineInput(enabled=True, width_m=25.0, height_m=4.0, col_spacing_m=6.0),
    )
    errs = validate_building_input(params)
    assert any("start+width" in e or "Mezzanine" in e for e in errs)


def test_crane_validation():
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=24.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        crane=CraneInput(enabled=True, runway_height_m=10.0),
    )
    errs = validate_building_input(params)
    assert any("Crane" in e for e in errs)


def test_length_must_match_sidewall_sum():
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=50.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
    )
    with pytest.raises(ValidationError):
        generate_peb_model(params)


def test_ffl_offsets_base_nodes():
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=6.0,
        sidewall_spacings_m=(6.0,),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        ffl_level_m=0.5,
        frame_type=FrameType.SINGLE_GABLE,
    )
    model = generate_peb_model(params)
    bases = [n for n in model.nodes.values() if abs(n.y - 0.5) < 1e-9]
    assert bases
    assert all(abs(n.y - 0.5) < 1e-9 for n in bases)
