"""Load generation and IS 800:2007 load combinations.

Sources (documented — review before real design use):
  - Dead / live intensities: user input (kN/m²), converted to member UNI with
    tributary width = average sidewall spacing.
  - Self-weight: section mass × g, applied as UNI on members.
  - Wind pressure (simplified IS 875 Part 3):
        pz = 0.6 * Vz²   (N/m²) with Vz in m/s
        Vz = Vb * k1 * k2 * k3 * k4
    Assumptions used here (explicitly stated, not hidden):
        k1 = 1.0, k3 = 1.0, k4 = 1.0
        k2 from a coarse Terrain Category 2 / Class B height table (approx.)
        Design pressure on windward vertical face qd = pz * Cp with Cp = +0.8
        (IS 875 Part 3 typical external pressure coefficient for windward wall —
         simplified; full zoning not implemented.)
  - Combinations: IS 800:2007 Table 4 (Limit State of Strength), partial set:
        1.5 DL
        1.5 DL + 1.5 LL
        1.5 DL ± 1.5 WL
        1.2 DL + 1.2 LL ± 1.2 WL
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.models import (
    LoadCase,
    LoadCombination,
    MemberUniformLoad,
    NodalLoad,
    StructuralModel,
)
from app.database.sections import SectionDatabase


G_M_S2 = 9.80665


@dataclass(frozen=True)
class LoadEngineConfig:
    include_self_weight: bool = True
    include_roof_dead: bool = True
    include_roof_live: bool = True
    include_wind: bool = True
    wind_cp_windward: float = 0.8  # IS 875 (Part 3) simplified
    terrain_category: int = 2


def _k2_terrain2(height_m: float) -> float:
    """Approximate k2 for Terrain Category 2, Class B (IS 875 Part 3 style).

    Coarse stepwise values for educational use — replace with full code table.
    """
    h = max(height_m, 10.0)
    if h <= 10:
        return 1.00
    if h <= 15:
        return 1.05
    if h <= 20:
        return 1.07
    if h <= 30:
        return 1.12
    return 1.15


def design_wind_pressure_kn_m2(
    vb_mps: float,
    height_m: float,
    *,
    k1: float = 1.0,
    k3: float = 1.0,
    k4: float = 1.0,
    terrain_category: int = 2,
    k2_override: float | None = None,
) -> Tuple[float, Dict[str, float]]:
    """Return pz (kN/m²) and factor breakdown.

    pz = 0.6 Vz²  (N/m²) → /1000 for kN/m²
    Source: IS 875 (Part 3) Clause 5.4 / 5.5 style formulation.
    """
    k2 = k2_override if k2_override is not None else (_k2_terrain2(height_m) if terrain_category == 2 else 1.0)
    vz = vb_mps * k1 * k2 * k3 * k4
    pz_n_m2 = 0.6 * vz * vz
    pz_kn_m2 = pz_n_m2 / 1000.0
    return pz_kn_m2, {"Vb": vb_mps, "k1": k1, "k2": k2, "k3": k3, "k4": k4, "Vz": vz, "pz": pz_kn_m2}


def average_bay_spacing(model: StructuralModel) -> float:
    spacings = model.metadata.get("sidewall_spacings_m") or []
    if not spacings:
        length = float(model.metadata.get("length_m", 0) or 0)
        n_bays = int(model.metadata.get("number_of_bays", 0) or 0)
        return length / n_bays if n_bays else 0.0
    return float(sum(spacings) / len(spacings))


def tributary_widths(model: StructuralModel) -> Dict[float, float]:
    stations = [0.0]
    for bay in model.metadata.get("sidewall_spacings_m", []):
        stations.append(stations[-1] + float(bay))
    return {round(z, 6): ((z - stations[i-1]) / 2 if i else 0)
            + ((stations[i+1] - z) / 2 if i < len(stations)-1 else 0)
            for i, z in enumerate(stations)}


def apply_loads(
    model: StructuralModel,
    *,
    config: Optional[LoadEngineConfig] = None,
    section_db: Optional[SectionDatabase] = None,
) -> StructuralModel:
    """Populate load cases, member loads, and IS 800 Table 4 combinations."""
    config = config or LoadEngineConfig()
    section_db = section_db or SectionDatabase()

    model.load_cases.clear()
    model.member_loads.clear()
    model.nodal_loads.clear()
    model.combinations.clear()

    model.load_cases["DL"] = LoadCase("DL", "Dead Load", "dead")
    model.load_cases["LL"] = LoadCase("LL", "Live Load", "live")
    model.load_cases["WL"] = LoadCase("WL", "Wind Load", "wind")

    trib = average_bay_spacing(model)
    widths = tributary_widths(model)
    roof = model.metadata.get("roof_loads") or {}
    dead_i = float(roof.get("dead_kn_m2", 0) or 0) + float(roof.get("collateral_kn_m2", 0) or 0)
    live_i = float(roof.get("live_kn_m2", 0) or 0)

    # Self-weight
    if config.include_self_weight:
        for member in model.member_list():
            if not member.section:
                continue
            try:
                sec = section_db.get(member.section)
            except KeyError:
                continue
            w = (sec.mass_kg_m * G_M_S2) / 1000.0  # kN/m downward
            a, b = model.nodes[member.start_node], model.nodes[member.end_node]
            if abs(a.z - b.z) > 1e-6:
                # Transverse frame analysis: transfer secondary-member weight
                # as simple-span end reactions, also used by the plane export.
                for nid in (a.id, b.id):
                    model.nodal_loads.append(NodalLoad(nid, "DL", fy_kn=-w * math.dist(a.coords, b.coords) / 2))
                continue
            model.member_loads.append(
                MemberUniformLoad(
                    member_id=member.id,
                    load_case_id="DL",
                    fy_kn_m=-w,
                    description="Self-weight",
                )
            )

    # Roof dead / live on rafters
    if trib > 0:
        if config.include_roof_dead and dead_i > 0:
            w = dead_i * trib
            for member in model.member_list():
                if member.member_type in ("rafter", "lean_rafter", "canopy", "roof_extension"):
                    a, b = model.nodes[member.start_node], model.nodes[member.end_node]
                    local_trib = widths.get(round(a.z, 6), 0)
                    w = dead_i * local_trib * abs(b.x-a.x) / math.dist(a.coords, b.coords)
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="DL",
                            fy_kn_m=-w,
                            description=f"Roof dead+collateral {dead_i:g} kN/m² × trib {trib:g} m",
                        )
                    )
        if config.include_roof_live and live_i > 0:
            w = live_i * trib
            for member in model.member_list():
                if member.member_type in ("rafter", "lean_rafter", "canopy", "roof_extension"):
                    a, b = model.nodes[member.start_node], model.nodes[member.end_node]
                    local_trib = widths.get(round(a.z, 6), 0)
                    w = live_i * local_trib * abs(b.x-a.x) / math.dist(a.coords, b.coords)
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="LL",
                            fy_kn_m=-w,
                            description=f"Roof live {live_i:g} kN/m² × trib {trib:g} m",
                        )
                    )

    # Mezzanine floor loads on transverse floor beams (along width)
    mz = model.metadata.get("mezzanine") or {}
    if mz.get("enabled"):
        levels = mz.get("levels") or []
        if not levels and mz.get("width_m"):
            levels = [mz]
        for li, lv in enumerate(levels):
            dead = float(lv.get("dead_kn_m2", 0) or 0) + float(
                lv.get("collateral_kn_m2", 0) or 0
            )
            live = float(lv.get("live_kn_m2", 0) or 0)
            joist = float(lv.get("joist_spacing_m", 0) or 0) or trib
            h = float(lv.get("height_m", 0) or 0)
            start = float(lv.get("start_m", 0) or 0)
            width = float(lv.get("width_m", 0) or 0)
            y_tol = 0.05
            ffl = float(model.metadata.get("ffl_level_m", 0) or 0)
            target_y = ffl + h
            for member in model.member_list():
                if member.member_type != "mezzanine_beam":
                    continue
                n0 = model.nodes[member.start_node]
                n1 = model.nodes[member.end_node]
                if abs(n0.y - target_y) > y_tol or abs(n1.y - target_y) > y_tol:
                    continue
                # Transverse beams: primarily along X
                if abs(n1.x - n0.x) < abs(n1.z - n0.z):
                    continue
                mid_x = 0.5 * (n0.x + n1.x)
                if mid_x < start - 1e-6 or mid_x > start + width + 1e-6:
                    continue
                # These are frame girders supporting the full adjacent floor
                # strip; joist spacing must not reduce the total floor load.
                joist = widths.get(round(n0.z, 6), 0)
                if dead > 0 and joist > 0:
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="DL",
                            fy_kn_m=-(dead * joist),
                            description=(
                                f"Mezz L{li+1} floor DL+coll {dead:g} kN/m² "
                                f"× joist {joist:g} m"
                            ),
                        )
                    )
                if live > 0 and joist > 0:
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="LL",
                            fy_kn_m=-(live * joist),
                            description=(
                                f"Mezz L{li+1} floor LL {live:g} kN/m² "
                                f"× joist {joist:g} m"
                            ),
                        )
                    )
                bw = float(lv.get("blockwall_kn_m", 0) or 0)
                if bw > 0:
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="DL",
                            fy_kn_m=-bw,
                            description=f"Mezz L{li+1} blockwall {bw:g} kN/m",
                        )
                    )

    # Wind on windward columns (horizontal +X)
    wind_meta: Dict[str, float] = {}
    if config.include_wind:
        ws = model.metadata.get("wind_seismic") or {}
        vb = float(ws.get("wind_speed_mps", 0) or 0)
        eave = float(model.metadata.get("eave_height_m", 0) or 0)
        if vb > 0 and trib > 0 and eave > 0:
            pz, wind_meta = design_wind_pressure_kn_m2(
                vb, eave, k1=float(ws.get("k1_risk", 1)),
                k3=float(ws.get("k3_topography", 1)),
                k4=float(ws.get("k4_importance", 1)),
                terrain_category=int(ws.get("terrain_category", config.terrain_category)),
                k2_override=ws.get("k2_override"))
            qd = pz * config.wind_cp_windward  # kN/m²
            w_col = qd * trib  # kN/m on windward columns
            # Windward = min X columns
            min_x = 0.0
            for member in model.member_list():
                if member.member_type != "column":
                    continue
                n0 = model.nodes[member.start_node]
                n1 = model.nodes[member.end_node]
                if abs(n0.x - min_x) < 1e-6 and abs(n1.x - min_x) < 1e-6:
                    w_col = qd * widths.get(round(n0.z, 6), 0)
                    model.member_loads.append(
                        MemberUniformLoad(
                            member_id=member.id,
                            load_case_id="WL",
                            fx_kn_m=w_col,
                            description=(
                                f"Windward wall qd={qd:.4g} kN/m² "
                                f"(pz={pz:.4g}, Cp={config.wind_cp_windward})"
                            ),
                        )
                    )

    model.metadata["load_engine"] = {
        "tributary_m": trib,
        "wind": wind_meta,
        "assumptions": [
            "Roof loads per horizontal plan area; end frames half bay, interior frames half adjacent bays",
            "Wind: user k1/k3/k4; approximate terrain-2 k2, other terrain requires review",
            "Windward Cp=+0.8 only; suction/roof zones not yet applied",
            "Combinations from IS 800:2007 Table 4 (partial set)",
        ],
    }

    # IS 800:2007 Table 4 — Limit state of strength (partial)
    combos = [
        LoadCombination("C1", "1.5 DL", {"DL": 1.5}, "IS 800:2007 Table 4"),
        LoadCombination("C2", "1.5 DL + 1.5 LL", {"DL": 1.5, "LL": 1.5}, "IS 800:2007 Table 4"),
        LoadCombination("C3", "1.5 DL + 1.5 WL", {"DL": 1.5, "WL": 1.5}, "IS 800:2007 Table 4"),
        LoadCombination("C4", "1.5 DL - 1.5 WL", {"DL": 1.5, "WL": -1.5}, "IS 800:2007 Table 4"),
        LoadCombination(
            "C5",
            "1.2 DL + 1.2 LL + 1.2 WL",
            {"DL": 1.2, "LL": 1.2, "WL": 1.2},
            "IS 800:2007 Table 4",
        ),
        LoadCombination(
            "C6",
            "1.2 DL + 1.2 LL - 1.2 WL",
            {"DL": 1.2, "LL": 1.2, "WL": -1.2},
            "IS 800:2007 Table 4",
        ),
    ]
    for c in combos:
        model.combinations[c.id] = c

    for c in (
        LoadCombination("C7", "0.9 DL + 1.5 WL", {"DL": 0.9, "WL": 1.5}, "IS 800:2007 Table 4"),
        LoadCombination("C8", "0.9 DL - 1.5 WL", {"DL": 0.9, "WL": -1.5}, "IS 800:2007 Table 4"),
        LoadCombination("S1", "Service DL + LL", {"DL": 1, "LL": 1}, "Serviceability"),
        LoadCombination("S2", "Service LL", {"LL": 1}, "Serviceability"),
        LoadCombination("S3", "Service WL", {"WL": 1}, "Serviceability"),
    ):
        model.combinations[c.id] = c

    code = str(model.metadata.get("load_combination_type", "IS800-2007-LSD"))
    warnings = []
    if code != "IS800-2007-LSD":
        # Preserve unfactored load cases for review; never label IS LSD
        # factors as ASCE or WSD results.
        model.combinations = {k: c for k, c in model.combinations.items() if k.startswith("S")}
        warnings.append(f"{code} strength combinations are not implemented; service cases only.")
    ws = model.metadata.get("wind_seismic", {})
    if ws.get("code_family") == "ASCE7":
        model.member_loads = [l for l in model.member_loads if l.load_case_id != "WL"]
        warnings.append("ASCE wind/seismic generation unavailable: exposure, site, Ss/S1 and method flags are stored only.")
    else:
        warnings.append("Wind is a preliminary windward-wall case only; enclosure, roof suction and full zoning are not applied.")
        if str(ws.get("terrain_category", "2")) != "2" and "k2_override" not in ws:
            warnings.append("Terrain categories 1/3/4 lack a verified k2 table; k2=1 is a placeholder.")
        warnings.append("Automatic IS seismic loads are not implemented: zone, soil and R are stored only.")
    if model.metadata.get("crane", {}).get("enabled"):
        warnings.append("Crane is a clearance annotation only: wheel loads, runway design, impact and surge are not generated.")
    if model.metadata.get("roof_monitor", {}).get("enabled"):
        warnings.append("Monitor members are connected; monitor cladding and wind pressure require separate loads.")
    ext = model.metadata.get("extensions", {})
    if any(ext.get("fascia_" + side, {}).get("enabled") for side in ("left", "right")):
        warnings.append("Fascia is a cladding annotation in the layout view; no additional structural member or cladding load is assumed.")
    if mz.get("enabled"):
        warnings.append("Mezzanine floor loads use frame tributary width; joist spacing is stored only. Individual joists are not modeled.")
    if model.metadata.get("blockwall_height_m", 0):
        warnings.append("Main blockwall height is a drawing input; wall dead load is not generated.")
    model.metadata["audit_warnings"] = warnings

    uplift = float(ws.get("wind_roof_uplift_kn_m2", 0))
    ah = float(ws.get("seismic_ah", 0))
    additional = []
    if uplift > 0:
        model.load_cases["WU"] = LoadCase("WU", "USER NET ROOF UPLIFT", "wind")
        for m in model.member_list():
            if m.member_type not in ("rafter", "lean_rafter", "canopy", "roof_extension"):
                continue
            a, b = model.nodes[m.start_node], model.nodes[m.end_node]
            w = uplift * widths.get(round(a.z, 6), 0) * abs(b.x-a.x) / math.dist(a.coords, b.coords)
            model.member_loads.append(MemberUniformLoad(m.id, "WU", fy_kn_m=w, description="User net uplift per plan area"))
        additional.append("WU")
    if ah > 0:
        weights = {nid: 0.0 for nid in model.nodes}
        for load in model.member_loads:
            if load.load_case_id == "DL":
                m = model.members[load.member_id]
                weight = max(0, -load.fy_kn_m) * math.dist(model.nodes[m.start_node].coords, model.nodes[m.end_node].coords)
                weights[m.start_node] += weight / 2
                weights[m.end_node] += weight / 2
        for load in model.nodal_loads:
            if load.load_case_id == "DL":
                weights[load.node_id] += max(0, -load.fy_kn)
        ffl = float(model.metadata.get("ffl_level_m", 0))
        active = {nid: w for nid, w in weights.items() if model.nodes[nid].y > ffl + 1e-6}
        for case, sign in (("EX+", 1), ("EX-", -1)):
            model.load_cases[case] = LoadCase(case, f"USER SEISMIC {case}", "seismic")
            for z in widths:
                frame = {nid: w for nid, w in active.items() if abs(model.nodes[nid].z-z) < 1e-6}
                denom = sum(w * (model.nodes[nid].y-ffl)**2 for nid, w in frame.items())
                shear = ah * sum(frame.values())
                for nid, weight in frame.items():
                    if denom > 0:
                        force = sign * shear * weight * (model.nodes[nid].y-ffl)**2 / denom
                        model.nodal_loads.append(NodalLoad(nid, case, fx_kn=force))
            additional.append(case)
        model.metadata["seismic_user"] = {"Ah": ah, "elevated_dead_weight_kn": sum(active.values()), "base_shear_kn": ah * sum(active.values())}
        warnings.append("User Ah seismic: elevated dead weight only, height-squared distribution, ±X; live-load mass and dynamic/torsional effects excluded.")
    for case in additional:
        model.combinations[f"S_{case}"] = LoadCombination(f"S_{case}", f"Service {case}", {case: 1}, "Serviceability")
        if code == "IS800-2007-LSD":
            for suffix, factors in (("A", {"DL": 1.5, case: 1.5}),
                                    ("B", {"DL": 1.2, "LL": 1.2, case: 1.2}),
                                    ("C", {"DL": 0.9, case: 1.5})):
                key = f"C_{case}_{suffix}"
                model.combinations[key] = LoadCombination(key, " + ".join(f"{v:g} {k}" for k, v in factors.items()), factors, "IS 800:2007 Table 4, user lateral case")

    return model
