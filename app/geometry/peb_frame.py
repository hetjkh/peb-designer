"""PEB frame geometry generation.

Supported frame types (geometry construction only):
  - clear_span  : classic portal, one ridge, no interior columns
  - multi_span  : interior columns, one overall ridge
  - multi_gable : one ridge per span, valleys at interior columns
  - mono_slope  : single slope across the width (high eave on the right)
  - asym_gable  : two slopes about a (possibly offset) ridge

Legacy alias: ``single_gable`` → ``clear_span``.

Ridge rise uses roof pitch 1:N (rise/run = 1/N):

    rise = run * (1 / N)

UI "Roof Slope (X:10)" maps as N = 10 / X.

Source: standard roof-pitch trigonometry. Not a design-code provision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, Union

from app.core.models import Member, Node, StructuralModel, SupportType
from app.geometry.spacing import parse_spacing_list, spacing_total
from app.geometry.validation import ValidationError


class FrameType(str, Enum):
    CLEAR_SPAN = "clear_span"
    MULTI_SPAN = "multi_span"
    MULTI_GABLE = "multi_gable"
    MONO_SLOPE = "mono_slope"
    ASYM_GABLE = "asym_gable"

    # Backward-compatible alias used by older templates/tests
    SINGLE_GABLE = "clear_span"


def coerce_frame_type(value: Union[str, FrameType]) -> FrameType:
    if isinstance(value, FrameType):
        # SINGLE_GABLE shares value with CLEAR_SPAN
        if value.value == FrameType.CLEAR_SPAN.value:
            return FrameType.CLEAR_SPAN
        return value
    raw = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "single_gable": FrameType.CLEAR_SPAN,
        "clear_span": FrameType.CLEAR_SPAN,
        "multi_span": FrameType.MULTI_SPAN,
        "multi_gable": FrameType.MULTI_GABLE,
        "mono_slope": FrameType.MONO_SLOPE,
        "monoslope": FrameType.MONO_SLOPE,
        "asym_gable": FrameType.ASYM_GABLE,
        "asymmetric_gable": FrameType.ASYM_GABLE,
    }
    if raw in aliases:
        return aliases[raw]
    return FrameType(raw)


def frame_allows_interior_columns(frame_type: FrameType) -> bool:
    ft = coerce_frame_type(frame_type)
    return ft in (FrameType.MULTI_SPAN, FrameType.MULTI_GABLE)


def pitch_n_from_slope_x10(x: float) -> float:
    """Convert UI Roof Slope (X:10) to internal 1:N pitch number N."""
    if x <= 0:
        raise ValueError("Roof slope X must be > 0.")
    return 10.0 / x


def slope_x10_from_pitch_n(n: float) -> float:
    """Convert internal 1:N pitch to UI Roof Slope (X:10)."""
    if n <= 0:
        return 1.0
    return 10.0 / n


def recommend_ext_col_base(
    width_m: float,
    eave_height_m: float,
    *,
    heavy_crane: bool = False,
) -> Tuple[SupportType, str]:
    """Recommend exterior column base from proportions.

    Returns (support, reason_phrase).
    Heavy / step-column crane cases are always Fixed.
    """
    if heavy_crane:
        return SupportType.FIXED, "step/heavy crane → Fixed"
    if width_m > eave_height_m:
        return SupportType.PINNED, "wider than it is tall"
    return SupportType.FIXED, "taller than it is wide"


@dataclass(frozen=True)
class RoofLoadsInput:
    """User-specified roof load intensities (kN/m²).

    These are taken as entered by the engineer. No code factors are applied
    here. Export may convert to member UNI loads using tributary assumptions
    documented in the exporter.
    """

    dead_kn_m2: float = 0.0
    collateral_kn_m2: float = 0.0
    live_kn_m2: float = 0.0


@dataclass(frozen=True)
class WindSeismicInput:
    """Stored project parameters for later load modules.

    Values are captured for reporting / STAAD comments only in this milestone.
    No wind or seismic pressures are calculated yet.

    ``code_family`` selects which parameter set is active in the UI:
      - IS     → terrain, k1/k3/k4, IS seismic zone, soil type, R
      - ASCE7  → exposure, site class, Ss/S1, DM/ADM/SM/Others
    """

    wind_speed_mps: float = 47.0
    building_condition: str = "Enclosed"
    load_combination_label: str = "User-defined (not applied yet)"
    code_family: str = "IS"  # IS | ASCE7

    # --- IS Code set ---
    terrain_category: str = "1"
    k1_risk: float = 1.0
    k3_topography: float = 1.0
    k4_importance: float = 1.0
    is_seismic_zone: str = "III"
    soil_type: str = "II"
    response_factor_r: float = 5.0

    # --- ASCE 7 set ---
    exposure: str = "B"
    site_class: str = "B"
    asce_seismic_zone: str = "2A"
    use_dm: bool = False
    use_adm: bool = False
    use_sm: bool = False
    use_others: bool = True
    ss_g: float = 0.365
    s1_g: float = 0.130
    k2_override: float = 1.0
    wind_roof_uplift_kn_m2: float = 0.0
    seismic_ah: float = 0.0  # engineer-specified horizontal coefficient; 0 disables

    @property
    def seismic_zone(self) -> str:
        """Active seismic zone for the selected code family."""
        return self.asce_seismic_zone if self.code_family == "ASCE7" else self.is_seismic_zone


@dataclass(frozen=True)
class MezzanineLevel:
    """One mezzanine floor strip in the transverse (width) direction.

    ``col_spacings_m`` are bay widths along the building width (X), e.g. 3@5 →
    columns at start, start+5, start+10, start+15.
    ``joist_spacing_m`` is the spacing along the building length (Z).
    """

    height_m: float = 3.5
    start_m: float = 0.0
    width_m: float = 15.0
    col_spacings_m: Tuple[float, ...] = (5.0, 5.0, 5.0)
    joist_spacing_m: float = 1.5
    dead_kn_m2: float = 3.5
    collateral_kn_m2: float = 0.25
    live_kn_m2: float = 3.75
    blockwall_kn_m: float = 0.0

    def column_xs(self) -> List[float]:
        """Absolute X positions of mezz columns (including start and end)."""
        xs = [float(self.start_m)]
        x = float(self.start_m)
        for sp in self.col_spacings_m:
            x += float(sp)
            xs.append(x)
        end = float(self.start_m) + float(self.width_m)
        if abs(xs[-1] - end) > 1e-6:
            # If spacings don't sum to width, force the end line
            if xs[-1] < end - 1e-9:
                xs.append(end)
            else:
                xs[-1] = end
        return xs

    def to_dict(self) -> dict:
        return {
            "height_m": self.height_m,
            "start_m": self.start_m,
            "width_m": self.width_m,
            "col_spacings_m": list(self.col_spacings_m),
            "joist_spacing_m": self.joist_spacing_m,
            "dead_kn_m2": self.dead_kn_m2,
            "collateral_kn_m2": self.collateral_kn_m2,
            "live_kn_m2": self.live_kn_m2,
            "blockwall_kn_m": self.blockwall_kn_m,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "MezzanineLevel":
        data = data or {}
        spacings = data.get("col_spacings_m")
        if spacings is None and data.get("col_spacing_m"):
            # legacy single spacing → one bay of that width if width known
            w = float(data.get("width_m", 0) or 0)
            s = float(data.get("col_spacing_m") or 0)
            if w > 0 and s > 0:
                n = max(1, int(round(w / s)))
                spacings = [s] * n
            else:
                spacings = [s] if s > 0 else [5.0]
        return cls(
            height_m=float(data.get("height_m", 3.5) or 3.5),
            start_m=float(data.get("start_m", 0.0) or 0.0),
            width_m=float(data.get("width_m", 15.0) or 15.0),
            col_spacings_m=tuple(float(v) for v in (spacings or (5.0, 5.0, 5.0))),
            joist_spacing_m=float(data.get("joist_spacing_m", 1.5) or 1.5),
            dead_kn_m2=float(data.get("dead_kn_m2", 3.5) or 3.5),
            collateral_kn_m2=float(data.get("collateral_kn_m2", 0.25) or 0.25),
            live_kn_m2=float(data.get("live_kn_m2", 3.75) or 3.75),
            blockwall_kn_m=float(data.get("blockwall_kn_m", 0.0) or 0.0),
        )


@dataclass(frozen=True)
class MezzanineInput:
    """Mezzanine floors — one or more levels, optional flat-roof-only mode."""

    enabled: bool = False
    flat_roof_mezz_only: bool = False
    connection_type: str = "pinned"  # pinned | fixed (mezz column bases)
    levels: Tuple[MezzanineLevel, ...] = ()
    # Legacy single-level fields (used when ``levels`` is empty)
    width_m: float = 0.0
    height_m: float = 0.0
    col_spacing_m: float = 0.0
    dead_kn_m2: float = 0.0
    live_kn_m2: float = 0.0
    collateral_kn_m2: float = 0.0

    def resolved_levels(self) -> Tuple[MezzanineLevel, ...]:
        if self.levels:
            return self.levels
        if self.enabled and self.width_m > 0 and self.height_m > 0:
            sp = self.col_spacing_m if self.col_spacing_m > 0 else self.width_m
            n = max(1, int(round(self.width_m / sp))) if sp > 0 else 1
            spacings = tuple([sp] * n)
            # Adjust last bay so sum ≈ width
            total = sum(spacings)
            if abs(total - self.width_m) > 1e-6 and n >= 1:
                adjusted = list(spacings[:-1]) + [self.width_m - sum(spacings[:-1])]
                spacings = tuple(max(0.1, v) for v in adjusted)
            return (
                MezzanineLevel(
                    height_m=self.height_m,
                    start_m=0.0,
                    width_m=self.width_m,
                    col_spacings_m=spacings,
                    dead_kn_m2=self.dead_kn_m2,
                    live_kn_m2=self.live_kn_m2,
                    collateral_kn_m2=self.collateral_kn_m2,
                ),
            )
        return ()

    def to_dict(self) -> dict:
        levels = self.resolved_levels()
        primary = levels[0] if levels else None
        return {
            "enabled": self.enabled,
            "flat_roof_mezz_only": self.flat_roof_mezz_only,
            "connection_type": self.connection_type,
            "levels": [lv.to_dict() for lv in levels],
            # Convenience mirrors for preview / older readers
            "width_m": primary.width_m if primary else self.width_m,
            "height_m": primary.height_m if primary else self.height_m,
            "start_m": primary.start_m if primary else 0.0,
            "col_spacing_m": (
                primary.col_spacings_m[0]
                if primary and primary.col_spacings_m
                else self.col_spacing_m
            ),
            "col_spacings_m": list(primary.col_spacings_m) if primary else [],
            "joist_spacing_m": primary.joist_spacing_m if primary else 1.5,
            "dead_kn_m2": primary.dead_kn_m2 if primary else self.dead_kn_m2,
            "live_kn_m2": primary.live_kn_m2 if primary else self.live_kn_m2,
            "collateral_kn_m2": (
                primary.collateral_kn_m2 if primary else self.collateral_kn_m2
            ),
            "blockwall_kn_m": primary.blockwall_kn_m if primary else 0.0,
        }


@dataclass(frozen=True)
class DeflectionLimits:
    """Serviceability deflection limits (denominator of Span/N or H/N).

    Vertical limits apply to rafters (L / N).
    Horizontal limits apply to column sway (H / N, H = eave height).
    """

    rafter_total_load_L_over: float = 120.0  # DL+LL
    rafter_live_load_L_over: float = 180.0
    column_wind_crane_H_over: float = 75.0
    column_seismic_H_over: float = 75.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "DeflectionLimits":
        data = data or {}
        return cls(
            rafter_total_load_L_over=float(
                data.get("rafter_total_load_L_over", 120.0) or 120.0
            ),
            rafter_live_load_L_over=float(
                data.get("rafter_live_load_L_over", 180.0) or 180.0
            ),
            column_wind_crane_H_over=float(
                data.get("column_wind_crane_H_over", 75.0) or 75.0
            ),
            column_seismic_H_over=float(
                data.get("column_seismic_H_over", 75.0) or 75.0
            ),
        )


@dataclass(frozen=True)
class RoofMonitorInput:
    """Clerestory / roof monitor sitting on the ridge (drawn pink in 2D)."""

    enabled: bool = False
    throat_width_m: float = 3.0
    height_m: float = 1.5
    extension_m: float = 0.75

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SideLeanTo:
    """Mono-slope lean-to attached to left or right eave."""

    enabled: bool = False
    width_m: float = 5.0
    slope_x10: float = 1.0  # X in X:10
    conn_height_m: Optional[float] = None  # None → connect at eave
    base: str = "pinned"

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "width_m": self.width_m,
            "slope_x10": self.slope_x10,
            "conn_height_m": self.conn_height_m,
            "base": self.base,
        }


@dataclass(frozen=True)
class SideRoofExtension:
    """Horizontal roof projection beyond the eave (purple in 2D)."""

    enabled: bool = False
    projection_m: float = 0.8

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SideFascia:
    """Vertical fascia drop at the eave (pink in 2D)."""

    enabled: bool = False
    height_m: float = 1.25
    cover_ridge: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SideCanopy:
    """Canopy / porch off the sidewall column (green/orange in 2D)."""

    enabled: bool = False
    width_m: float = 3.0
    height_on_col_m: float = 3.0
    slope_x10: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BuildingExtensions:
    """All optional side / roof extensions (STAGen-style)."""

    lean_to_left: SideLeanTo = field(default_factory=SideLeanTo)
    lean_to_right: SideLeanTo = field(default_factory=SideLeanTo)
    roof_ext_left: SideRoofExtension = field(default_factory=SideRoofExtension)
    roof_ext_right: SideRoofExtension = field(default_factory=SideRoofExtension)
    fascia_left: SideFascia = field(default_factory=SideFascia)
    fascia_right: SideFascia = field(default_factory=SideFascia)
    canopy_left: SideCanopy = field(default_factory=SideCanopy)
    canopy_right: SideCanopy = field(default_factory=SideCanopy)
    roof_monitor: RoofMonitorInput = field(default_factory=RoofMonitorInput)

    def to_dict(self) -> dict:
        return {
            "lean_to_left": self.lean_to_left.to_dict(),
            "lean_to_right": self.lean_to_right.to_dict(),
            "roof_ext_left": self.roof_ext_left.to_dict(),
            "roof_ext_right": self.roof_ext_right.to_dict(),
            "fascia_left": self.fascia_left.to_dict(),
            "fascia_right": self.fascia_right.to_dict(),
            "canopy_left": self.canopy_left.to_dict(),
            "canopy_right": self.canopy_right.to_dict(),
            "roof_monitor": self.roof_monitor.to_dict(),
        }


@dataclass(frozen=True)
class CraneInput:
    """EOT crane runway annotation / future load generation (yellow in 2D)."""

    enabled: bool = False
    name: str = "Crane 1"
    manufacturer: str = "Konecranes"
    capacity_kn: float = 50.0
    hook_height_m: float = 4.5
    runway_height_m: float = 0.0  # 0 → use hook_height_m
    bridge_kn: float = 0.0
    trolley_kn: float = 0.0
    wheels_per_end: int = 2
    span_index: int = 1

    @property
    def effective_height_m(self) -> float:
        return self.runway_height_m if self.runway_height_m > 0 else self.hook_height_m

    def to_dict(self) -> dict:
        d = asdict(self)
        d["effective_height_m"] = self.effective_height_m
        return d


@dataclass(frozen=True)
class BuildingGeometryInput:
    """Full building definition for geometry generation."""

    width_spans_m: Tuple[float, ...]
    length_m: float
    sidewall_spacings_m: Tuple[float, ...]
    eave_height_m: float
    roof_pitch_1_to_n: float  # N in 1:N
    frame_type: FrameType = FrameType.CLEAR_SPAN
    ffl_level_m: float = 0.0
    blockwall_height_m: float = 0.0
    # Ridge distance from left eave (m). None / ridge_auto → mid-width (or type default).
    ridge_distance_m: Optional[float] = None
    ridge_auto: bool = True
    roof_loads: RoofLoadsInput = field(default_factory=RoofLoadsInput)
    wind_seismic: WindSeismicInput = field(default_factory=WindSeismicInput)
    mezzanine: MezzanineInput = field(default_factory=MezzanineInput)
    crane: CraneInput = field(default_factory=CraneInput)
    extensions: BuildingExtensions = field(default_factory=BuildingExtensions)
    # Kept for older callers; prefer extensions.roof_monitor
    roof_monitor: RoofMonitorInput = field(default_factory=RoofMonitorInput)
    load_combination_type: str = "IS800-2007-LSD"
    deflection_limits: DeflectionLimits = field(default_factory=DeflectionLimits)

    def resolved_roof_monitor(self) -> RoofMonitorInput:
        if self.extensions.roof_monitor.enabled:
            return self.extensions.roof_monitor
        return self.roof_monitor

    @property
    def span_m(self) -> float:
        return spacing_total(list(self.width_spans_m))

    @property
    def number_of_width_spans(self) -> int:
        return len(self.width_spans_m)

    @property
    def number_of_bays(self) -> int:
        return len(self.sidewall_spacings_m)

    @property
    def number_of_frames(self) -> int:
        return self.number_of_bays + 1

    @property
    def frame_stations_z(self) -> List[float]:
        z = 0.0
        stations = [0.0]
        for bay in self.sidewall_spacings_m:
            z += bay
            stations.append(z)
        return stations

    def roof_rise(self, run_m: float) -> float:
        if self.roof_pitch_1_to_n <= 0:
            return 0.0
        return run_m / self.roof_pitch_1_to_n

    def ridge_height_for_run(self, run_m: float) -> float:
        return self.eave_height_m + self.roof_rise(run_m)

    def resolved_ridge_x(self) -> float:
        total = self.span_m
        if self.ridge_auto or self.ridge_distance_m is None:
            return total / 2.0
        return float(self.ridge_distance_m)


def resolve_width_spans(
    frame_type: FrameType,
    width_values: Sequence[float],
    int_col_values: Sequence[float],
) -> Tuple[float, ...]:
    """Combine building width + int. col. spacing into span list.

    Rules:
    - Clear Span / Asym Gable / Mono-Slope: no interior columns; single span.
    - Multi-Span / Multi-Gable: prefer multi-token width; else int-col list
      that sums to total width.
    """
    ft = coerce_frame_type(frame_type)
    widths = [float(v) for v in width_values if float(v) > 0]
    ints = [float(v) for v in int_col_values if float(v) > 0]

    if not widths:
        raise ValidationError(["Building width is required."])

    total = spacing_total(widths)

    if not frame_allows_interior_columns(ft):
        if ints:
            raise ValidationError(
                [
                    f"{ft.value.replace('_', ' ').title()} takes no interior columns — "
                    "set Int. Col. Spacing to 0 (a non-zero spacing is refused)."
                ]
            )
        return (total,)

    if len(widths) >= 2:
        return tuple(widths)

    if len(ints) >= 1:
        if abs(spacing_total(ints) - total) > 1e-6:
            raise ValidationError(
                [
                    "Int. Col. Spacing must sum to Building Width "
                    f"(width={total:g} m, spacing sum={spacing_total(ints):g} m)."
                ]
            )
        # If a single token equals total width, that is still one span (no int col)
        if len(ints) == 1:
            raise ValidationError(
                [
                    f"{ft.value} requires at least two width spans "
                    "(example width 2@20, or Int. Col. Spacing 20+20)."
                ]
            )
        return tuple(ints)

    raise ValidationError(
        [
            f"{ft.value} requires interior column layout — use width like 2@30 "
            "or set Int. Col. Spacing (e.g. 20+20)."
        ]
    )


def _column_xs(spans: Sequence[float]) -> List[float]:
    xs = [0.0]
    acc = 0.0
    for s in spans:
        acc += s
        xs.append(acc)
    return xs


def _profile_nodes_xy(
    params: BuildingGeometryInput,
) -> List[Tuple[float, float, str]]:
    """Return ordered (x, y_above_ffl, role) points for one frame profile.

    Roles: base_col, eave, ridge, valley, int_col_top
    Bases are added separately at FFL.
    """
    spans = list(params.width_spans_m)
    cols = _column_xs(spans)
    He = params.eave_height_m
    ft = coerce_frame_type(params.frame_type)
    total = params.span_m
    points: List[Tuple[float, float, str]] = []

    # Flat roof (mezz-only): zero slope through all column lines
    if params.mezzanine.enabled and params.mezzanine.flat_roof_mezz_only:
        out: List[Tuple[float, float, str]] = []
        for i, x in enumerate(cols):
            role = "eave" if i == 0 or i == len(cols) - 1 else "int_col_top"
            out.append((x, He, role))
        return out

    if ft == FrameType.CLEAR_SPAN:
        ridge_x = params.resolved_ridge_x()
        # Symmetric rise reference uses half-width; offset ridge keeps equal eaves.
        Hr = params.ridge_height_for_run(total / 2.0)
        return [
            (0.0, He, "eave"),
            (ridge_x, Hr, "ridge"),
            (total, He, "eave"),
        ]

    if ft == FrameType.ASYM_GABLE:
        ridge_x = params.resolved_ridge_x()
        if ridge_x <= 0 or ridge_x >= total:
            ridge_x = total / 2.0
        Hr = params.ridge_height_for_run(total / 2.0)
        return [
            (0.0, He, "eave"),
            (ridge_x, Hr, "ridge"),
            (total, He, "eave"),
        ]

    if ft == FrameType.MONO_SLOPE:
        # Low eave at left, high eave (treated as ridge) at right.
        Hr = params.ridge_height_for_run(total)
        return [
            (0.0, He, "eave"),
            (total, Hr, "ridge"),
        ]

    if ft == FrameType.MULTI_SPAN:
        ridge_x = params.resolved_ridge_x()
        Hr = params.ridge_height_for_run(total / 2.0)
        # Roof polyline: left eave → ridge → right eave
        roof = [(0.0, He), (ridge_x, Hr), (total, He)]

        def roof_y_at(x: float) -> float:
            for (x0, y0), (x1, y1) in zip(roof[:-1], roof[1:]):
                if x0 - 1e-9 <= x <= x1 + 1e-9:
                    if abs(x1 - x0) < 1e-12:
                        return y0
                    t = (x - x0) / (x1 - x0)
                    return y0 + t * (y1 - y0)
            return He

        points.append((0.0, He, "eave"))
        for x in cols[1:-1]:
            if abs(x - ridge_x) < 1e-6:
                points.append((ridge_x, Hr, "ridge"))
            else:
                points.append((x, roof_y_at(x), "int_col_top"))
        if abs(ridge_x - cols[0]) > 1e-6 and abs(ridge_x - cols[-1]) > 1e-6:
            if not any(abs(p[0] - ridge_x) < 1e-6 for p in points):
                points.append((ridge_x, Hr, "ridge"))
        points.append((total, He, "eave"))
        points = sorted(
            set((round(x, 9), round(y, 9), r) for x, y, r in points),
            key=lambda p: p[0],
        )
        merged: Dict[float, Tuple[float, float, str]] = {}
        priority = {"ridge": 3, "eave": 2, "int_col_top": 1, "valley": 1}
        for x, y, r in points:
            prev = merged.get(x)
            if prev is None or priority.get(r, 0) >= priority.get(prev[2], 0):
                merged[x] = (x, y, r)
        return [merged[k] for k in sorted(merged)]

    # multi_gable
    points.append((0.0, He, "eave"))
    for i, span in enumerate(spans):
        x0 = cols[i]
        x1 = cols[i + 1]
        ridge_x = 0.5 * (x0 + x1)
        Hr = params.ridge_height_for_run(span / 2.0)
        points.append((ridge_x, Hr, "ridge"))
        if i < len(spans) - 1:
            points.append((x1, He, "valley"))
        else:
            points.append((x1, He, "eave"))
    return points


def validate_building_input(params: BuildingGeometryInput) -> List[str]:
    errors: List[str] = []
    import math
    def check_numbers(value, path="input"):
        if isinstance(value, dict):
            for key, item in value.items():
                check_numbers(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for item in value:
                check_numbers(item, path)
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{path} must be finite.")
    check_numbers(asdict(params))
    if errors:
        return errors
    if not params.sidewall_spacings_m or any(v <= 0 for v in params.sidewall_spacings_m):
        errors.append("Bay spacings must be positive.")
    if not params.width_spans_m or any(v <= 0 for v in params.width_spans_m):
        errors.append("Width spacings must be positive.")
    if any(v < 0 for v in asdict(params.roof_loads).values()):
        errors.append("Roof load intensities cannot be negative.")
    ws = params.wind_seismic
    if any(v <= 0 for v in (ws.k1_risk, ws.k2_override, ws.k3_topography, ws.k4_importance, ws.response_factor_r)):
        errors.append("Wind factors and response factor R must be positive.")
    if ws.wind_speed_mps < 0 or ws.wind_roof_uplift_kn_m2 < 0 or ws.seismic_ah < 0:
        errors.append("Wind speed, uplift and seismic coefficient must be nonnegative.")
    ft = coerce_frame_type(params.frame_type)
    if params.span_m < 5 or params.span_m > 120:
        errors.append("Building width must be between 5 m and 120 m.")
    if params.length_m < 5 or params.length_m > 400:
        errors.append("Building length must be between 5 m and 400 m.")
    if abs(spacing_total(list(params.sidewall_spacings_m)) - params.length_m) > 1e-6:
        errors.append(
            "Building length must equal the sum of bay / sidewall spacings "
            f"(sum={spacing_total(list(params.sidewall_spacings_m)):.6g} m)."
        )
    if params.eave_height_m < 3 or params.eave_height_m > 40:
        errors.append("Eave height must be between 3 m and 40 m.")
    flat_mezz = params.mezzanine.enabled and params.mezzanine.flat_roof_mezz_only
    if not flat_mezz:
        if params.roof_pitch_1_to_n < 2 or params.roof_pitch_1_to_n > 60:
            errors.append("Roof pitch 1:N — N must be between 2 and 60.")
    if params.ffl_level_m < 0 or params.ffl_level_m > 5:
        errors.append("FFL level must be between 0 and 5 m.")
    if params.blockwall_height_m < 0 or params.blockwall_height_m > params.eave_height_m:
        errors.append("Blockwall height must be between 0 and eave height.")

    if not frame_allows_interior_columns(ft) and len(params.width_spans_m) > 1:
        errors.append(
            f"{ft.value} does not accept interior columns "
            "(use a single building width)."
        )
    if ft in (FrameType.MULTI_SPAN, FrameType.MULTI_GABLE):
        if len(params.width_spans_m) < 2:
            errors.append(
                f"{ft.value} requires at least two width spans "
                "(example: 2@30)."
            )

    ridge_x = params.resolved_ridge_x()
    if ft in (FrameType.CLEAR_SPAN, FrameType.ASYM_GABLE, FrameType.MULTI_SPAN):
        if ridge_x <= 0 or ridge_x >= params.span_m:
            errors.append("Ridge distance must be between 0 and building width.")

    if params.mezzanine.enabled:
        levels = params.mezzanine.resolved_levels()
        if not levels:
            errors.append("Mezzanine is enabled but no levels are defined.")
        for i, lv in enumerate(levels, start=1):
            if lv.height_m <= 0:
                errors.append(f"Mezzanine level {i}: height must be > 0.")
            if lv.width_m <= 0:
                errors.append(f"Mezzanine level {i}: width must be > 0.")
            if not lv.col_spacings_m or any(s <= 0 for s in lv.col_spacings_m):
                errors.append(f"Mezzanine level {i}: column spacings must be > 0.")
            if lv.joist_spacing_m <= 0:
                errors.append(f"Mezzanine level {i}: joist spacing must be > 0.")
            if any(v < 0 for v in (lv.dead_kn_m2, lv.live_kn_m2, lv.collateral_kn_m2, lv.blockwall_kn_m)):
                errors.append(f"Mezzanine level {i}: loads must be nonnegative.")
            if sum(lv.col_spacings_m) > lv.width_m + 1e-6:
                errors.append(f"Mezzanine level {i}: column spacings exceed floor width.")
            if not params.mezzanine.flat_roof_mezz_only:
                if lv.start_m < -1e-9:
                    errors.append(f"Mezzanine level {i}: start must be ≥ 0.")
                if lv.start_m + lv.width_m > params.span_m + 1e-6:
                    errors.append(
                        f"Mezzanine level {i}: start+width must be ≤ building width."
                    )
                if lv.height_m >= params.eave_height_m - 1e-9:
                    errors.append(
                        f"Mezzanine level {i}: height must be < eave height."
                    )
            conn = (params.mezzanine.connection_type or "pinned").lower()
            if conn not in ("pinned", "fixed"):
                errors.append("Mezzanine connection type must be Pinned or Fixed.")
    if params.crane.enabled:
        if params.crane.capacity_kn <= 0 or params.crane.bridge_kn < 0 or params.crane.trolley_kn < 0 or params.crane.wheels_per_end < 1:
            errors.append("Crane capacity and wheel count must be positive; bridge/trolley weights must be nonnegative.")
        if params.crane.span_index < 1 or params.crane.span_index > len(params.width_spans_m):
            errors.append("Crane span number is outside the building spans.")
        ch = params.crane.effective_height_m
        if ch <= 0 or ch >= params.eave_height_m:
            errors.append(
                "Crane hook / runway height must be > 0 and < eave height."
            )
    rm = params.resolved_roof_monitor()
    if rm.enabled:
        center = params.resolved_ridge_x()
        if center - rm.throat_width_m / 2 <= 0 or center + rm.throat_width_m / 2 >= params.span_m:
            errors.append("Roof monitor throat must fit inside the roof at the selected ridge.")
        if rm.throat_width_m <= 0 or rm.throat_width_m >= params.span_m:
            errors.append("Roof monitor throat width must be > 0 and < building width.")
        if rm.height_m <= 0:
            errors.append("Roof monitor height must be > 0.")
        if rm.extension_m < 0:
            errors.append("Roof monitor extension must be ≥ 0.")
    for side, lt in (("left", params.extensions.lean_to_left), ("right", params.extensions.lean_to_right)):
        if lt.enabled and lt.width_m <= 0:
            errors.append(f"Lean-to ({side}): width must be > 0.")
        if lt.enabled:
            h = params.eave_height_m if lt.conn_height_m is None else lt.conn_height_m
            if h <= 0 or h > params.eave_height_m or h - lt.width_m * lt.slope_x10 / 10 <= 0:
                errors.append(f"Lean-to ({side}): connection must be on column and outer roof above ground.")
    for side, c in (("left", params.extensions.canopy_left), ("right", params.extensions.canopy_right)):
        if c.enabled:
            if c.width_m <= 0:
                errors.append(f"Canopy ({side}): width must be > 0.")
            if c.height_on_col_m <= 0 or c.height_on_col_m > params.eave_height_m:
                errors.append(
                    f"Canopy ({side}): height on column must be > 0 and ≤ eave."
                )
            if c.height_on_col_m - c.width_m * c.slope_x10 / 10 <= 0:
                errors.append(f"Canopy ({side}): roof tip must be above ground.")
    for side in ("left", "right"):
        roof = getattr(params.extensions, "roof_ext_" + side)
        fascia = getattr(params.extensions, "fascia_" + side)
        if roof.enabled and roof.projection_m <= 0:
            errors.append(f"Roof extension ({side}): projection must be positive.")
        if fascia.enabled and fascia.height_m <= 0:
            errors.append(f"Fascia ({side}): height must be positive.")
    return errors


def generate_peb_model(params: BuildingGeometryInput) -> StructuralModel:
    """Generate 3D nodes/members for all frames along building length."""
    params = _apply_flat_roof_mezz_override(params)
    errors = validate_building_input(params)
    if errors:
        raise ValidationError(errors)

    model = StructuralModel()
    profile = _profile_nodes_xy(params)
    col_xs = _column_xs(params.width_spans_m)
    ffl = params.ffl_level_m
    stations = params.frame_stations_z

    node_id = 1
    member_id = 1
    # Map (frame_idx, x_rounded, kind) -> node id ; kind in base|top
    top_ids: Dict[Tuple[int, float], int] = {}
    base_ids: Dict[Tuple[int, float], int] = {}

    for frame_idx, z in enumerate(stations):
        ftag = frame_idx + 1

        # Base nodes under every column line
        for x in col_xs:
            model.add_node(
                Node(
                    id=node_id,
                    x=x,
                    y=ffl,
                    z=z,
                    label=f"F{ftag}-B@{x:g}",
                )
            )
            base_ids[(frame_idx, round(x, 9))] = node_id
            node_id += 1

        # Roof / eave / ridge / valley nodes
        for x, y_rel, role in profile:
            y = ffl + y_rel
            # If a column exists at this x, reuse intent: top node is separate
            model.add_node(
                Node(
                    id=node_id,
                    x=x,
                    y=y,
                    z=z,
                    label=f"F{ftag}-{role}@{x:g}",
                )
            )
            top_ids[(frame_idx, round(x, 9))] = node_id
            node_id += 1

        # Columns: base → top at each column x
        for x in col_xs:
            xr = round(x, 9)
            # Top may be eave/valley/ridge/int_col_top; if no top at exact x,
            # create vertical to interpolated — profile should include column tops
            # for multi_span; for single_gable only exterior columns.
            if (frame_idx, xr) not in top_ids:
                # Interior column under single-gable multi width: project to roof
                # Find roof y from profile segments
                y_rel = _interp_profile_y(profile, x)
                model.add_node(
                    Node(
                        id=node_id,
                        x=x,
                        y=ffl + y_rel,
                        z=z,
                        label=f"F{ftag}-inttop@{x:g}",
                    )
                )
                top_ids[(frame_idx, xr)] = node_id
                node_id += 1

            model.add_member(
                Member(
                    id=member_id,
                    start_node=base_ids[(frame_idx, xr)],
                    end_node=top_ids[(frame_idx, xr)],
                    member_type="column",
                    label=f"F{ftag}-COL@{x:g}",
                )
            )
            member_id += 1

        # Rafters along profile order
        ordered_tops = []
        for x, _y, _role in profile:
            ordered_tops.append(top_ids[(frame_idx, round(x, 9))])
        # Include any extra int tops not on profile (sorted by x)
        extra = [
            (x, nid)
            for (fi, x), nid in top_ids.items()
            if fi == frame_idx and nid not in ordered_tops
        ]
        if extra:
            # merge by x into chain
            pts = [(model.nodes[nid].x, nid) for nid in ordered_tops]
            pts.extend(extra)
            pts = sorted(set(pts), key=lambda t: t[0])
            ordered_tops = [nid for _x, nid in pts]

        for a, b in zip(ordered_tops[:-1], ordered_tops[1:]):
            # Flat-roof mezz-only: mark roof members as mezzanine beams
            mtype = (
                "mezzanine_beam"
                if params.mezzanine.enabled and params.mezzanine.flat_roof_mezz_only
                else "rafter"
            )
            model.add_member(
                Member(
                    id=member_id,
                    start_node=a,
                    end_node=b,
                    member_type=mtype,
                    label=f"F{ftag}-RF-{a}-{b}",
                )
            )
            member_id += 1

    # Optional mezzanine inside the main frame (not flat-roof-only)
    if params.mezzanine.enabled and not params.mezzanine.flat_roof_mezz_only:
        member_id, node_id = _add_mezzanine(
            model, params, stations, ffl, node_id, member_id
        )

    ridge_heights = sorted(
        {ffl + y for _x, y, role in profile if role == "ridge"},
        reverse=True,
    )
    model.metadata.update(
        {
            "span_m": params.span_m,
            "width_spans_m": list(params.width_spans_m),
            "length_m": params.length_m,
            "sidewall_spacings_m": list(params.sidewall_spacings_m),
            "eave_height_m": params.eave_height_m,
            "roof_pitch_1_to_n": params.roof_pitch_1_to_n,
            "frame_type": coerce_frame_type(params.frame_type).value,
            "ffl_level_m": ffl,
            "blockwall_height_m": params.blockwall_height_m,
            "ridge_distance_m": params.resolved_ridge_x(),
            "ridge_auto": params.ridge_auto,
            "ridge_height_m": ridge_heights[0] if ridge_heights else ffl + params.eave_height_m,
            "ridge_heights_m": ridge_heights,
            "number_of_bays": params.number_of_bays,
            "number_of_frames": params.number_of_frames,
            "profile_xy": [(x, y, r) for x, y, r in profile],
            "column_xs": col_xs,
            "roof_loads": {
                "dead_kn_m2": params.roof_loads.dead_kn_m2,
                "collateral_kn_m2": params.roof_loads.collateral_kn_m2,
                "live_kn_m2": params.roof_loads.live_kn_m2,
            },
            "wind_seismic": {
                "wind_speed_mps": params.wind_seismic.wind_speed_mps,
                "building_condition": params.wind_seismic.building_condition,
                "load_combination_label": params.wind_seismic.load_combination_label,
                "code_family": params.wind_seismic.code_family,
                "terrain_category": params.wind_seismic.terrain_category,
                "k1_risk": params.wind_seismic.k1_risk,
                "k3_topography": params.wind_seismic.k3_topography,
                "k4_importance": params.wind_seismic.k4_importance,
                "is_seismic_zone": params.wind_seismic.is_seismic_zone,
                "soil_type": params.wind_seismic.soil_type,
                "response_factor_r": params.wind_seismic.response_factor_r,
                "exposure": params.wind_seismic.exposure,
                "site_class": params.wind_seismic.site_class,
                "asce_seismic_zone": params.wind_seismic.asce_seismic_zone,
                "seismic_zone": params.wind_seismic.seismic_zone,
                "use_dm": params.wind_seismic.use_dm,
                "use_adm": params.wind_seismic.use_adm,
                "use_sm": params.wind_seismic.use_sm,
                "use_others": params.wind_seismic.use_others,
                "ss_g": params.wind_seismic.ss_g,
                "s1_g": params.wind_seismic.s1_g,
                "k2_override": params.wind_seismic.k2_override,
                "wind_roof_uplift_kn_m2": params.wind_seismic.wind_roof_uplift_kn_m2,
                "seismic_ah": params.wind_seismic.seismic_ah,
            },
            "mezzanine": params.mezzanine.to_dict(),
            "crane": params.crane.to_dict(),
            "extensions": params.extensions.to_dict(),
            "roof_monitor": params.resolved_roof_monitor().to_dict(),
            "load_combination_type": params.load_combination_type,
            "deflection_limits": params.deflection_limits.to_dict(),
            "milestone": 2,
            "description": "PEB frames with optional multi-span/gable geometry",
        }
    )
    from app.geometry.connectivity import add_extensions, connect_intersections
    add_extensions(model, params, profile)
    connect_intersections(model)
    return model


def _apply_flat_roof_mezz_override(
    params: BuildingGeometryInput,
) -> BuildingGeometryInput:
    """When Flat Roof (Mezz Only), drive building geometry from the mezz level."""
    mz = params.mezzanine
    if not (mz.enabled and mz.flat_roof_mezz_only):
        return params
    levels = mz.resolved_levels()
    if not levels:
        return params
    lv = levels[0]
    spacings = tuple(lv.col_spacings_m) if lv.col_spacings_m else (lv.width_m,)
    # Ensure spacings cover width
    total = sum(spacings)
    if abs(total - lv.width_m) > 1e-3 and lv.width_m > 0:
        n = max(1, len(spacings))
        spacings = tuple([lv.width_m / n] * n)
    return BuildingGeometryInput(
        width_spans_m=spacings,
        length_m=params.length_m,
        sidewall_spacings_m=params.sidewall_spacings_m,
        eave_height_m=lv.height_m,
        roof_pitch_1_to_n=1.0e6,  # effectively flat
        frame_type=FrameType.MULTI_SPAN if len(spacings) > 1 else FrameType.CLEAR_SPAN,
        ffl_level_m=params.ffl_level_m,
        blockwall_height_m=0.0,
        ridge_distance_m=None,
        ridge_auto=True,
        roof_loads=params.roof_loads,
        wind_seismic=params.wind_seismic,
        mezzanine=mz,
        crane=CraneInput(enabled=False),
        extensions=BuildingExtensions(),
        roof_monitor=RoofMonitorInput(enabled=False),
        load_combination_type=params.load_combination_type,
        deflection_limits=params.deflection_limits,
    )


def _interp_profile_y(
    profile: Sequence[Tuple[float, float, str]], x: float
) -> float:
    pts = [(p[0], p[1]) for p in profile]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x0 - 1e-9 <= x <= x1 + 1e-9:
            if abs(x1 - x0) < 1e-12:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _add_mezzanine(
    model: StructuralModel,
    params: BuildingGeometryInput,
    stations: Sequence[float],
    ffl: float,
    node_id: int,
    member_id: int,
) -> Tuple[int, int]:
    """Embed mezzanine floors in each frame: beams along width, columns to FFL.

    Column lines come from each level's ``col_spacings_m`` (transverse).
    Members are generated at every main-frame station along the length.
    """
    main_col_xs = set(round(x, 6) for x in _column_xs(params.width_spans_m))
    levels = params.mezzanine.resolved_levels()

    # Per-level, per-frame top node ids keyed by rounded x
    # and longitudinal tracking for beams along Z
    for li, lv in enumerate(levels):
        xs = [round(x, 6) for x in lv.column_xs()]
        y = ffl + lv.height_m
        prev_tops: Optional[Dict[float, int]] = None

        for zi, z in enumerate(stations):
            tops: Dict[float, int] = {}
            for xi, x in enumerate(xs):
                # Floor node at mezz height
                n_top = node_id
                model.add_node(
                    Node(
                        id=n_top,
                        x=x,
                        y=y,
                        z=z,
                        label=f"MZ{li+1}-T{zi+1}@{x:g}",
                    )
                )
                node_id += 1
                tops[x] = n_top

                # Interior mezz column (skip if coincides with main frame column line —
                # floor still attaches via its own node; a short stub is avoided)
                on_main = any(abs(x - mx) < 1e-4 for mx in main_col_xs)
                if not on_main:
                    n_base = node_id
                    model.add_node(
                        Node(
                            id=n_base,
                            x=x,
                            y=ffl,
                            z=z,
                            label=f"MZ{li+1}-B{zi+1}@{x:g}",
                        )
                    )
                    node_id += 1
                    model.add_member(
                        Member(
                            id=member_id,
                            start_node=n_base,
                            end_node=n_top,
                            member_type="mezzanine_column",
                            label=f"MZ{li+1}-COL-{zi+1}-{xi+1}",
                        )
                    )
                    member_id += 1

            # Transverse floor beams along X
            for a, b in zip(xs[:-1], xs[1:]):
                model.add_member(
                    Member(
                        id=member_id,
                        start_node=tops[a],
                        end_node=tops[b],
                        member_type="mezzanine_beam",
                        label=f"MZ{li+1}-BM-{zi+1}-{a:g}-{b:g}",
                    )
                )
                member_id += 1

            # Longitudinal beams between frames
            if prev_tops is not None:
                for x in xs:
                    model.add_member(
                        Member(
                            id=member_id,
                            start_node=prev_tops[x],
                            end_node=tops[x],
                            member_type="mezzanine_beam",
                            label=f"MZ{li+1}-LG-{zi+1}@{x:g}",
                        )
                    )
                    member_id += 1
            prev_tops = tops

    return member_id, node_id


# Backward-compatible helpers used by older tests / simple callers
def building_from_simple(
    span_m: float,
    length_m: float,
    eave_height_m: float,
    roof_slope_deg: float,
    bay_spacing_m: float,
) -> BuildingGeometryInput:
    """Create BuildingGeometryInput from Milestone-1 style fields."""
    import math

    # Convert degrees to approximate 1:N pitch: N = 1/tan(θ)
    if roof_slope_deg <= 0:
        n = 1000.0
    else:
        n = 1.0 / math.tan(math.radians(roof_slope_deg))
    n_bays = int(round(length_m / bay_spacing_m))
    bays = tuple([bay_spacing_m] * n_bays)
    return BuildingGeometryInput(
        width_spans_m=(span_m,),
        length_m=length_m,
        sidewall_spacings_m=bays,
        eave_height_m=eave_height_m,
        roof_pitch_1_to_n=n,
        frame_type=FrameType.SINGLE_GABLE,
    )
