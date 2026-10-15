"""Analysis engine abstraction and built-in 2D direct-stiffness solver.

The core app depends only on AnalysisEngine. A NumPy/SciPy plane-frame
solver is provided so the product runs without proprietary software and
without requiring OpenSees at install time.

OpenSees can be added later behind the same interface.

Method: classical direct stiffness method for 2D frames (3 DOF/node:
ux, uy, rz). Each transverse PEB frame (constant Z) is solved in the X–Y
plane. Gravity loads use global FY; wind uses global FX.

References:
  - Weaver & Gere / standard matrix structural analysis
  - McGuire, Gallagher & Ziemian — Matrix Structural Analysis
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from app.core.models import (
    AnalysisResults,
    LoadCombination,
    MemberForces,
    NodeDisplacement,
    StructuralModel,
    SupportType,
)
from app.database.materials import get_material
from app.database.sections import SectionDatabase


class AnalysisEngine(ABC):
    @abstractmethod
    def analyze(self, model: StructuralModel) -> AnalysisResults:
        raise NotImplementedError


def _member_length(model: StructuralModel, member_id: int) -> Tuple[float, float, float, float]:
    m = model.members[member_id]
    n0 = model.nodes[m.start_node]
    n1 = model.nodes[m.end_node]
    dx = n1.x - n0.x
    dy = n1.y - n0.y
    L = math_hypot(dx, dy)
    return dx, dy, L, (math.atan2(dy, dx) if L > 0 else 0.0)


def math_hypot(a: float, b: float) -> float:
    return float(np.hypot(a, b))


def _local_stiffness(E: float, A: float, I: float, L: float) -> np.ndarray:
    """6x6 local beam stiffness (kN, m units). E in kN/m², A m², I m⁴, L m."""
    if L <= 0:
        raise ValueError("Zero-length member")
    EA_L = E * A / L
    EI_L = E * I / L
    EI_L2 = E * I / (L * L)
    EI_L3 = E * I / (L ** 3)
    k = np.array(
        [
            [EA_L, 0, 0, -EA_L, 0, 0],
            [0, 12 * EI_L3, 6 * EI_L2, 0, -12 * EI_L3, 6 * EI_L2],
            [0, 6 * EI_L2, 4 * EI_L, 0, -6 * EI_L2, 2 * EI_L],
            [-EA_L, 0, 0, EA_L, 0, 0],
            [0, -12 * EI_L3, -6 * EI_L2, 0, 12 * EI_L3, -6 * EI_L2],
            [0, 6 * EI_L2, 2 * EI_L, 0, -6 * EI_L2, 4 * EI_L],
        ],
        dtype=float,
    )
    return k


def _rotation(c: float, s: float) -> np.ndarray:
    R = np.zeros((6, 6), dtype=float)
    R[0, 0] = c
    R[0, 1] = s
    R[1, 0] = -s
    R[1, 1] = c
    R[2, 2] = 1.0
    R[3, 3] = c
    R[3, 4] = s
    R[4, 3] = -s
    R[4, 4] = c
    R[5, 5] = 1.0
    return R


class DirectStiffness2DEngine(AnalysisEngine):
    """Plane-frame solver for transverse PEB frames."""

    def __init__(self, section_db: Optional[SectionDatabase] = None) -> None:
        self.section_db = section_db or SectionDatabase()

    def analyze(self, model: StructuralModel) -> AnalysisResults:
        if model.metadata.get("requires_staad_analysis"):
            return AnalysisResults(status="unsupported", message="Imported native STAAD models contain specifications and loads outside the 2D solver. Run this model in STAAD.Pro and import its matching ANL results.")
        if not model.members:
            return AnalysisResults(status="error", message="Empty model")
        if not model.combinations:
            return AnalysisResults(status="error", message="No load combinations")

        frames = self._group_frames(model)
        self._member_load_index = defaultdict(list)
        for load in model.member_loads:
            self._member_load_index[load.member_id].append(load)
        if not frames:
            return AnalysisResults(status="error", message="No planar frames found")

        all_forces: List[MemberForces] = []
        all_disp: List[NodeDisplacement] = []
        reactions: Dict[int, Tuple[float, float, float]] = {}

        for z, node_ids in frames.items():
            try:
                forces, disps, reacts = self._analyze_frame(model, node_ids)
            except (ValueError, np.linalg.LinAlgError) as exc:
                return AnalysisResults(status="error", message=f"Frame Z={z:g}: {exc}")
            all_forces.extend(forces)
            all_disp.extend(disps)
            reactions.update(reacts)

        return AnalysisResults(
            status="ok",
            message=f"Analyzed {len(frames)} transverse frame(s) with DirectStiffness2DEngine",
            member_forces=all_forces,
            displacements=all_disp,
            reactions=reactions,
        )

    def _group_frames(self, model: StructuralModel) -> Dict[float, List[int]]:
        buckets: Dict[float, List[int]] = defaultdict(list)
        for n in model.node_list():
            key = round(n.z, 6)
            buckets[key].append(n.id)
        # Keep frames that have at least 3 nodes
        return {z: ids for z, ids in buckets.items() if len(ids) >= 3}

    def _analyze_frame(
        self, model: StructuralModel, node_ids: Sequence[int]
    ) -> Tuple[List[MemberForces], List[NodeDisplacement], Dict[int, Tuple[float, float, float]]]:
        node_set = set(node_ids)
        members = [
            m
            for m in model.member_list()
            if m.start_node in node_set and m.end_node in node_set
        ]
        # Drop near-zero length / out-of-plane only members (dz significant)
        planar = []
        for m in members:
            n0 = model.nodes[m.start_node]
            n1 = model.nodes[m.end_node]
            if abs(n0.z - n1.z) > 1e-6:
                continue
            if np.hypot(n1.x - n0.x, n1.y - n0.y) < 1e-9:
                continue
            planar.append(m)
        members = planar
        if not members:
            return [], [], {}

        # DOF map: node -> (ux, uy, rz)
        dof: Dict[int, Tuple[int, int, int]] = {}
        n_dof = 0
        for nid in sorted(node_set):
            dof[nid] = (n_dof, n_dof + 1, n_dof + 2)
            n_dof += 3

        K = np.zeros((n_dof, n_dof), dtype=float)
        member_meta = []

        for m in members:
            props = self._section_props(model, m.id)
            if props is None:
                continue
            E, A, I = props
            dx, dy, L, _th = _member_length(model, m.id)
            c = dx / L
            s = dy / L
            k_local = _local_stiffness(E, A, I, L)
            R = _rotation(c, s)
            k_global = R.T @ k_local @ R
            i0, i1, i2 = dof[m.start_node]
            j0, j1, j2 = dof[m.end_node]
            edofs = [i0, i1, i2, j0, j1, j2]
            for a in range(6):
                for b in range(6):
                    K[edofs[a], edofs[b]] += k_global[a, b]
            member_meta.append((m, E, A, I, L, c, s, edofs, k_local, R))

        restrained = self._restrained_dofs(model, dof)
        free = [i for i in range(n_dof) if i not in set(restrained)]
        factorization = cho_factor(K[np.ix_(free, free)]) if free else None
        forces_out: List[MemberForces] = []
        disp_out: List[NodeDisplacement] = []
        reacts: Dict[int, Tuple[float, float, float]] = {}

        for combo in model.combinations.values():
            F = self._load_vector(model, combo, dof, members)
            u = np.zeros(n_dof)
            if free:
                u[free] = cho_solve(factorization, F[free])

            for nid, (du, dv, dr) in dof.items():
                disp_out.append(
                    NodeDisplacement(
                        node_id=nid,
                        combination_id=combo.id,
                        ux_m=float(u[du]),
                        uy_m=float(u[dv]),
                        uz_m=0.0,
                    )
                )

            # Reactions approx at supports: K*u - F
            resid = K @ u - F
            for nid, support in model.supports.items():
                if nid not in dof:
                    continue
                du, dv, _dr = dof[nid]
                reacts[nid] = (float(resid[du]), float(resid[dv]), 0.0)

            for m, E, A, I, L, c, s, edofs, k_local, R in member_meta:
                ue = u[edofs]
                # local end forces
                fl = k_local @ (R @ ue)
                # Add fixed-end forces from uniform loads in local system for this combo
                fl = fl + self._fixed_end_local(model, m.id, combo, L, c, s)
                forces_out.append(
                    MemberForces(
                        member_id=m.id,
                        combination_id=combo.id,
                        n_start_kn=float(fl[0]),
                        v_start_kn=float(fl[1]),
                        m_start_knm=float(fl[2]),
                        n_end_kn=float(fl[3]),
                        v_end_kn=float(fl[4]),
                        m_end_knm=float(fl[5]),
                    )
                )

        return forces_out, disp_out, reacts

    def _section_props(
        self, model: StructuralModel, member_id: int
    ) -> Optional[Tuple[float, float, float]]:
        m = model.members[member_id]
        if not m.section or not m.material:
            return None
        try:
            sec = self.section_db.get(m.section)
            mat = get_material(m.material)
        except KeyError:
            return None
        # Convert to consistent N,mm or kN,m: use kN and m
        E = mat.e_mpa * 1e3  # MPa = N/mm² → kN/m² = MPa*1000
        A = sec.area_cm2 * 1e-4  # cm² → m²
        I = sec.ix_cm4 * 1e-8  # cm⁴ → m⁴
        return E, A, I

    def _restrained_dofs(
        self, model: StructuralModel, dof: Dict[int, Tuple[int, int, int]]
    ) -> List[int]:
        fixed: List[int] = []
        for nid, (du, dv, dr) in dof.items():
            support = model.supports.get(nid)
            if support is None:
                continue
            if support.ux:
                fixed.append(du)
            if support.uy:
                fixed.append(dv)
            if support.support_type == SupportType.FIXED or support.rz:
                fixed.append(dr)
        return sorted(set(fixed))

    def _load_vector(
        self,
        model: StructuralModel,
        combo: LoadCombination,
        dof: Dict[int, Tuple[int, int, int]],
        members: Sequence,
    ) -> np.ndarray:
        n_dof = 3 * len(dof)
        F = np.zeros(n_dof, dtype=float)
        member_ids = {m.id for m in members}

        for mload in model.member_loads:
            if mload.member_id not in member_ids:
                continue
            factor = combo.factors.get(mload.load_case_id, 0.0)
            if abs(factor) < 1e-15:
                continue
            m = model.members[mload.member_id]
            dx, dy, L, _ = _member_length(model, m.id)
            if L <= 0:
                continue
            # Equivalent nodal loads for uniform global FX, FY on beam
            wx = mload.fx_kn_m * factor
            wy = mload.fy_kn_m * factor
            # Transform global UDL to local, then FEM, then back — simplified:
            # apply half of total force to each end in global directions
            fx = wx * L / 2.0
            fy = wy * L / 2.0
            i0, i1, i2 = dof[m.start_node]
            j0, j1, j2 = dof[m.end_node]
            F[i0] += fx
            F[i1] += fy
            F[j0] += fx
            F[j1] += fy
            # Approximate moments for perpendicular component
            # local q = -s*wx + c*wy (local transverse)
            c = dx / L
            s = dy / L
            q = -s * wx + c * wy
            m_end = q * L * L / 12.0
            F[i2] += m_end
            F[j2] -= m_end

        for nload in model.nodal_loads:
            if nload.node_id not in dof:
                continue
            factor = combo.factors.get(nload.load_case_id, 0.0)
            du, dv, _ = dof[nload.node_id]
            F[du] += nload.fx_kn * factor
            F[dv] += nload.fy_kn * factor
        return F

    def _fixed_end_local(
        self,
        model: StructuralModel,
        member_id: int,
        combo: LoadCombination,
        L: float,
        c: float,
        s: float,
    ) -> np.ndarray:
        """Local fixed-end force vector for UDL (for force recovery consistency)."""
        fl = np.zeros(6, dtype=float)
        for mload in getattr(self, "_member_load_index", {}).get(member_id, model.member_loads):
            if mload.member_id != member_id:
                continue
            factor = combo.factors.get(mload.load_case_id, 0.0)
            if abs(factor) < 1e-15:
                continue
            wx = mload.fx_kn_m * factor
            wy = mload.fy_kn_m * factor
            # axial local q_x = c*wx + s*wy ; transverse q_y = -s*wx + c*wy
            qx = c * wx + s * wy
            qy = -s * wx + c * wy
            fl[0] -= qx * L / 2.0
            fl[3] -= qx * L / 2.0
            fl[1] -= qy * L / 2.0
            fl[4] -= qy * L / 2.0
            fl[2] -= qy * L * L / 12.0
            fl[5] += qy * L * L / 12.0
        return fl

    @staticmethod
    def _solve(K: np.ndarray, F: np.ndarray, restrained: Sequence[int]) -> np.ndarray:
        n = K.shape[0]
        free = [i for i in range(n) if i not in set(restrained)]
        if not free:
            return np.zeros(n)
        Kff = K[np.ix_(free, free)]
        Ff = F[free]
        try:
            uf = np.linalg.solve(Kff, Ff)
        except np.linalg.LinAlgError:
            raise ValueError("Unstable frame: singular stiffness matrix. Check member connections and supports.")
        u = np.zeros(n, dtype=float)
        u[free] = uf
        return u


class OpenSeesEngine(AnalysisEngine):
    """Optional OpenSees backend (not required). Falls back with clear error."""

    def analyze(self, model: StructuralModel) -> AnalysisResults:
        try:
            import openseespy.opensees  # noqa: F401
        except ImportError:
            return AnalysisResults(
                status="error",
                message=(
                    "OpenSeesPy is not installed. Use DirectStiffness2DEngine "
                    "or pip install openseespy."
                ),
            )
        return AnalysisResults(
            status="error",
            message="OpenSees bridge not fully implemented yet — use DirectStiffness2DEngine.",
        )


def get_default_engine() -> AnalysisEngine:
    return DirectStiffness2DEngine()
