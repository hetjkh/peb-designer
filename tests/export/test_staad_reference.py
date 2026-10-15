"""Import real native features, preserve source and reject unsafe result reuse."""
from dataclasses import replace
from pathlib import Path
import os

import pytest

from app.analysis.engine import DirectStiffness2DEngine
from app.core.pipeline import PipelineOptions, run_pipeline
from app.design.is800 import design_model
from app.export.staad import build_staad_std_text
from app.export.staad_audit import audit_staad_model, format_staad_audit
from app.export.staad_import import _expand_ids, import_staad_std, parse_staad_std, statements
from app.export.staad_results import attach_staad_results


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


REFERENCE = """STAAD SPACE
UNIT METER KN
JOINT COORDINATES
1 0 0 0
2 0 5 0; 3 5 6 0
4 5 0 0
MEMBER INCIDENCES
1 1 2; 2 2 3
3 4 3
DEFINE MATERIAL START
ISOTROPIC STEEL
E 2.05e8
POISSON 0.3
DENSITY 76.8195
TYPE STEEL
END DEFINE MATERIAL
MEMBER PROPERTY AMERICAN
1 3 TAPERED 0.47 0.006 0.47 0.2 0.01 0.2 0.01
MEMBER PROPERTY TATASTRUCTURA
2 TABLE ST 150X150X4.0SHS
CONSTANTS
BETA 90 MEMB 1
MATERIAL STEEL ALL
MEMBER TENSION
2
MEMBER RELEASE
2 START MY MZ
2 END MY MZ
SUPPORTS
1 FIXED BUT MZ
4 PINNED
DEFINE 1893 LOAD
ZONE 0.16 RF 4 I 1.2 SS 2 ST 2 DM 0.05
SELFWEIGHT 1.5
LOAD 1 LOADTYPE Seismic TITLE EL X+
1893 LOAD X 1
PERFORM ANALYSIS
CHANGE
LOAD 3 LOADTYPE Seismic TITLE DL
SELFWEIGHT Y -1.15
MEMBER LOAD
2 UNI GY -3
2 UNI Y -1
JOINT LOAD
3 FX 2 FY -5 FZ 3
LOAD COMB 118 0.9 DL + 1.5ELX+
3 0.9 1 11.5
PERFORM ANALYSIS PRINT ALL
DEFINE ENVELOPE
118 ENVELOPE 1 TYPE STRENGTH
END DEFINE ENVELOPE
PARAMETER 1
CODE IS800 LSD
FYLD 345000 MEMB 1 3
LX 1.5 MEMB 1 3
LZ 5 MEMB 1 3
STP 2 MEMB 1 3
TRACK 2 ALL
LOAD LIST 118
CHECK CODE MEMB 1 3
FINISH
"""


def write_anl(path, source, results=None, finished=True):
    echo = "\n".join(f"{i}. {line.rstrip(';')}" for i, line in enumerate(source.splitlines(), 1))
    # TRACK 2 repeats member headers on subsequent pages. Use the closest
    # preceding header; never let a multiline regex cross into another member.
    results = results or """
| Member Number: 1 |
| Member Section: TAP ERED |
\f STAAD SPACE -- PAGE NO. 2
| Member Number: 1 |
| Status: FAIL Ratio: 2.456 Critical Load Case: 118 Location: 0.00 |
| Critical Condition: Sec. 9.3.1.1 |
| Member Number: 3 |
| Status: PASS Ratio: 0.712 Critical Load Case: 118 Location: 5.00 |
| Critical Condition: Sec. 9.3.1.3 |
"""
    path.write_text(echo + "\n" + results + ("\nEND OF THE STAAD.Pro RUN" if finished else ""))


