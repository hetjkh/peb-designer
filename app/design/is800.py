"""IS 800:2007 steel member design checks (simplified educational implementation).

IMPORTANT:
  - Formulas cite IS 800:2007 clauses below.
  - Several simplifying assumptions are stated explicitly.
  - Results are NOT certified for construction until validated by a qualified engineer.

Checks implemented:
  1) Tension (Clause 6.2) — Tdg = Ag fy / γ_m0
  2) Compression (Clause 7.1) — simplified Euler/IS buckling curve 'a' approx.
       fcd from χ fy / γ_m0 with χ from φ, λ_nd (Clause 7.1.2)
  3) Bending (Clause 8.2.1) — Md = βb Zp fy / γ_m0 with βb=1.0, Zp≈1.2 Ze (approx for rolled I)
  4) Shear (Clause 8.4) — Vd = Av fy / (√3 γ_m0)
  5) Combined (Clause 9.3.1) — interaction utilization

Assumptions (documented):
  - Section class treated as plastic/compact (βb = 1.0) — not computed from flanges/web.
  - Effective length factors Ky = Kz = 1.0 (pinned-pinned) unless metadata overrides.
  - Imperfection factor α = 0.21 (buckling curve a) for all members — conservative/simple.
  - Governing forces taken as max |N|, |V|, |M| across all combinations.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.core.models import CheckResult, MemberDesignResult, StructuralModel
from app.database.materials import get_material
from app.database.sections import SectionDatabase


def _member_length_m(model: StructuralModel, member_id: int) -> float:
    m = model.members[member_id]
    n0 = model.nodes[m.start_node]
    n1 = model.nodes[m.end_node]
    return math.sqrt((n1.x - n0.x) ** 2 + (n1.y - n0.y) ** 2 + (n1.z - n0.z) ** 2)


def _governing_forces(model: StructuralModel, member_id: int):
    if model.analysis is None:
        return 0.0, 0.0, 0.0, 0.0
    forces = model.analysis.forces_for_member(member_id)
    if not forces:
        return 0.0, 0.0, 0.0, 0.0
    n = max(f.n_max_abs for f in forces)
    v = max(f.v_max_abs for f in forces)
    m = max(f.m_max_abs for f in forces)
    n_signed = 0.0
    for f in forces:
        # End actions have opposite signs: tension = -N_start = N_end.
        n_signed = min(n_signed, -f.n_start_kn, f.n_end_kn)
    return n, v, m, n_signed


def _chi_buckling(lambda_nd: float, alpha: float = 0.21) -> float:
    """IS 800:2007 Eq. 7.1.2 — reduction factor χ."""
    if lambda_nd <= 0.2:
        return 1.0
    phi = 0.5 * (1.0 + alpha * (lambda_nd - 0.2) + lambda_nd**2)
    chi = 1.0 / (phi + math.sqrt(max(phi**2 - lambda_nd**2, 0.0)))
    return min(chi, 1.0)


def design_member(
    model: StructuralModel,
    member_id: int,
    *,
    section_db: Optional[SectionDatabase] = None,
    K: float = 1.0,
) -> MemberDesignResult:
    if model.metadata.get("requires_staad_analysis"):
        raise ValueError("Use native STAAD code checks for imported reference models.")
    section_db = section_db or SectionDatabase()
    member = model.members[member_id]
    result = MemberDesignResult(
        member_id=member_id,
        section=member.section or "—",
        material=member.material or "—",
    )
    if not member.section or not member.material:
        result.checks.append(
            CheckResult("Assignment", 0.0, "N/A", "Section/material not assigned")
        )
        result.finalize()
        return result

    try:
        sec = section_db.get(member.section)
        mat = get_material(member.material)
    except KeyError as exc:
        result.checks.append(CheckResult("Lookup", 0.0, "FAIL", str(exc)))
        result.finalize()
        return result

    forces = _governing_forces(model, member_id)
    n_abs, v_abs, m_abs, n_signed = forces

    L = model.metadata.get("physical_member_lengths_m", {}).get(member_id, _member_length_m(model, member_id))
    Ag = sec.area_cm2 * 1e2  # cm² → mm²
    fy = mat.fy_mpa
    gamma_m0 = mat.gamma_m0

    # --- Tension (Clause 6.2) — if axial tension ---
    Tdg = (Ag * fy) / gamma_m0 / 1000.0  # kN  (N→kN)
    if n_signed > 1e-6:  # tension if positive local axial (depends on sign convention)
        # Our FEM: compression often negative in local x for column under gravity.
        util_t = 0.0
        status_t = "N/A"
        detail_t = "No governing tension detected"
    else:
        # Check tension capacity anyway against |N| if any tension exists in combos
        util_t = 0.0
        status_t = "N/A"
        detail_t = f"Tdg={Tdg:.2f} kN (Clause 6.2)"
    # Re-evaluate tension from any positive N
    if model.analysis:
        tmax = 0.0
        for f in model.analysis.forces_for_member(member_id):
            tmax = max(tmax, -f.n_start_kn, f.n_end_kn)
        if tmax > 1e-6:
            util_t = tmax / Tdg if Tdg > 0 else 999.0
            status_t = "PASS" if util_t <= 1.0 else "FAIL"
            detail_t = f"T={tmax:.2f} / Tdg={Tdg:.2f} kN (IS 800:2007 Cl. 6.2)"
    result.checks.append(
        CheckResult("Tension", util_t, status_t, detail_t, "IS 800:2007 Cl. 6.2")
    )

    # --- Compression (Clause 7.1) ---
    ry = sec.ry_cm * 10.0  # cm → mm
    Le = K * L * 1000.0  # m → mm
    slenderness = Le / ry if ry > 0 else 9999.0
    # Non-dimensional effective slenderness λ_nd = (fy/fcc)^0.5 / φ? 
    # IS 800: λ_nd = √(fy / fcr) where fcr = π² E / (KL/r)²
    E = mat.e_mpa
    if slenderness > 0:
        fcr = (math.pi**2 * E) / (slenderness**2)
        lambda_nd = math.sqrt(fy / fcr) if fcr > 0 else 10.0
    else:
        lambda_nd = 0.0
    chi = _chi_buckling(lambda_nd)
    fcd = chi * fy / gamma_m0  # MPa
    Pd = fcd * Ag / 1000.0  # kN
    N_c = max(-n_signed, 0.0)  # compression magnitude
    # Also use n_abs if mostly compression members
    if model.analysis:
        cmax = 0.0
        for f in model.analysis.forces_for_member(member_id):
            cmax = max(cmax, f.n_start_kn, -f.n_end_kn)
        N_c = max(N_c, cmax)
    util_c = N_c / Pd if Pd > 0 else 0.0
    result.checks.append(
        CheckResult(
            "Compression",
            util_c,
            "PASS" if util_c <= 1.0 else "FAIL",
            f"Nc={N_c:.2f} / Pd={Pd:.2f} kN; λ={slenderness:.1f}; χ={chi:.3f} (Cl. 7.1)",
            "IS 800:2007 Cl. 7.1.2",
        )
    )

    # --- Bending (Clause 8.2.1) ---
    Ze = sec.zx_cm3 * 1e3  # cm³ → mm³
    Zp = 1.2 * Ze  # approximate shape factor for I-sections (assumption)
    beta_b = 1.0
    Md = beta_b * Zp * fy / gamma_m0 / 1e6  # N·mm → kN·m
    util_m = m_abs / Md if Md > 0 else 0.0
    result.checks.append(
        CheckResult(
            "Bending",
            util_m,
            "PASS" if util_m <= 1.0 else "FAIL",
            f"M={m_abs:.2f} / Md={Md:.2f} kNm; βb=1.0, Zp≈1.2Ze (Cl. 8.2.1)",
            "IS 800:2007 Cl. 8.2.1",
        )
    )

    # --- Shear (Clause 8.4) ---
    # Av ≈ h * tw for I along web
    Av = sec.depth_mm * sec.tw_mm  # mm²
    Vd = Av * fy / (math.sqrt(3.0) * gamma_m0) / 1000.0  # kN
    util_v = v_abs / Vd if Vd > 0 else 0.0
    result.checks.append(
        CheckResult(
            "Shear",
            util_v,
            "PASS" if util_v <= 1.0 else "FAIL",
            f"V={v_abs:.2f} / Vd={Vd:.2f} kN (Cl. 8.4)",
            "IS 800:2007 Cl. 8.4",
        )
    )

    # --- Combined axial + bending (Clause 9.3.1 simplified) ---
    # Conservatively: Nc/Pd + My/Md <= 1.0 (interaction)
    if Pd > 0 and Md > 0:
        util_comb = N_c / Pd + m_abs / Md
    else:
        util_comb = 0.0
    result.checks.append(
        CheckResult(
            "Combined",
            util_comb,
            "PASS" if util_comb <= 1.0 else "FAIL",
            f"Nc/Pd + M/Md = {util_comb:.3f} (Cl. 9.3.1 simplified)",
            "IS 800:2007 Cl. 9.3.1",
        )
    )

    # Slenderness limit informational (IS 800 Table 3 — compression members often 180)
    slend_limit = 180.0
    util_sl = slenderness / slend_limit
    result.checks.append(
        CheckResult(
            "Slenderness",
            util_sl,
            "PASS" if util_sl <= 1.0 else "FAIL",
            f"KL/r={slenderness:.1f} / limit {slend_limit:.0f} (Table 3 guidance)",
            "IS 800:2007 Table 3",
        )
    )

    result.finalize()
    return result


def design_model(
    model: StructuralModel,
    *,
    section_db: Optional[SectionDatabase] = None,
    member_types: Optional[List[str]] = None,
) -> Dict[int, MemberDesignResult]:
    """Run design on primary members (columns/rafters by default)."""
    if model.metadata.get("requires_staad_analysis"):
        raise ValueError("Imported STAAD models require native code checks; simplified app checks cannot replace the imported ANL results.")
    section_db = section_db or SectionDatabase()
    types = set(member_types or ["column", "rafter"])
    results: Dict[int, MemberDesignResult] = {}
    for member in model.member_list():
        if member.member_type not in types:
            continue
        results[member.id] = design_member(model, member.id, section_db=section_db)
    model.design_results = results
    _serviceability_checks(model, results)
    return results


def _serviceability_checks(model, results):
    """Nodal service displacement checks; not a continuous deflection envelope."""
    if model.analysis is None:
        return
    limits = model.metadata.get("deflection_limits", {})
    span = float(model.metadata.get("span_m", 0))
    height = float(model.metadata.get("eave_height_m", 0))
    for mid, result in results.items():
        member = model.members[mid]
        nodes = {member.start_node, member.end_node}
        if member.member_type == "rafter":
            cases = [("S1", "Rafter total deflection", "rafter_total_load_L_over", 120, span, "uy_m"),
                     ("S2", "Rafter live deflection", "rafter_live_load_L_over", 180, span, "uy_m")]
        else:
            cases = [("S3", "Column wind sway", "column_wind_crane_H_over", 150, height, "ux_m"),
                     ("S_EX+", "Column seismic sway", "column_seismic_H_over", 250, height, "ux_m")]
        for case, name, key, default, length, component in cases:
            if case not in model.combinations or length <= 0:
                continue
            limit = float(limits.get(key, default))
            if limit <= 0:
                continue
            demand = max((abs(getattr(d, component)) for d in model.analysis.displacements
                          if d.node_id in nodes and d.combination_id == case), default=0)
            allowed = length / limit
            utilization = demand / allowed
            result.checks.append(CheckResult(name, utilization, "PASS" if utilization <= 1 else "FAIL",
                f"Nodal displacement {demand*1000:.3f} mm / {allowed*1000:.3f} mm; L/{limit:g}. Interior maxima need review.", "User serviceability limit"))
        result.finalize()
