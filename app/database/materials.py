"""Steel materials used by the design / analysis modules.

Sources:
  - IS 800:2007 Table 1 / Clause 2.2.4 — partial safety factors γ_m0, γ_m1
  - IS 2062 / common PEB practice — fy, fu for E250 / E350 / E450 grades
  - IS 800:2007 Clause 2.2.4.1 — E = 2×10^5 MPa, G = 0.769×10^5 MPa, ν = 0.3
  - Density 7850 kg/m³ — standard structural steel
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Material:
    name: str
    fy_mpa: float
    fu_mpa: float
    e_mpa: float = 2.0e5
    g_mpa: float = 0.769e5
    density_kg_m3: float = 7850.0
    gamma_m0: float = 1.10  # IS 800:2007 Table 5
    gamma_m1: float = 1.25  # IS 800:2007 Table 5
    source: str = "IS 800:2007 / IS 2062"


MATERIALS: Dict[str, Material] = {
    "E250": Material("E250", fy_mpa=250.0, fu_mpa=410.0),
    "E350": Material("E350", fy_mpa=350.0, fu_mpa=490.0),
    "E450": Material("E450", fy_mpa=450.0, fu_mpa=570.0),
}


def get_material(name: str) -> Material:
    key = name.strip().upper()
    if key not in MATERIALS:
        raise KeyError(f"Unknown material: {name}")
    return MATERIALS[key]


def list_materials() -> List[Material]:
    return list(MATERIALS.values())