def test_reference_assignments_loads_and_lossless_export():
    m = parse_staad_std(REFERENCE)
    assert len(m.nodes) == 4 and len(m.members) == 3
    assert all(v.material == "STEEL" for v in m.members.values())
    native = m.metadata["staad_native"]
    assert native["properties"][1]["dimensions_m"]["depth_start"] == .47
    assert native["properties"][2]["table"] == "TATASTRUCTURA"
    assert native["materials"]["STEEL"]["E_kn_m2"] == 205e6
    assert native["specifications"][1]["beta_deg"] == 90
    assert native["specifications"][2] == {"tension": True, "releases": {"START": "MY MZ", "END": "MY MZ"}}
    assert m.supports[1].rx and m.supports[1].ry and not m.supports[1].rz
    assert m.supports[4].uy and not m.supports[4].rx
    assert len(m.member_loads) == 1 and m.member_loads[0].fy_kn_m == -3
    assert len(m.nodal_loads) == 1 and m.nodal_loads[0].fz_kn == 3
    assert any(r["command"] == "2 UNI Y -1" and not r["represented"] for r in native["loads"]["3"])
    assert m.combinations["118"].factors == {"3": .9, "1": 11.5}
    assert native["design_parameters"][1]["FYLD"]["value_si"] == 345000
    assert "eave_height_m" not in m.metadata  # ridge is not an eave
    assert build_staad_std_text(m) == REFERENCE
    audit = audit_staad_model(m)
    assert audit["unchecked_members"] == [2]
    assert any("11.5" in f for f in audit["findings"])
    assert any("LOAD COMB" in f for f in audit["findings"])
    assert any("labelled seismic" in f for f in audit["findings"])


def test_units_and_unit_changes_convert_coordinates_forces_and_parameters():
    s = REFERENCE.replace("UNIT METER KN", "UNIT FEET KIP").replace("PARAMETER 1", "UNIT MM NEWTON\nPARAMETER 1")
    m = parse_staad_std(s)
    assert m.nodes[2].y == pytest.approx(1.524)
    assert m.member_loads[0].fy_kn_m == pytest.approx(-3*4.4482216152605/.3048)
    assert m.nodal_loads[0].fx_kn == pytest.approx(2*4.4482216152605)
    assert m.metadata["staad_native"]["design_parameters"][1]["LX"]["value_si"] == .0015
    assert build_staad_std_text(m) == s


@pytest.mark.parametrize("old,new", [("UNIT METER KN", "UNIT FURLONG KN"),
    ("1 1 2;", "1 1 99;"), ("1 0 0 0", "1 NaN 0 0"),
    ("1 0 0 0", "1 0 0 0; 1 1 1 1")])
def test_bad_geometry_and_units_are_not_silently_dropped(old, new):
    with pytest.raises(ValueError): parse_staad_std(REFERENCE.replace(old, new))


def test_by_ranges():
    assert _expand_ids("1 TO 7 BY 2 9".split()) == [1, 3, 5, 7, 9]
    with pytest.raises(ValueError): _expand_ids("1 TO 5 BY 0".split())


def test_springs_do_not_turn_stiffness_values_into_support_ids():
    m = parse_staad_std(REFERENCE.replace("1 FIXED BUT MZ", "1 FIXED BUT KFX 1000"))
    assert 1 not in m.supports
    assert "1 FIXED BUT KFX 1000" in m.metadata["staad_native"]["untranslated"]
    assert "1 FIXED BUT KFX 1000" in build_staad_std_text(m)


def test_native_model_cannot_enter_partial_solver_or_overwrite_results(section_db):
    m = parse_staad_std(REFERENCE)
    assert DirectStiffness2DEngine(section_db).analyze(m).status == "unsupported"
    with pytest.raises(ValueError, match="native"): design_model(m, section_db=section_db)
    m.nodes[2] = replace(m.nodes[2], y=8)
    with pytest.raises(ValueError, match="changed"): build_staad_std_text(m)


def test_matching_anl_tracks_real_member_ids_and_source(tmp_path):
    std = tmp_path / "native.STD"
    std.write_text(REFERENCE)
    write_anl(std.with_suffix(".ANL"), REFERENCE)
    m = import_staad_std(std)
    assert m.metadata["staad_results"]["attached"]
    assert m.analysis.status == "external" and not m.analysis.member_forces
    assert set(m.design_results) == {1, 3}
    assert m.design_results[1].status == "FAIL" and m.design_results[1].max_utilization == 2.456
    assert m.design_results[3].status == "PASS"
    assert "118" in m.design_results[1].checks[0].detail
    assert audit_staad_model(m)["fail_count"] == 1
    assert build_staad_std_text(m) == REFERENCE


@pytest.mark.parametrize("reason", ["stale", "truncated", "error", "mutated"])
def test_bad_anl_never_colors_members_as_passed(tmp_path, reason):
    m = parse_staad_std(REFERENCE)
    path = tmp_path / "native.ANL"
    s = REFERENCE.replace("1 11.5", "1 1.5") if reason == "stale" else REFERENCE
    write_anl(path, s, finished=reason != "truncated")
    if reason == "error": path.write_text(path.read_text()+"\n***ERROR MODEL UNSTABLE\n")
    if reason == "mutated": m.nodes[2] = replace(m.nodes[2], y=8)
    assert not attach_staad_results(m, path)
    assert not m.design_results


