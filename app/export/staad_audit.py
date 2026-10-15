"""Reviewable native input / result audit, also used by the desktop workspace."""
from __future__ import annotations

from collections import Counter
from app.core.models import StructuralModel

BENTLEY_REPEAT_LOAD = "https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0113645"


def audit_staad_model(model: StructuralModel) -> dict:
    native = model.metadata.get("staad_native")
    if not native:
        return {"findings": list(model.metadata.get("audit_warnings", []))}
    findings = list(model.metadata.get("audit_warnings", []))
    tension = [i for i, spec in native["specifications"].items() if spec.get("tension")]
    releases = [i for i, spec in native["specifications"].items() if spec.get("releases")]
    checked = set(native["checked_members"])
    unchecked = sorted(set(model.members) - checked)
    if tension and model.combinations:
        findings.append("Tension-only members are combined using LOAD COMB. Superposition does not re-evaluate active braces under simultaneous loads; engineer review and REPEAT LOAD cases are required.")
    second_order = any(c.upper().startswith("PDELTA") for c in native["analysis_commands"])
    if not second_order:
        findings.append("No PDELTA command found. Review second-order requirements and the ANL amplification warnings.")
    for combo in model.combinations.values():
        for case, factor in combo.factors.items():
            if abs(factor) > 3:
                findings.append(f"Combination {combo.id} ({combo.name}): case {case} factor {factor:g} is unusually large. Verify against the intended combination; original value is preserved.")
    for case in model.load_cases.values():
        title = case.name.upper().strip()
        expected = "dead" if title == "DL" or title.startswith("DEAD") else "live" if title == "LL" or title.startswith("LIVE") else "wind" if title.startswith(("WL", "WIND")) else None
        if expected and case.load_type != expected:
            findings.append(f"Load {case.id} '{case.name}' is labelled {case.load_type}, although its title suggests {expected}.")
    if unchecked:
        findings.append(f"{len(unchecked)} members are outside CHECK CODE: " + ", ".join(map(str, unchecked)) + ". These are unchecked, not passing.")
    if not any("DFF" in p for p in native["design_parameters"].values()):
        findings.append("No native DFF deflection check is defined. Serviceability envelopes alone do not check deflection limits.")
    missing_properties = sorted(set(model.members) - set(native["properties"]))
    missing_materials = [i for i, m in model.members.items() if not m.material]
    if missing_properties: findings.append(f"Missing readable section assignments: {missing_properties}")
    if missing_materials: findings.append(f"Missing material assignments: {missing_materials}")
    if native["untranslated"]:
        findings.append(f"{len(native['untranslated'])} untranslated commands are retained in the native STD; inspect the preserved input.")
    if native["loads"]:
        findings.append("Native load diagrams are not drawn in the app. Explicit global member/joint forces are parsed; local-axis, selfweight and generated seismic loads remain native. View complete loading in STAAD.Pro; the original commands are retained in STAAD output.")
    results = model.metadata.get("staad_results", {})
    for w in results.get("warnings", []): findings.append("STAAD output: " + w)
    fail = [i for i, r in model.design_results.items() if r.status == "FAIL"]
    passed = [i for i, r in model.design_results.items() if r.status == "PASS"]
    worst = max(model.design_results.values(), key=lambda r: r.max_utilization, default=None)
    return {"source": model.metadata["imported_from"],
            "nodes": len(model.nodes), "members": len(model.members), "supports": len(model.supports),
            "primary_load_cases": len(model.load_cases), "combinations": len(model.combinations),
            "property_members": dict(Counter(p["kind"] for p in native["properties"].values())),
            "released_members": len(releases), "tension_members": len(tension),
            "material_assignments": dict(Counter(m.material or "UNASSIGNED" for m in model.members.values())),
            "checked_member_count": len(checked), "unchecked_members": unchecked,
            "result_source": results.get("source"), "results_attached": results.get("attached", False),
            "pass_count": len(passed), "fail_count": len(fail), "failed_members": sorted(fail),
            "worst_member": worst.member_id if worst else None, "worst_ratio": worst.max_utilization if worst else None,
            "findings": findings, "repeat_load_reference": BENTLEY_REPEAT_LOAD}


def format_staad_audit(model: StructuralModel) -> str:
    audit = audit_staad_model(model)
    if "source" not in audit:
        return "Generated model review\n\n" + "\n\n".join(audit["findings"])
    lines = ["STAAD reference audit", f"Source: {audit['source']}",
             "Native input retained. Imported results are not recalculated by the app.",
             "Sidebar controls describe generated models; changing them starts a generated model, not a resized reference.", "",
             f"{audit['nodes']} nodes | {audit['members']} members | {audit['supports']} supports",
             f"{audit['primary_load_cases']} primary loads | {audit['combinations']} combinations",
             f"Sections: {audit['property_members']}", f"Materials: {audit['material_assignments']}",
             f"Released members: {audit['released_members']} | Tension-only: {audit['tension_members']}"]
    if audit["results_attached"]:
        lines += [f"Matching ANL: {audit['result_source']}",
                  f"PASS: {audit['pass_count']} | FAIL: {audit['fail_count']} | No result: {len(model.members)-len(model.design_results)}",
                  f"Worst: member {audit['worst_member']}, ratio {audit['worst_ratio']:.3f}",
                  "Failed members: " + ", ".join(map(str, audit["failed_members"]))]
    else:
        lines.append("No matching, completed ANL results attached.")
    lines += ["", "Review findings:"] + [f"- {f}" for f in audit["findings"]]
    lines += ["", "Native load cases (declared type):"]
    lines += [f"{c.id}: {c.name} [{c.load_type}]" for c in model.load_cases.values()]
    lines += ["", "Native combinations (case: factor):"]
    lines += [f"{c.id}: {c.name} | {c.factors} | {c.source}" for c in model.combinations.values()]
    native = model.metadata["staad_native"]
    lines += ["", "Load definitions:", *native["definitions"], "", "Analysis commands:", *native["analysis_commands"],
              "", "Bentley explanation of repeat loads:", BENTLEY_REPEAT_LOAD]
    return "\n".join(lines)


def main() -> None:
    import argparse
    import json
    from pathlib import Path
    from app.export.staad_import import import_staad_std
    from app.export.staad import export_staad_std
    parser = argparse.ArgumentParser(description="Audit a STAAD reference and its matching ANL without changing the original.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = import_staad_std(args.input)
    report = audit_staad_model(model)
    (args.output_dir / "audit.txt").write_text(format_staad_audit(model), encoding="utf-8")
    (args.output_dir / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    export_staad_std(model, args.output_dir / (args.input.stem + "_PRESERVED.std"))
    print(f"Audited {report['members']} members; native results: {report['pass_count']} PASS, {report['fail_count']} FAIL. Reports: {args.output_dir}")


if __name__ == "__main__":
    main()
