"""Create reproducible STAAD.Pro CONNECT files through the app's input panel."""

from __future__ import annotations

import json
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.core.preferences import AppPreferences
from app.export.staad import export_staad_std
from app.export.staad_import import parse_staad_std
from app.gui.widgets.building_input_panel import BuildingInputPanel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("staad_test"))
    parser.add_argument("--revision", default="v2")
    parser.add_argument("--staad-analysis", choices=("linear", "pdelta"), default="linear")
    args = parser.parse_args()
    if not args.revision.replace("_", "").isalnum():
        parser.error("Revision must contain only letters, numbers or underscores")
    app = QApplication.instance() or QApplication([])
    panel = BuildingInputPanel()
    panel.apply_preferences(AppPreferences(), reset_geometry=True)
    panel.staad_analysis_combo.setCurrentIndex(panel.staad_analysis_combo.findData(args.staad_analysis))
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    records = []
    generated = []
    panel.model_generated.connect(lambda model, text: generated.append((model, text)))
    for filename, plane in ((f"PEB_CONNECT_2D_{args.revision}.std", True), (f"PEB_CONNECT_3D_{args.revision}.std", False)):
        panel.export_mode.setCurrentIndex(0 if plane else 1)
        if not panel._on_generate(automatic=True):
            raise RuntimeError(panel.status.text())
        model, preview_text = generated[-1]
        target = output / filename
        export_staad_std(model, target, title="PEB Designer export")
        contents = target.read_text(encoding="utf-8")
        if contents != preview_text:
            raise RuntimeError(f"Export disagrees with live STAAD panel: {filename}")
        imported = parse_staad_std(contents)
        expected_nodes = sum(abs(node.z - model.metadata["export_frame_z"]) < 1e-6
                             for node in model.nodes.values()) if plane else len(model.nodes)
        if len(imported.nodes) != expected_nodes:
            raise RuntimeError(f"Node round-trip failed: {filename}")
        records.append({
            "file": filename,
            "kind": "STAAD PLANE" if plane else "STAAD SPACE",
            "joints": len(imported.nodes),
            "members": len(imported.members),
            "primary_load_cases": len(model.load_cases),
            "load_combinations": len(model.combinations),
            "internal_analysis": model.analysis.status if model.analysis else "not run",
            "staad_analysis": args.staad_analysis,
            "note": "Bentley STAAD.Pro import and analysis still to be checked",
        })
        print(f"{filename}: {len(imported.nodes)} joints, {len(imported.members)} members")
    (output / "manifest.json").write_text(json.dumps({
        "source": "PEB Designer default sidebar input, STAAD.Pro CONNECT Edition",
        "geometry": {"width_m": 40, "length_m": 60, "eave_m": 6.5,
                     "roof_slope_x_to_10": 1, "bay_spacing_m": 7.5},
        "models": records,
    }, indent=2) + "\n", encoding="utf-8")
    panel._live_timer.stop()
    panel.close()
    del app


if __name__ == "__main__":
    main()