def test_native_status_not_reclassified_using_app_threshold(tmp_path):
    m = parse_staad_std(REFERENCE.replace("TRACK 2 ALL", "RATIO 1.3 ALL\nTRACK 2 ALL"))
    path = tmp_path / "native.ANL"
    write_anl(path, m.metadata["staad_native"]["source_text"],
        "Member Number: 1\nStatus: PASS Ratio: 1.2 Critical Load Case: 118 Location: 0.0\n")
    assert attach_staad_results(m, path)
    assert m.design_results[1].status == "PASS"


def test_provided_project_reference_has_expected_coverage_and_failures():
    path = Path(__file__).resolve().parents[2] / "without optimization" / "Project 1.STD"
    if not path.exists(): pytest.skip("User-supplied integration reference is not installed")
    m = import_staad_std(path)
    audit = audit_staad_model(m)
    assert (audit["nodes"], audit["members"], audit["supports"]) == (164, 298, 38)
    assert (audit["primary_load_cases"], audit["combinations"]) == (8, 32)
    assert audit["property_members"] == {"TAPERED": 154, "PRIS": 60, "TABLE": 84}
    assert audit["released_members"] == 91 and audit["tension_members"] == 60
    assert (audit["pass_count"], audit["fail_count"], len(audit["unchecked_members"])) == (171, 64, 63)
    assert (audit["worst_member"], audit["worst_ratio"]) == (154, 6.995)
    assert not m.metadata["staad_native"]["untranslated"]
    assert build_staad_std_text(m) == path.read_text()


def test_second_order_export_preserves_every_combination_factor(warehouse_params, section_db):
    r = run_pipeline(warehouse_params, options=PipelineOptions(run_analysis=False, run_design=True,
        export_plane=True, staad_analysis="pdelta", column_section="BU 400x200x6x10"), section_db=section_db)
    s = r.staad_text
    assert "LOAD COMB " not in s
    assert "PDELTA 20 ANALYSIS SMALLDELTA PRINT STATICS CHECK" in s
    assert s.count("REPEAT LOAD") == len(r.model.combinations)
    imported = parse_staad_std(s)
    cases = sorted(r.model.load_cases)
    repeat = imported.metadata["staad_native"]["repeat_loads"]
    for number, combo in enumerate(r.model.combinations.values(), 100):
        expected = {str(cases.index(k)+1): v for k, v in combo.factors.items()}
        tokens = repeat[str(number)].split()
        assert {tokens[i]: float(tokens[i+1]) for i in range(0, len(tokens), 2)} == expected
    native = imported.metadata["staad_native"]
    assert all(mid in imported.members for mid in native["checked_members"])
    for mid in native["checked_members"]:
        p = native["design_parameters"][mid]
        assert p["TRACK"]["value"] == 2 and p["BEAM"]["value"] == 1
        assert p["STP"]["value"] == (2 if imported.members[mid].section.startswith("TAPERED") else 1)
        assert p["LX"]["value"] == pytest.approx(r.model.metadata["physical_member_lengths_m"][mid])
    assert max(map(len, s.splitlines())) <= 79


@pytest.mark.parametrize("iterations", [0, 101, 1.5, float("nan")])
def test_invalid_iterations_rejected(warehouse_params, section_db, iterations):
    with pytest.raises(ValueError):
        run_pipeline(warehouse_params, options=PipelineOptions(pdelta_iterations=iterations), section_db=section_db)


def test_reference_inspector_and_2d_slice(qapp):
    from app.gui.widgets.member_info_panel import MemberInfoPanel
    from app.gui.widgets.frame_preview_2d import FramePreview2D
    m = parse_staad_std(REFERENCE)
    widget = MemberInfoPanel()
    widget.show_member(m, 1)
    text = widget.body.toPlainText()
    assert "345000 kN/m2" in text and "470 mm" in text and "90" in text
    preview = FramePreview2D()
    preview.set_model(m, station=0)
    assert not preview.render_to_image().isNull()
    assert "Reference" in format_staad_audit(m) or "reference" in format_staad_audit(m)
