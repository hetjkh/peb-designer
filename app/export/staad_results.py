"""Read native STAAD code-check summaries without presenting them as app results."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from app.core.models import AnalysisResults, CheckResult, MemberDesignResult, StructuralModel
from app.export.staad_import import model_fingerprint, statements


def _canonical(text: str) -> list[str]:
    return [" ".join(line.upper().split()) for line in statements(text)]


def attach_staad_results(model: StructuralModel, path: str | Path) -> bool:
    """Require a completed run and a complete, matching input echo (not filenames)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    echo_rows = re.findall(r"^\s*(\d+)\. (.*)$", text, re.M)
    consecutive = [int(n) for n, _ in echo_rows] == list(range(1, len(echo_rows)+1))
    echo = "\n".join(line for _, line in echo_rows)
    source = model.metadata["staad_native"]["source_text"]
    complete = "END OF THE STAAD.Pro RUN" in text
    try:
        matched = (bool(echo_rows) and consecutive and _canonical(echo) == _canonical(source)
                   and model_fingerprint(model) == model.metadata.get("staad_import_fingerprint"))
    except ValueError:
        matched = False
    errors = re.findall(r"^.*\*+\s*ERROR\b.*$", text, re.M | re.I)
    warnings = []
    for match in re.finditer(r"\*+WARNING[^\n]*(?:\n[^\n]+){0,4}", text):
        warnings.append(" ".join(match[0].split()))
    report = {"source": str(path), "sha256": hashlib.sha256(text.encode()).hexdigest(),
              "input_matches": matched, "completed": complete, "errors": errors,
              "warnings": warnings, "attached": False, "records": []}
    model.metadata["staad_results"] = report
    model.design_results.clear()
    model.analysis = AnalysisResults(status="not_run", message="Native results have not been attached.")
    if not matched or not complete or errors:
        reason = "input echo differs or is incomplete" if not matched else "run is incomplete or contains errors"
        report["reason"] = reason
        model.metadata["audit_warnings"].append(f"ANL results not attached: {reason} ({path.name}).")
        return False

    member, pending = None, None
    for line in text.splitlines():
        match = re.search(r"Member Number:\s*(\d+)", line)
        if match:
            member = int(match[1]); pending = None
        match = re.search(r"Status:\s*(PASS|FAIL)\s+Ratio:\s*([-+\d.Ee]+)\s+Critical Load Case:\s*(\d+)\s+Location:\s*([-+\d.Ee]+)", line)
        if match and member is not None:
            status, ratio, case, location = match.groups()
            pending = {"member_id": member, "status": status, "ratio": float(ratio),
                       "load_case": case, "location_native_units": float(location), "clause": ""}
            report["records"].append(pending)
        match = re.search(r"Critical Condition:\s*(.*?)\s*\|?\s*$", line)
        if match and pending is not None:
            pending["clause"] = match[1]
    unknown = {r["member_id"] for r in report["records"]} - set(model.members)
    if unknown or not report["records"]:
        report["reason"] = "No supported code-check summaries or unknown member IDs in ANL"
        model.metadata["audit_warnings"].append(report["reason"])
        return False
    for record in report["records"]:
        mid = record["member_id"]
        m = model.members[mid]
        result = model.design_results.setdefault(mid, MemberDesignResult(mid, m.section or "", m.material or ""))
        result.checks.append(CheckResult(
            "STAAD native code check", record["ratio"], record["status"],
            f"Load {record['load_case']}; {record['clause']}; location "
            f"{record['location_native_units']:g} (ANL length units). Source: {path.name}",
            "STAAD.Pro ANL (matching input; imported, not recalculated)"))
        # Native PASS/FAIL can include slenderness and an allowable RATIO other
        # than 1. Do not reclassify it with the app's simplified threshold.
        result.max_utilization = max(c.utilization for c in result.checks)
        result.status = "FAIL" if any(c.status == "FAIL" for c in result.checks) else "PASS"
    report["attached"] = True
    model.analysis = AnalysisResults(status="external", message="Code-check summaries imported from matching STAAD ANL; forces and displacements have not been imported or recalculated.")
    return True
