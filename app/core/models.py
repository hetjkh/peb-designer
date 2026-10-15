"""Internal structural model types (solver-independent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


class SupportType(str, Enum):
    PINNED = "pinned"
    FIXED = "fixed"
    FREE = "free"


@dataclass(frozen=True)
class Node:
    """A structural node in 3D space.

    Coordinate convention:
        X — span (building width)
        Y — vertical height
        Z — building length (bay direction)
    """

    id: int
    x: float
    y: float
    z: float
    label: str = ""

    @property
    def coords(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Member:
    """A line member connecting two nodes."""

    id: int
    start_node: int
    end_node: int
    member_type: str = "generic"
    section: Optional[str] = None
    material: Optional[str] = None
    label: str = ""


@dataclass(frozen=True)
class Support:
    """Nodal support restraint."""

    node_id: int
    support_type: SupportType = SupportType.PINNED
    # Restraint flags: True = restrained (for FIXED/PINNED semantics)
    ux: bool = True
    uy: bool = True
    uz: bool = True
    rx: bool = False
    ry: bool = False
    rz: bool = False  # pinned: rotations free; fixed: True


@dataclass(frozen=True)
class LoadCase:
    """Named load case (DL, LL, WL, …)."""

    id: str
    name: str
    load_type: str  # dead | live | wind | other


@dataclass(frozen=True)
class MemberUniformLoad:
    """Uniform load along a member (kN/m) in global axes."""

    member_id: int
    load_case_id: str
    fx_kn_m: float = 0.0
    fy_kn_m: float = 0.0
    fz_kn_m: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class NodalLoad:
    """Point load at a node (kN / kN·m)."""

    node_id: int
    load_case_id: str
    fx_kn: float = 0.0
    fy_kn: float = 0.0
    fz_kn: float = 0.0


@dataclass(frozen=True)
class LoadCombination:
    """Factored combination of load cases."""

    id: str
    name: str
    factors: Dict[str, float]  # load_case_id -> factor
    source: str = ""


@dataclass
class MemberForces:
    """Internal forces at member ends (local: axial N, shear V, moment M)."""

    member_id: int
    combination_id: str
    n_start_kn: float = 0.0
    n_end_kn: float = 0.0
    v_start_kn: float = 0.0
    v_end_kn: float = 0.0
    m_start_knm: float = 0.0
    m_end_knm: float = 0.0

    @property
    def n_max_abs(self) -> float:
        return max(abs(self.n_start_kn), abs(self.n_end_kn))

    @property
    def v_max_abs(self) -> float:
        return max(abs(self.v_start_kn), abs(self.v_end_kn))

    @property
    def m_max_abs(self) -> float:
        return max(abs(self.m_start_knm), abs(self.m_end_knm))


@dataclass
class NodeDisplacement:
    node_id: int
    combination_id: str
    ux_m: float = 0.0
    uy_m: float = 0.0
    uz_m: float = 0.0


@dataclass
class AnalysisResults:
    status: str = "not_run"
    message: str = ""
    member_forces: List[MemberForces] = field(default_factory=list)
    displacements: List[NodeDisplacement] = field(default_factory=list)
    reactions: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)

    def forces_for_member(
        self, member_id: int, combination_id: Optional[str] = None
    ) -> List[MemberForces]:
        out = [f for f in self.member_forces if f.member_id == member_id]
        if combination_id is not None:
            out = [f for f in out if f.combination_id == combination_id]
        return out


@dataclass
class CheckResult:
    name: str
    utilization: float
    status: str  # PASS | FAIL | N/A
    detail: str = ""
    source: str = ""


@dataclass
class MemberDesignResult:
    member_id: int
    section: str
    material: str
    checks: List[CheckResult] = field(default_factory=list)
    max_utilization: float = 0.0
    status: str = "N/A"

    def finalize(self) -> None:
        utils = [c.utilization for c in self.checks if c.status != "N/A"]
        self.max_utilization = max(utils) if utils else 0.0
        if any(c.status == "FAIL" for c in self.checks):
            self.status = "FAIL"
        elif utils:
            self.status = "PASS" if self.max_utilization <= 1.0 else "FAIL"
        else:
            self.status = "N/A"


@dataclass
class StructuralModel:
    """In-memory structural model shared across modules."""

    nodes: Dict[int, Node] = field(default_factory=dict)
    members: Dict[int, Member] = field(default_factory=dict)
    supports: Dict[int, Support] = field(default_factory=dict)
    load_cases: Dict[str, LoadCase] = field(default_factory=dict)
    member_loads: List[MemberUniformLoad] = field(default_factory=list)
    nodal_loads: List[NodalLoad] = field(default_factory=list)
    combinations: Dict[str, LoadCombination] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)
    analysis: Optional[AnalysisResults] = None
    design_results: Dict[int, MemberDesignResult] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id: {node.id}")
        self.nodes[node.id] = node

    def add_member(self, member: Member) -> None:
        if member.id in self.members:
            raise ValueError(f"Duplicate member id: {member.id}")
        if member.start_node not in self.nodes:
            raise ValueError(f"Unknown start node: {member.start_node}")
        if member.end_node not in self.nodes:
            raise ValueError(f"Unknown end node: {member.end_node}")
        self.members[member.id] = member

    def set_support(self, support: Support) -> None:
        if support.node_id not in self.nodes:
            raise ValueError(f"Unknown support node: {support.node_id}")
        self.supports[support.node_id] = support

    def replace_member(self, member: Member) -> None:
        if member.id not in self.members:
            raise ValueError(f"Unknown member: {member.id}")
        self.members[member.id] = member

    def node_list(self) -> List[Node]:
        return [self.nodes[k] for k in sorted(self.nodes)]

    def member_list(self) -> List[Member]:
        return [self.members[k] for k in sorted(self.members)]

    def clear(self) -> None:
        self.nodes.clear()
        self.members.clear()
        self.supports.clear()
        self.load_cases.clear()
        self.member_loads.clear()
        self.nodal_loads.clear()
        self.combinations.clear()
        self.metadata.clear()
        self.analysis = None
        self.design_results.clear()

    def summary(self) -> str:
        return f"Nodes: {len(self.nodes)}  |  Members: {len(self.members)}"

    def iter_member_endpoints(
        self,
    ) -> Iterable[Tuple[Member, Node, Node]]:
        for member in self.member_list():
            yield (
                member,
                self.nodes[member.start_node],
                self.nodes[member.end_node],
            )
