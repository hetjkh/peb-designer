"""End-to-end structural pipeline: geometry → assign → loads → analyze → design."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.analysis.engine import AnalysisEngine, get_default_engine
from app.core.assign import assign_defaults
from app.core.models import StructuralModel, SupportType
from app.core.preferences import get_preferences
from app.database.sections import SectionDatabase
from app.design.is800 import design_model
from app.export.staad import build_staad_std_text
from app.geometry.peb_frame import BuildingGeometryInput, generate_peb_model
from app.geometry.connectivity import add_secondary_members
from app.geometry.validation import ValidationError
from app.loads.engine import LoadEngineConfig, apply_loads


@dataclass
class PipelineOptions:
    column_section: str = "ISMB 400"
    rafter_section: str = "ISMB 350"
    material: str = "E350"
    support_type: SupportType = SupportType.PINNED
    run_analysis: bool = True
    run_design: bool = True
    design_code: str = "IS800-2007-LSD"
    staad_version: str = "STAAD.Pro CONNECT Edition"
    purlin_spacing_m: float = 1.5
    girt_spacing_m: float = 1.5
    export_plane: bool = False
    secondary_connection: str = "pinned"
    staad_analysis: str = "linear"  # linear | pdelta (native export only)
    pdelta_iterations: int = 20


@dataclass
class PipelineResult:
    model: StructuralModel
    staad_text: str
    analysis_ok: bool
    design_summary: str


def run_pipeline(
    params: BuildingGeometryInput,
    *,
    options: Optional[PipelineOptions] = None,
    engine: Optional[AnalysisEngine] = None,
    section_db: Optional[SectionDatabase] = None,
) -> PipelineResult:
    prefs = get_preferences()
    options = options or PipelineOptions(
        support_type=prefs.support_type(),
        design_code=prefs.design_code,
        staad_version=prefs.staad_version,
        purlin_spacing_m=prefs.purlin_spacing_m,
        girt_spacing_m=prefs.girt_spacing_m,
    )
    section_db = section_db or SectionDatabase()
    if engine is None:
        from app.analysis.engine import DirectStiffness2DEngine
        engine = DirectStiffness2DEngine(section_db=section_db)

    import math
    if any(not math.isfinite(v) or v <= 0 for v in (options.purlin_spacing_m, options.girt_spacing_m)):
        raise ValidationError(["Purlin and girt spacing must be positive finite numbers."])
    if options.secondary_connection not in ("pinned", "rigid"):
        raise ValidationError(["Secondary connection must be pinned or rigid."])
    if options.staad_analysis not in ("linear", "pdelta"):
        raise ValidationError(["STAAD analysis must be linear or pdelta."])
    if type(options.pdelta_iterations) is not int or not 1 <= options.pdelta_iterations <= 100:
        raise ValidationError(["P-Delta iterations must be an integer from 1 to 100."])

    model = generate_peb_model(params)
    add_secondary_members(model, options.purlin_spacing_m, options.girt_spacing_m)
    assign_defaults(
        model,
        column_section=options.column_section,
        rafter_section=options.rafter_section,
        material=options.material,
        support_type=options.support_type,
    )
    apply_loads(model, config=LoadEngineConfig(), section_db=section_db)

    model.metadata["design_code"] = options.design_code
    model.metadata["load_combination_type"] = model.metadata.get(
        "load_combination_type", options.design_code
    )
    # Prefer geometry-input load combo if present
    if hasattr(params, "load_combination_type") and params.load_combination_type:
        model.metadata["load_combination_type"] = params.load_combination_type
        model.metadata["design_code"] = params.load_combination_type
    if hasattr(params, "deflection_limits") and params.deflection_limits:
        model.metadata["deflection_limits"] = params.deflection_limits.to_dict()
    model.metadata["staad_version"] = options.staad_version
    model.metadata["export_design"] = options.run_design
    model.metadata["purlin_spacing_m"] = options.purlin_spacing_m
    model.metadata["girt_spacing_m"] = options.girt_spacing_m
    model.metadata["secondary_connection"] = options.secondary_connection
    model.metadata["staad_analysis"] = options.staad_analysis
    model.metadata["pdelta_iterations"] = options.pdelta_iterations
    model.metadata["ext_col_base"] = options.support_type.value
    if options.export_plane:
        from app.loads.engine import tributary_widths
        widths = tributary_widths(model)
        model.metadata["export_frame_z"] = max(widths, key=widths.get)
    try:
        from app.database.plate_catalog import get_plate_catalog

        cat = get_plate_catalog()
        model.metadata["plate_catalog"] = {
            "web_depths_mm": list(cat.web_depths_mm),
            "web_thicknesses_mm": list(cat.web_thicknesses_mm),
            "flange_widths_mm": list(cat.flange_widths_mm),
            "flange_thicknesses_mm": list(cat.flange_thicknesses_mm),
        }
    except Exception:
        pass

    analysis_ok = False
    if options.run_analysis:
        model.analysis = engine.analyze(model)
        analysis_ok = model.analysis.status == "ok"

    design_summary = "Design not run"
    # Design engine currently implements IS 800 LSD checks only.
    run_is800 = options.run_design and model.metadata["design_code"] == "IS800-2007-LSD"
    if options.run_design and not run_is800:
        design_summary = (
            f"Design skipped — '{options.design_code}' not implemented yet "
            "(IS800-* supported)."
        )
    elif run_is800 and analysis_ok:
        results = design_model(model, section_db=section_db)
        n_pass = sum(1 for r in results.values() if r.status == "PASS")
        n_fail = sum(1 for r in results.values() if r.status == "FAIL")
        max_u = max((r.max_utilization for r in results.values()), default=0.0)
        design_summary = (
            f"Members designed: {len(results)} | PASS: {n_pass} | FAIL: {n_fail} | "
            f"max util: {max_u:.2f} | code: {options.design_code}"
        )
    elif options.run_design and not analysis_ok:
        design_summary = "Design skipped — analysis failed"

    model.metadata["audit_warnings"].append(
        "Internal analysis is transverse 2D only; longitudinal members transfer self-weight as end reactions. Full 3D stability is not checked."
    )
    model.metadata["audit_warnings"].append(
        "Design checks are preliminary: section classification, lateral torsional buckling, physical bracing and continuous deflection envelopes require independent checks."
    )
    if options.staad_analysis == "pdelta":
        model.metadata["audit_warnings"].append(
            "STAAD export uses P-Delta with repeat loads. App results remain first-order 2D; run the STD in STAAD and check displacement/iteration convergence before using its results."
        )
    if options.run_design:
        model.metadata["audit_warnings"].append(
            "Native primary-member LX/LY/LZ use full physical member lengths, not mesh segment lengths. Actual lateral restraints and effective-length factors need engineer review. Native DFF deflection checks are not yet exported."
        )
    staad = build_staad_std_text(model, title="PEB Designer export", section_db=section_db)
    return PipelineResult(
        model=model,
        staad_text=staad,
        analysis_ok=analysis_ok,
        design_summary=design_summary,
    )
