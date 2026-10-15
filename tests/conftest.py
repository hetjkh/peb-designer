"""Shared fixtures for PEB Designer tests."""

from __future__ import annotations

import pytest

from app.core.assign import assign_defaults
from app.core.models import SupportType
from app.database.sections import SectionDatabase
from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    RoofLoadsInput,
    WindSeismicInput,
    building_from_simple,
    generate_peb_model,
)
from app.loads.engine import apply_loads


@pytest.fixture
def section_db(tmp_path):
    return SectionDatabase(tmp_path / "sections.db")


@pytest.fixture
def simple_geometry_model():
    """20×12 m single-gable, 2 frames — fast for unit tests."""
    return generate_peb_model(building_from_simple(20.0, 12.0, 8.0, 10.0, 6.0))


@pytest.fixture
def assigned_model(simple_geometry_model, section_db):
    model = simple_geometry_model
    assign_defaults(
        model,
        column_section="ISMB 400",
        rafter_section="ISMB 350",
        material="E350",
        support_type=SupportType.PINNED,
    )
    model.metadata["roof_loads"] = {
        "dead_kn_m2": 0.3,
        "collateral_kn_m2": 0.15,
        "live_kn_m2": 0.75,
    }
    model.metadata["wind_seismic"] = {"wind_speed_mps": 44.0}
    apply_loads(model, section_db=section_db)
    return model


@pytest.fixture
def warehouse_params():
    return BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=24.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.SINGLE_GABLE,
        roof_loads=RoofLoadsInput(0.3, 0.15, 0.75),
        wind_seismic=WindSeismicInput(wind_speed_mps=44.0),
    )
