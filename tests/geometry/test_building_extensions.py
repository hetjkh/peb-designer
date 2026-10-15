"""Building extensions (lean-to, fascia, canopy, roof ext, monitor)."""

from __future__ import annotations

from app.geometry.peb_frame import (
    BuildingExtensions,
    BuildingGeometryInput,
    FrameType,
    RoofMonitorInput,
    SideCanopy,
    SideFascia,
    SideLeanTo,
    SideRoofExtension,
    generate_peb_model,
)


def test_extensions_in_metadata():
    ext = BuildingExtensions(
        lean_to_right=SideLeanTo(enabled=True, width_m=5.0, slope_x10=1.0),
        roof_ext_left=SideRoofExtension(enabled=True, projection_m=0.8),
        fascia_left=SideFascia(enabled=True, height_m=1.25),
        canopy_left=SideCanopy(
            enabled=True, width_m=3.0, height_on_col_m=3.0, slope_x10=1.0
        ),
        roof_monitor=RoofMonitorInput(
            enabled=True, throat_width_m=3.0, height_m=1.5, extension_m=0.75
        ),
    )
    model = generate_peb_model(
        BuildingGeometryInput(
            width_spans_m=(40.0,),
            length_m=60.0,
            sidewall_spacings_m=tuple([7.5] * 8),
            eave_height_m=6.5,
            roof_pitch_1_to_n=10.0,
            frame_type=FrameType.CLEAR_SPAN,
            extensions=ext,
        )
    )
    e = model.metadata["extensions"]
    assert e["lean_to_right"]["enabled"] is True
    assert e["roof_ext_left"]["projection_m"] == 0.8
    assert e["fascia_left"]["height_m"] == 1.25
    assert e["canopy_left"]["width_m"] == 3.0
    assert model.metadata["roof_monitor"]["enabled"] is True
