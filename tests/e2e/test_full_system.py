"""End-to-end regression: every template through full pipeline."""

from __future__ import annotations

import pytest

from app.core.pipeline import PipelineOptions, run_pipeline
from app.core.models import SupportType
from app.export.staad import build_staad_std_text
from app.gui.widgets.frame_preview_2d import FramePreview2D
from app.gui.widgets.member_info_panel import MemberInfoPanel
from app.templates.catalog import list_templates

import os

os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize("tpl", list_templates(), ids=lambda t: t.id)
def test_template_full_pipeline(tpl, section_db):
    """Geometry → assign → loads → analysis → design → STAAD for each template."""
    params = tpl.to_params()
    result = run_pipeline(
        params,
        options=PipelineOptions(
            column_section="ISMB 400",
            rafter_section="ISMB 350",
            material="E350",
            support_type=SupportType.PINNED,
            run_analysis=True,
            run_design=True,
        ),
        section_db=section_db,
    )
    model = result.model

    assert len(model.nodes) > 0
    assert len(model.members) > 0
    assert model.supports
    assert model.load_cases
    assert model.combinations
    assert model.member_loads
    assert result.analysis_ok, (
        model.analysis.message if model.analysis else "no analysis"
    )
    assert model.analysis is not None
    assert model.analysis.member_forces
    assert model.design_results
    assert "STAAD SPACE" in result.staad_text
    assert "JOINT COORDINATES" in result.staad_text
    assert "MEMBER INCIDENCES" in result.staad_text
    assert "SUPPORTS" in result.staad_text

    # Every designed member has checks
    for res in model.design_results.values():
        assert res.checks
        assert res.status in ("PASS", "FAIL")


@pytest.mark.parametrize("tpl", list_templates(), ids=lambda t: t.id)
def test_template_2d_and_member_info(tpl, section_db, qapp):
    params = tpl.to_params()
    result = run_pipeline(
        params,
        options=PipelineOptions(run_analysis=True, run_design=True),
        section_db=section_db,
    )
    model = result.model

    preview = FramePreview2D()
    preview.set_from_metadata(model.metadata)
    image = preview.render_to_image(640, 360)
    assert not image.isNull()

    # Member info for first column/rafter
    mid = next(
        m.id
        for m in model.member_list()
        if m.member_type in ("column", "rafter")
    )
    panel = MemberInfoPanel()
    panel.show_member(model, mid)
    text = panel.body.toPlainText()
    assert f"Member: M{mid}" in text
    assert "Section:" in text
    assert "Design STATUS:" in text or "No design" in text


def test_pipeline_without_analysis_skips_design(warehouse_params, section_db):
    result = run_pipeline(
        warehouse_params,
        options=PipelineOptions(run_analysis=False, run_design=True),
        section_db=section_db,
    )
    assert not result.analysis_ok
    assert "skipped" in result.design_summary.lower() or "not run" in result.design_summary.lower() or "Design skipped" in result.design_summary


def test_staad_node_count_equals_3d_model(warehouse_params, section_db):
    result = run_pipeline(warehouse_params, section_db=section_db)
    text = build_staad_std_text(result.model)
    joint_block = text.split("JOINT COORDINATES")[1].split("MEMBER INCIDENCES")[0]
    assert joint_block.count(";") == len(result.model.nodes)
