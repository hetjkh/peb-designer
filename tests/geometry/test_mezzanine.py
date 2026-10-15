"""Mezzanine multi-level geometry and flat-roof mode."""

from __future__ import annotations

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    FrameType,
    MezzanineInput,
    MezzanineLevel,
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


def test_mezz_embedded_columns_and_beams():
    mz = MezzanineInput(
        enabled=True,
        connection_type="pinned",
        levels=(
            MezzanineLevel(
                height_m=3.5,
                start_m=0.0,
                width_m=15.0,
                col_spacings_m=(5.0, 5.0, 5.0),
                joist_spacing_m=1.5,
                dead_kn_m2=3.5,
                live_kn_m2=3.75,
            ),
        ),
    )
    model = generate_peb_model(_base(mezzanine=mz))
    assert model.metadata["mezzanine"]["enabled"] is True
    assert len(model.metadata["mezzanine"]["levels"]) == 1
    cols = [m for m in model.members.values() if m.member_type == "mezzanine_column"]
    beams = [m for m in model.members.values() if m.member_type == "mezzanine_beam"]
    # Interior cols at 5,10,15 — not at wall x=0 (main column)
    assert len(cols) > 0
    assert len(beams) > 0
    # Interior column X positions
    xs = set()
    for m in cols:
        n = model.nodes[m.end_node]
        xs.add(round(n.x, 3))
    assert 5.0 in xs
    assert 10.0 in xs
    assert 15.0 in xs
    assert 0.0 not in xs


def test_mezz_flat_roof_only():
    mz = MezzanineInput(
        enabled=True,
        flat_roof_mezz_only=True,
        connection_type="pinned",
        levels=(
            MezzanineLevel(
                height_m=3.5,
                start_m=0.0,
                width_m=15.0,
                col_spacings_m=(5.0, 5.0, 5.0),
            ),
        ),
    )
    model = generate_peb_model(_base(mezzanine=mz))
    assert abs(model.metadata["span_m"] - 15.0) < 1e-6
    assert abs(model.metadata["eave_height_m"] - 3.5) < 1e-6
    assert model.metadata["mezzanine"]["flat_roof_mezz_only"] is True
    # Flat roof members tagged as mezzanine_beam
    assert any(m.member_type == "mezzanine_beam" for m in model.members.values())
    # No pitched rise
    ridge = float(model.metadata["ridge_height_m"])
    ffl = float(model.metadata["ffl_level_m"])
    assert abs(ridge - (ffl + 3.5)) < 0.05


def test_mezz_legacy_fields_still_work():
    mz = MezzanineInput(
        enabled=True, width_m=8.0, height_m=4.0, col_spacing_m=4.0
    )
    assert len(mz.resolved_levels()) == 1
    errs = validate_building_input(_base(mezzanine=mz, eave_height_m=10.0, width_spans_m=(25.0,)))
    assert errs == []
    model = generate_peb_model(_base(mezzanine=mz, eave_height_m=10.0, width_spans_m=(25.0,)))
    assert any(m.member_type.startswith("mezzanine") for m in model.members.values())
