"""Validation for PEB building geometry inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


class ValidationError(ValueError):
    """Raised when one or more geometry inputs are invalid."""

    def __init__(self, messages: Sequence[str]):
        self.messages = list(messages)
        super().__init__("\n".join(self.messages))


@dataclass(frozen=True)
class GeometryLimits:
    """Soft engineering limits for Milestone 1 UI validation.

    These are practical bounds for a first prototype, not code-mandated
    values. They may be revised when design standards are implemented.
    """

    min_span_m: float = 5.0
    max_span_m: float = 80.0
    min_length_m: float = 5.0
    max_length_m: float = 300.0
    min_eave_height_m: float = 3.0
    max_eave_height_m: float = 30.0
    min_roof_slope_deg: float = 0.0
    max_roof_slope_deg: float = 45.0
    min_bay_spacing_m: float = 3.0
    max_bay_spacing_m: float = 15.0
    length_tolerance_m: float = 1e-6


def validate_geometry_input(
    span_m: float,
    length_m: float,
    eave_height_m: float,
    roof_slope_deg: float,
    bay_spacing_m: float,
    limits: GeometryLimits | None = None,
) -> List[str]:
    """Validate geometry inputs.

    Returns a list of human-readable error messages (empty if valid).
    """
    limits = limits or GeometryLimits()
    errors: List[str] = []

    def _check_positive(name: str, value: float) -> None:
        if value is None or not isinstance(value, (int, float)):
            errors.append(f"{name} must be a number.")
            return
        if value != value:  # NaN
            errors.append(f"{name} is not a valid number.")
        elif value <= 0:
            errors.append(f"{name} must be greater than zero.")

    _check_positive("Span", span_m)
    _check_positive("Length", length_m)
    _check_positive("Eave height", eave_height_m)
    _check_positive("Bay spacing", bay_spacing_m)

    if isinstance(roof_slope_deg, (int, float)):
        if roof_slope_deg != roof_slope_deg:
            errors.append("Roof slope is not a valid number.")
        elif roof_slope_deg < limits.min_roof_slope_deg:
            errors.append(
                f"Roof slope must be ≥ {limits.min_roof_slope_deg}°."
            )
        elif roof_slope_deg > limits.max_roof_slope_deg:
            errors.append(
                f"Roof slope must be ≤ {limits.max_roof_slope_deg}°."
            )
    else:
        errors.append("Roof slope must be a number.")

    if errors:
        return errors

    if span_m < limits.min_span_m or span_m > limits.max_span_m:
        errors.append(
            f"Span must be between {limits.min_span_m} m and "
            f"{limits.max_span_m} m."
        )
    if length_m < limits.min_length_m or length_m > limits.max_length_m:
        errors.append(
            f"Length must be between {limits.min_length_m} m and "
            f"{limits.max_length_m} m."
        )
    if (
        eave_height_m < limits.min_eave_height_m
        or eave_height_m > limits.max_eave_height_m
    ):
        errors.append(
            f"Eave height must be between {limits.min_eave_height_m} m and "
            f"{limits.max_eave_height_m} m."
        )
    if (
        bay_spacing_m < limits.min_bay_spacing_m
        or bay_spacing_m > limits.max_bay_spacing_m
    ):
        errors.append(
            f"Bay spacing must be between {limits.min_bay_spacing_m} m and "
            f"{limits.max_bay_spacing_m} m."
        )

    if bay_spacing_m > length_m:
        errors.append("Bay spacing cannot exceed building length.")

    # Length must be an integer number of bays (within tolerance).
    n_bays = length_m / bay_spacing_m
    n_bays_rounded = round(n_bays)
    if abs(n_bays - n_bays_rounded) > limits.length_tolerance_m:
        errors.append(
            "Building length must be an integer multiple of bay spacing "
            f"(length / bay spacing = {n_bays:.6g})."
        )
    elif n_bays_rounded < 1:
        errors.append("At least one bay is required.")

    return errors


def require_valid_geometry(**kwargs) -> None:
    """Raise ValidationError if geometry inputs are invalid."""
    messages = validate_geometry_input(**kwargs)
    if messages:
        raise ValidationError(messages)
