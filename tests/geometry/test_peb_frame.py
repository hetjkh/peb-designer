"""Geometry engine unit tests."""

from __future__ import annotations

import math

import pytest

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    building_from_simple,
    generate_peb_model,
)
from app.geometry.spacing import parse_spacing_list
from app.geometry.validation import ValidationError, validate_geometry_input


def test_parse_spacing_forms() -> None:
    assert parse_spacing_list("20") == [20.0]
    assert parse_spacing_list("2@30") == [30.0, 30.0]
    assert parse_spacing_list("30+30") == [30.0, 30.0]
    assert parse_spacing_list("10+2@15") == [10.0, 15.0, 15.0]


def test_validate_accepts_typical_warehouse() -> None:
    errors = validate_geometry_input(
        span_m=20.0,
        length_m=60.0,
        eave_height_m=8.0,
        roof_slope_deg=10.0,
        bay_spacing_m=6.0,
    )
    assert errors == []


def test_validate_rejects_non_multiple_length() -> None:
    errors = validate_geometry_input(
        span_m=20.0,
        length_m=61.0,
        eave_height_m=8.0,
        roof_slope_deg=10.0,
        bay_spacing_m=6.0,
    )
    assert any("integer multiple" in e for e in errors)


def test_ridge_height_pitch() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([6.0] * 10),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
    )
    assert params.ridge_height_for_run(10.0) == pytest.approx(9.0)


def test_generate_single_gable_counts() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([6.0] * 10),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.CLEAR_SPAN,
    )
    model = generate_peb_model(params)
    assert params.number_of_frames == 11
    assert len(model.nodes) > 0
    assert len(model.members) > 0
    assert model.metadata["frame_type"] == "clear_span"


def test_multi_gable_has_two_ridges() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(30.0, 30.0),
        length_m=60.0,
        sidewall_spacings_m=tuple([6.0] * 10),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.MULTI_GABLE,
    )
    model = generate_peb_model(params)
    profile = model.metadata["profile_xy"]
    ridges = [p for p in profile if p[2] == "ridge"]
    assert len(ridges) == 2


def test_multi_span_interior_column() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(30.0, 30.0),
        length_m=30.0,
        sidewall_spacings_m=(7.5, 7.5, 7.5, 7.5),
        eave_height_m=6.5,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.MULTI_SPAN,
    )
    model = generate_peb_model(params)
    assert model.metadata["column_xs"] == [0.0, 30.0, 60.0]
    assert any(m.member_type == "column" for m in model.members.values())


def test_building_from_simple_compat() -> None:
    params = building_from_simple(20.0, 12.0, 8.0, 10.0, 6.0)
    model = generate_peb_model(params)
    assert len(model.nodes) > 0


def test_generate_model_rejects_bad_multi() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([6.0] * 10),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.MULTI_SPAN,
    )
    with pytest.raises(ValidationError):
        generate_peb_model(params)


def test_member_connectivity() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=6.0,
        sidewall_spacings_m=(6.0,),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
    )
    model = generate_peb_model(params)
    for member in model.members.values():
        assert member.start_node in model.nodes
        assert member.end_node in model.nodes
