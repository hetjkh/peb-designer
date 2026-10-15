"""Analysis and design pipeline tests."""

from app.analysis.engine import DirectStiffness2DEngine
from app.core.assign import assign_defaults
from app.core.pipeline import PipelineOptions, run_pipeline
from app.design.is800 import design_model
from app.geometry.peb_frame import BuildingGeometryInput, FrameType, building_from_simple, generate_peb_model
from app.loads.engine import apply_loads


def test_direct_stiffness_runs() -> None:
    model = generate_peb_model(building_from_simple(20, 12, 8, 10, 6))
    assign_defaults(model)
    model.metadata["roof_loads"] = {"dead_kn_m2": 0.3, "collateral_kn_m2": 0.0, "live_kn_m2": 0.75}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 44.0}
    apply_loads(model)
    result = DirectStiffness2DEngine().analyze(model)
    assert result.status == "ok", result.message
    assert result.member_forces
    assert result.displacements


def test_design_after_analysis() -> None:
    model = generate_peb_model(building_from_simple(20, 12, 8, 10, 6))
    assign_defaults(model, column_section="ISMB 400", rafter_section="ISMB 350")
    model.metadata["roof_loads"] = {"dead_kn_m2": 0.3, "collateral_kn_m2": 0.15, "live_kn_m2": 0.75}
    model.metadata["wind_seismic"] = {"wind_speed_mps": 44.0}
    apply_loads(model)
    model.analysis = DirectStiffness2DEngine().analyze(model)
    results = design_model(model)
    assert results
    for r in results.values():
        assert r.checks
        assert r.status in ("PASS", "FAIL", "N/A")


def test_full_pipeline() -> None:
    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=24.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.SINGLE_GABLE,
    )
    # attach loads via metadata after generate inside pipeline — set on BuildingGeometryInput roof_loads
    from app.geometry.peb_frame import RoofLoadsInput, WindSeismicInput

    params = BuildingGeometryInput(
        width_spans_m=(20.0,),
        length_m=24.0,
        sidewall_spacings_m=(6.0, 6.0, 6.0, 6.0),
        eave_height_m=8.0,
        roof_pitch_1_to_n=10.0,
        frame_type=FrameType.SINGLE_GABLE,
        roof_loads=RoofLoadsInput(0.3, 0.15, 0.75),
        wind_seismic=WindSeismicInput(wind_speed_mps=44.0),
    )
    result = run_pipeline(params, options=PipelineOptions(run_analysis=True, run_design=True))
    assert result.analysis_ok
    assert result.model.design_results
    assert "STAAD SPACE" in result.staad_text
