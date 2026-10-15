"""Behavioral regressions for the sidebar / analytical model / STD audit."""
import math
from dataclasses import replace

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.core.assign import assign_defaults
from app.core.models import LoadCase, NodalLoad, MemberUniformLoad
from app.core.pipeline import PipelineOptions, run_pipeline
from app.export.staad import build_staad_std_text, extract_transverse_frame
from app.geometry.peb_frame import (
    BuildingExtensions, SideLeanTo, SideCanopy, SideFascia, SideRoofExtension,
    RoofMonitorInput, MezzanineInput, MezzanineLevel, WindSeismicInput,
    DeflectionLimits, generate_peb_model,
)
from app.gui.widgets.building_input_panel import BuildingInputPanel
from app.gui.widgets.frame_preview_2d import FramePreview2D
from app.loads.engine import apply_loads, tributary_widths
from app.analysis.engine import DirectStiffness2DEngine


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_ms(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def panel(qapp):
    p = BuildingInputPanel()
    p.run_analysis_cb.setChecked(False)
    p.run_design_cb.setChecked(False)
    yield p
    p._live_timer.stop()
    p.close()
    p.deleteLater()


def test_live_edit_updates_without_button_and_blocks_invalid_export(panel):
    received = []
    panel.model_generated.connect(lambda m, text: received.append((m, text)))
    panel.width_edit.setText("30")
    wait_ms(500)
    assert received[-1][0].metadata["span_m"] == 30
    assert received[-1][1].startswith("STAAD PLANE")
    panel.width_edit.setText("")
    assert not panel.flush_update()
    assert "Check input" in panel.status.text()
    panel.width_edit.setText("35")
    assert panel.flush_update()
    assert received[-1][0].metadata["span_m"] == 35


def test_staad_analysis_option_updates_export_without_generate(panel):
    received = []
    panel.model_generated.connect(lambda m, text: received.append((m, text)))
    panel.staad_analysis_combo.setCurrentIndex(panel.staad_analysis_combo.findData("pdelta"))
    wait_ms(500)
    assert received[-1][0].metadata["staad_analysis"] == "pdelta"
    assert "PDELTA 20 ANALYSIS SMALLDELTA" in received[-1][1]
    assert "REPEAT LOAD" in received[-1][1] and "LOAD COMB " not in received[-1][1]


@pytest.mark.parametrize("field,value,key", [
    ("width_edit", "30", "span_m"), ("eave_edit", "7", "eave_height_m"),
    ("ffl_edit", "1", "ffl_level_m"), ("blockwall_edit", "2", "blockwall_height_m"),
    ("purlin_edit", "2", "purlin_spacing_m"), ("girt_edit", "2", "girt_spacing_m"),
])
def test_sidebar_dimension_edit_reaches_model(panel, field, value, key):
    received = []
    panel.model_generated.connect(lambda m, _: received.append(m))
    getattr(panel, field).setText(value)
    assert panel._live_timer.isActive()
    assert panel.flush_update()
    assert received[-1].metadata[key] == float(value)


def test_dynamic_mezzanine_fields_trigger_update(panel):
    received = []
    panel.model_generated.connect(lambda m, _: received.append(m))
    panel.mezz_section._on_add_level()
    assert panel.flush_update()
    card = panel.mezz_section._cards[0]
    card.joist_edit.setText("2")
    assert panel._live_timer.isActive()
    assert panel.flush_update()
    assert received[-1].metadata["mezzanine"]["levels"][0]["joist_spacing_m"] == 2


def test_unequal_bays_are_preserved(panel):
    panel.length_edit.setText("20")
    panel.bay_edit.setText("6+8+6")
    assert panel.read_params().sidewall_spacings_m == (6, 8, 6)
    assert panel.flush_update()


def test_roof_load_conservation_unequal_bays(warehouse_params, section_db):
    p = replace(warehouse_params, length_m=20, sidewall_spacings_m=(6, 8, 6))
    model = generate_peb_model(p)
    assign_defaults(model)
    apply_loads(model, section_db=section_db)
    assert tributary_widths(model) == {0: 3, 6: 7, 14: 7, 20: 3}
    total = sum(-l.fy_kn_m * math.dist(model.nodes[model.members[l.member_id].start_node].coords,
                                     model.nodes[model.members[l.member_id].end_node].coords)
                for l in model.member_loads if l.load_case_id == "LL")
    assert total == pytest.approx(p.span_m * p.length_m * p.roof_loads.live_kn_m2)


@pytest.mark.parametrize("extension,kind", [
    (BuildingExtensions(lean_to_left=SideLeanTo(enabled=True, base="fixed")), "lean_rafter"),
    (BuildingExtensions(canopy_right=SideCanopy(enabled=True)), "canopy"),
    (BuildingExtensions(roof_ext_left=SideRoofExtension(enabled=True)), "roof_extension"),
    (BuildingExtensions(roof_monitor=RoofMonitorInput(enabled=True)), "monitor_rafter"),
])
def test_extensions_are_connected_and_analyzed(warehouse_params, section_db, extension, kind):
    result = run_pipeline(replace(warehouse_params, extensions=extension),
                          options=PipelineOptions(run_design=False, export_plane=True), section_db=section_db)
    assert result.analysis_ok, result.model.analysis.message
    assert any(m.member_type == kind for m in result.model.members.values())
    assert len({tuple(round(v, 7) for v in n.coords) for n in result.model.nodes.values()}) == len(result.model.nodes)
    if kind == "lean_rafter":
        assert all(s.support_type.value == "fixed" for i, s in result.model.supports.items() if result.model.nodes[i].x < 0)


def test_mezzanine_joins_main_column_and_floor_load_is_conserved(warehouse_params, section_db):
    lv = MezzanineLevel(height_m=3, width_m=10, col_spacings_m=(5, 5), joist_spacing_m=1)
    p = replace(warehouse_params, mezzanine=MezzanineInput(enabled=True, levels=(lv,)))
    model = generate_peb_model(p)
    assign_defaults(model)
    apply_loads(model, section_db=section_db)
    nid = next(n.id for n in model.nodes.values() if n.coords == (0, 3, 0))
    incident = [m for m in model.members.values() if nid in (m.start_node, m.end_node)]
    assert {"column", "mezzanine_beam"} <= {m.member_type for m in incident}
    total = sum(-l.fy_kn_m * math.dist(model.nodes[model.members[l.member_id].start_node].coords,
                                     model.nodes[model.members[l.member_id].end_node].coords)
                for l in model.member_loads if l.load_case_id == "LL" and model.members[l.member_id].member_type == "mezzanine_beam")
    assert total == pytest.approx(lv.live_kn_m2 * lv.width_m * p.length_m)


def test_wind_factors_and_user_seismic_reach_export(warehouse_params, section_db):
    ws = WindSeismicInput(k1_risk=1.1, k2_override=1.2, k3_topography=1.3, k4_importance=1.4,
                          seismic_ah=.12, wind_roof_uplift_kn_m2=.6)
    result = run_pipeline(replace(warehouse_params, wind_seismic=ws),
                          options=PipelineOptions(run_analysis=False, run_design=False, export_plane=True), section_db=section_db)
    wind = result.model.metadata["load_engine"]["wind"]
    assert wind["pz"] == pytest.approx(.0006 * (ws.wind_speed_mps*1.1*1.2*1.3*1.4)**2)
    shear = result.model.metadata["seismic_user"]["base_shear_kn"]
    assert sum(l.fx_kn for l in result.model.nodal_loads if l.load_case_id == "EX+") == pytest.approx(shear)
    assert sum(l.fx_kn for l in result.model.nodal_loads if l.load_case_id == "EX-") == pytest.approx(-shear)
    assert "JOINT LOAD" in result.staad_text and "SEISMIC" in result.staad_text
    assert "USER NET ROOF UPLIFT" in result.staad_text
    assert "DEFINE ENVELOPE" in result.staad_text


def test_export_materials_builtup_and_every_load_axis(assigned_model, section_db):
    assign_defaults(assigned_model, column_section="BU 400x200x6x10")
    assigned_model.load_cases["USER"] = LoadCase("USER", "USER POINT", "other")
    assigned_model.nodal_loads.append(NodalLoad(1, "USER", 2, -3, 4))
    assigned_model.member_loads.append(MemberUniformLoad(1, "USER", fz_kn_m=5))
    text = build_staad_std_text(assigned_model, section_db=section_db)
    assert "TABLE ST BU" not in text
    assert "TAPERED 0.4 0.006 0.4 0.2 0.01 0.2 0.01" in text
    assert "ISOTROPIC STEEL" in text and "MATERIAL STEEL ALL" in text
    assert "STRENGTH FY 350000 FU 490000" in text
    assert "1 FX 2 FY -3 FZ 4" in text and "1 UNI GZ 5" in text
    assert "TITLE USER POINT" in text
    assert "PERFORM ANALYSIS PRINT STATICS CHECK" in text
    assert max(map(len, text.splitlines())) <= 79


def test_plane_export_contains_one_frame_and_matches_preview(warehouse_params, section_db, qapp):
    r = run_pipeline(warehouse_params, options=PipelineOptions(export_plane=True, run_design=False), section_db=section_db)
    assert r.staad_text.startswith("STAAD PLANE")
    frame = extract_transverse_frame(r.model, r.model.metadata["export_frame_z"])
    assert all(n.z == 0 for n in frame.nodes.values())
    assert all(m.member_type not in ("purlin", "girt") for m in frame.members.values())
    assert len(frame.members) < len(r.model.members)
    widget = FramePreview2D()
    widget.set_model(r.model)
    assert not widget.render_to_image(900, 440).isNull()


def test_staad_secondary_specifications_do_not_release_portal(warehouse_params, section_db):
    pinned = run_pipeline(warehouse_params, options=PipelineOptions(run_analysis=False,
        run_design=False, secondary_connection="pinned"), section_db=section_db)
    text = pinned.staad_text
    assert "MEMBER RELEASE\n" in text
    assert "START MY MZ" in text and "END MY MZ" in text
    assert "ISOTROPIC STEEL" in text and "ISOTROPIC E350" not in text
    property_block = text.split("MEMBER PROPERTY INDIAN\n", 1)[1].split("DEFINE MATERIAL START", 1)[0]
    assert property_block.count("TABLE ST") == 3
    from app.export.staad_import import parse_staad_std, _preprocess, _expand_ids
    imported = parse_staad_std(text)
    assert len(imported.members) == len(pinned.model.members)
    releases = text.split("MEMBER RELEASE\n", 1)[1].split("SUPPORTS", 1)[0]
    start_line = next(line for line in _preprocess(releases) if "START MY MZ" in line)
    released_ids = set(_expand_ids(start_line.split("START", 1)[0].split()))
    assert released_ids == {m.id for m in pinned.model.member_list() if m.member_type in ("purlin", "girt")}
    rigid = run_pipeline(warehouse_params, options=PipelineOptions(run_analysis=False,
        run_design=False, secondary_connection="rigid"), section_db=section_db)
    assert "MEMBER RELEASE\n" not in rigid.staad_text


def test_serviceability_limits_change_utilization(warehouse_params, section_db):
    options = PipelineOptions(run_design=True)
    normal = run_pipeline(warehouse_params, options=options, section_db=section_db)
    strict = run_pipeline(replace(warehouse_params, deflection_limits=DeflectionLimits(rafter_total_load_L_over=240)), options=options, section_db=section_db)
    def maximum(result):
        return max(c.utilization for r in result.model.design_results.values() for c in r.checks if c.name == "Rafter total deflection")
    assert maximum(strict) == pytest.approx(2 * maximum(normal))


def test_unsupported_code_never_runs_lsd_design(warehouse_params, section_db):
    r = run_pipeline(replace(warehouse_params, load_combination_type="IS800-2007-WSD"), section_db=section_db)
    assert not r.model.design_results
    assert all(c.source == "Serviceability" for c in r.model.combinations.values())
    assert "CODE IS800 LSD" not in r.staad_text


def test_unstable_model_is_not_solved_with_least_squares(assigned_model, section_db):
    assigned_model.supports.clear()
    result = DirectStiffness2DEngine(section_db).analyze(assigned_model)
    assert result.status == "error"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_wind_input_is_rejected(warehouse_params, value):
    with pytest.raises(ValueError):
        generate_peb_model(replace(warehouse_params, wind_seismic=WindSeismicInput(k2_override=value)))


def test_main_window_exports_current_revision_and_retains_import_text(qapp, monkeypatch, tmp_path):
    # VTK needs a desktop OpenGL context; substitute only that widget so actual
    # Qt signals, input panel, pipeline, preview and file actions are exercised.
    from PySide6.QtWidgets import QWidget
    from app.gui import main_window as module
    class Viewer(QWidget):
        def clear(self): pass
        def display_model(self, model): self.model = model
        def select_member(self, mid): pass
        def reset_camera(self): pass
    monkeypatch.setattr(module, "StructuralViewer3D", Viewer)
    monkeypatch.setattr(module.QMessageBox, "information", lambda *a: None)
    w = module.MainWindow()
    try:
        w.input_panel.run_analysis_cb.setChecked(False)
        w.input_panel.run_design_cb.setChecked(False)
        assert w.input_panel.flush_update()
        w.input_panel.width_edit.setText("32")
        assert not w._staad_text
        out = tmp_path / "live.std"
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *a: (str(out), ""))
        w._export_staad()
        assert w._model.metadata["span_m"] == 32
        assert out.read_text() == w._staad_text
        assert w._staad_text.startswith("STAAD PLANE")
        w._clear_staad_output()
        w._export_staad()
        assert out.stat().st_size > 100
        original = out.read_text() + "* retain this unsupported command/comment\n"
        out.write_text(original)
        monkeypatch.setattr(module.QFileDialog, "getOpenFileName", lambda *a: (str(out), ""))
        w._import_staad()
        assert not w.input_panel._live_timer.isActive()
        assert w.preview_2d._analytical_model is w._model
        assert "STAAD reference audit" in w.audit_panel.toPlainText()
        assert not w.loads_cb.isEnabled()
        assert not w.preview_2d.render_to_image().isNull()
        w._export_staad()
        assert out.read_text() == original
        w.input_panel.width_edit.setText("34")
        w._export_staad()
        assert w._model.metadata["span_m"] == 34
        assert w.loads_cb.isEnabled()
        assert out.read_text() != original
    finally:
        w.input_panel._live_timer.stop()
        w.close()
