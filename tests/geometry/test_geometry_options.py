"""Tests for extended geometry options (frame types, int-col, auto base)."""

from __future__ import annotations

import pytest

from app.core.models import SupportType
from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    coerce_frame_type,
    generate_peb_model,
    pitch_n_from_slope_x10,
    recommend_ext_col_base,
    resolve_width_spans,
    slope_x10_from_pitch_n,
)
from app.geometry.validation import ValidationError


def test_coerce_legacy_single_gable() -> None:
    assert coerce_frame_type("single_gable") == FrameType.CLEAR_SPAN
    assert coerce_frame_type(FrameType.SINGLE_GABLE) == FrameType.CLEAR_SPAN


def test_slope_x10_roundtrip() -> None:
    assert pitch_n_from_slope_x10(1.0) == pytest.approx(10.0)
    assert slope_x10_from_pitch_n(10.0) == pytest.approx(1.0)
    assert pitch_n_from_slope_x10(2.0) == pytest.approx(5.0)


def test_recommend_ext_col_base_wider_pinned() -> None:
    rec, reason = recommend_ext_col_base(40.0, 6.5)
    assert rec == SupportType.PINNED
    assert "wider" in reason


def test_recommend_ext_col_base_heavy_crane_fixed() -> None:
    rec, _ = recommend_ext_col_base(40.0, 6.5, heavy_crane=True)
    assert rec == SupportType.FIXED


def test_resolve_clear_span_refuses_int_cols() -> None:
    with pytest.raises(ValidationError):
        resolve_width_spans(FrameType.CLEAR_SPAN, [40.0], [20.0, 20.0])


def test_resolve_multi_span_from_width() -> None:
    spans = resolve_width_spans(FrameType.MULTI_SPAN, [20.0, 20.0], [])
    assert spans == (20.0, 20.0)


def test_resolve_multi_span_from_int_col() -> None:
    spans = resolve_width_spans(FrameType.MULTI_SPAN, [40.0], [20.0, 20.0])
    assert spans == (20.0, 20.0)


def test_mono_slope_profile() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(40.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([7.5] * 8),
        eave_height_m=6.5,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.MONO_SLOPE,
    )
    model = generate_peb_model(params)
    profile = model.metadata["profile_xy"]
    assert profile[0][2] == "eave"
    assert profile[-1][2] == "ridge"
    assert profile[-1][1] == pytest.approx(10.5)  # 6.5 + 40/10


def test_asym_gable_offset_ridge() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(40.0,),
        length_m=60.0,
        sidewall_spacings_m=tuple([7.5] * 8),
        eave_height_m=6.5,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.ASYM_GABLE,
        ridge_distance_m=12.0,
        ridge_auto=False,
    )
    model = generate_peb_model(params)
    ridges = [p for p in model.metadata["profile_xy"] if p[2] == "ridge"]
    assert len(ridges) == 1
    assert ridges[0][0] == pytest.approx(12.0)
