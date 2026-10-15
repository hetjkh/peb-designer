"""PEB geometry generation and validation."""

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    DeflectionLimits,
    MezzanineInput,
    MezzanineLevel,
    RoofMonitorInput,
    CraneInput,
    BuildingExtensions,
    building_from_simple,
    coerce_frame_type,
    frame_allows_interior_columns,
    generate_peb_model,
    pitch_n_from_slope_x10,
    recommend_ext_col_base,
    resolve_width_spans,
    slope_x10_from_pitch_n,
    validate_building_input,
)
from app.geometry.spacing import parse_spacing_list
from app.geometry.validation import ValidationError, validate_geometry_input

__all__ = [
    "BuildingExtensions",
    "BuildingGeometryInput",
    "CraneInput",
    "DeflectionLimits",
    "FrameType",
    "MezzanineInput",
    "MezzanineLevel",
    "RoofMonitorInput",
    "building_from_simple",
    "coerce_frame_type",
    "frame_allows_interior_columns",
    "generate_peb_model",
    "pitch_n_from_slope_x10",
    "recommend_ext_col_base",
    "resolve_width_spans",
    "slope_x10_from_pitch_n",
    "parse_spacing_list",
    "ValidationError",
    "validate_geometry_input",
]
