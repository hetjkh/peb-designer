"""Regression tests for all pre-built templates and their 2D profiles."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Offscreen Qt for 2D image rendering in CI / headless runs
os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.export.staad import build_staad_std_text, export_staad_std
from app.geometry.peb_frame import generate_peb_model, validate_building_input
from app.gui.widgets.frame_preview_2d import FramePreview2D
from app.templates.catalog import BuildingTemplate, list_templates


PREVIEW_DIR = Path(__file__).resolve().parents[2] / "examples" / "templates" / "previews"
STD_DIR = Path(__file__).resolve().parents[2] / "examples" / "templates" / "std"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_at_least_ten_templates() -> None:
    assert len(list_templates()) >= 10


@pytest.mark.parametrize("tpl", list_templates(), ids=lambda t: t.id)
def test_template_validates_and_generates(tpl: BuildingTemplate) -> None:
    params = tpl.to_params()
    errors = validate_building_input(params)
    assert errors == [], f"{tpl.id}: {errors}"

    model = generate_peb_model(params)
    assert len(model.nodes) > 0
    assert len(model.members) > 0

    profile = model.metadata.get("profile_xy") or []
    assert profile, f"{tpl.id}: missing 2D profile"

    ridges = [p for p in profile if p[2] == "ridge"]
    columns = model.metadata.get("column_xs") or []
    assert len(ridges) >= tpl.expect_min_ridges
    assert len(columns) >= tpl.expect_min_columns

    if tpl.expect_has_mezzanine:
        assert model.metadata["mezzanine"]["enabled"] is True
        assert any(m.member_type.startswith("mezzanine") for m in model.members.values())

    if tpl.expect_has_crane:
        assert model.metadata["crane"]["enabled"] is True

    # STAAD text should build for every template
    text = build_staad_std_text(model, title=tpl.name)
    assert "STAAD SPACE" in text
    assert "JOINT COORDINATES" in text
    assert "FINISH" in text


@pytest.mark.parametrize("tpl", list_templates(), ids=lambda t: t.id)
def test_template_2d_preview_renders(tpl: BuildingTemplate, qapp: QApplication, tmp_path: Path) -> None:
    model = generate_peb_model(tpl.to_params())
    preview = FramePreview2D()
    preview.set_from_metadata(model.metadata)
    image = preview.render_to_image(900, 420)
    assert not image.isNull()
    assert image.width() == 900
    assert image.height() == 420

    out = tmp_path / f"{tpl.id}.png"
    assert image.save(str(out))
    assert out.exists() and out.stat().st_size > 1000


def test_export_all_template_artifacts(qapp: QApplication) -> None:
    """Write lasting preview PNGs and .std files under examples/templates/."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    STD_DIR.mkdir(parents=True, exist_ok=True)

    for tpl in list_templates():
        model = generate_peb_model(tpl.to_params())
        preview = FramePreview2D()
        preview.set_from_metadata(model.metadata)
        png = PREVIEW_DIR / f"{tpl.id}.png"
        assert preview.render_to_image().save(str(png))
        export_staad_std(model, STD_DIR / f"{tpl.id}.std", title=tpl.name)

    assert len(list(PREVIEW_DIR.glob("*.png"))) >= 10
    assert len(list(STD_DIR.glob("*.std"))) >= 10


def test_templates_are_geometrically_distinct() -> None:
    """Ensure the 12 presets are not accidental duplicates."""
    signatures = set()
    for tpl in list_templates():
        model = generate_peb_model(tpl.to_params())
        profile = tuple(
            (round(x, 3), round(y, 3), role)
            for x, y, role in (model.metadata.get("profile_xy") or [])
        )
        sig = (
            tpl.frame_type.value,
            round(model.metadata["span_m"], 3),
            round(float(model.metadata["eave_height_m"]), 3),
            profile,
            bool((model.metadata.get("mezzanine") or {}).get("enabled")),
            bool((model.metadata.get("crane") or {}).get("enabled")),
            round(float(model.metadata.get("blockwall_height_m") or 0), 3),
        )
        assert sig not in signatures, f"Duplicate geometry signature: {tpl.id}"
        signatures.add(sig)
    assert len(signatures) >= 10
