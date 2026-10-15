"""Pre-built PEB building templates for demos and regression tests.

Each template exercises a different 2D cross-section configuration.
Templates are geometry / input presets only — not design-code solutions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.geometry.peb_frame import (
    BuildingGeometryInput,
    CraneInput,
    FrameType,
    MezzanineInput,
    RoofLoadsInput,
    WindSeismicInput,
)
from app.geometry.spacing import parse_spacing_list


@dataclass(frozen=True)
class BuildingTemplate:
    """UI-ready preset that can be loaded into the input panel."""

    id: str
    name: str
    description: str
    width_expr: str
    length_m: float
    frame_type: FrameType
    roof_pitch_1_to_n: float
    eave_height_m: float
    ffl_level_m: float
    sidewall_expr: str
    blockwall_height_m: float = 0.0
    dead_kn_m2: float = 0.3
    collateral_kn_m2: float = 0.15
    live_kn_m2: float = 0.75
    wind_speed_mps: float = 47.0
    exposure: str = "B"
    building_condition: str = "Enclosed"
    seismic_zone: str = "2A"
    site_class: str = "B"
    mezzanine_enabled: bool = False
    mezz_width_m: float = 8.0
    mezz_height_m: float = 4.0
    mezz_col_spacing_m: float = 6.0
    crane_enabled: bool = False
    crane_name: str = "Crane 1"
    crane_capacity_kn: float = 100.0
    crane_runway_height_m: float = 6.0
    # Expected 2D checks used by tests
    expect_min_ridges: int = 1
    expect_min_columns: int = 2
    expect_has_mezzanine: bool = False
    expect_has_crane: bool = False

    def to_params(self) -> BuildingGeometryInput:
        widths = parse_spacing_list(self.width_expr, field_name="Building width")
        sidewalls = parse_spacing_list(self.sidewall_expr, field_name="Sidewall spacing")
        if len(sidewalls) == 1:
            bay = sidewalls[0]
            n = int(round(self.length_m / bay))
            if n >= 1 and abs(n * bay - self.length_m) <= 1e-6:
                sidewalls = [bay] * n
        return BuildingGeometryInput(
            width_spans_m=tuple(widths),
            length_m=self.length_m,
            sidewall_spacings_m=tuple(sidewalls),
            eave_height_m=self.eave_height_m,
            roof_pitch_1_to_n=self.roof_pitch_1_to_n,
            frame_type=self.frame_type,
            ffl_level_m=self.ffl_level_m,
            blockwall_height_m=self.blockwall_height_m,
            roof_loads=RoofLoadsInput(
                dead_kn_m2=self.dead_kn_m2,
                collateral_kn_m2=self.collateral_kn_m2,
                live_kn_m2=self.live_kn_m2,
            ),
            wind_seismic=WindSeismicInput(
                wind_speed_mps=self.wind_speed_mps,
                exposure=self.exposure,
                building_condition=self.building_condition,
                is_seismic_zone=self.seismic_zone
                if self.seismic_zone in ("I", "II", "III", "IV", "V")
                else "III",
                asce_seismic_zone=self.seismic_zone
                if self.seismic_zone not in ("I", "II", "III", "IV", "V")
                else "2A",
                site_class=self.site_class,
            ),
            mezzanine=MezzanineInput(
                enabled=self.mezzanine_enabled,
                width_m=self.mezz_width_m,
                height_m=self.mezz_height_m,
                col_spacing_m=self.mezz_col_spacing_m,
            ),
            crane=CraneInput(
                enabled=self.crane_enabled,
                name=self.crane_name,
                capacity_kn=self.crane_capacity_kn,
                runway_height_m=self.crane_runway_height_m,
            ),
        )


def _templates() -> Tuple[BuildingTemplate, ...]:
    return (
        BuildingTemplate(
            id="sg_small_warehouse",
            name="01 — Small warehouse (single gable)",
            description="20 m × 40 m classic portal, pitch 1:10",
            width_expr="20",
            length_m=40.0,
            frame_type=FrameType.SINGLE_GABLE,
            roof_pitch_1_to_n=10.0,
            eave_height_m=7.0,
            ffl_level_m=0.0,
            sidewall_expr="8@5",
            expect_min_ridges=1,
            expect_min_columns=2,
        ),
        BuildingTemplate(
            id="sg_wide_hall",
            name="02 — Wide hall (single gable)",
            description="36 m clear span, longer building",
            width_expr="36",
            length_m=72.0,
            frame_type=FrameType.SINGLE_GABLE,
            roof_pitch_1_to_n=12.0,
            eave_height_m=9.0,
            ffl_level_m=0.0,
            sidewall_expr="12@6",
            expect_min_ridges=1,
            expect_min_columns=2,
        ),
        BuildingTemplate(
            id="ms_equal_twin",
            name="03 — Multi-span twin (2@30)",
            description="Two 30 m spans, one overall ridge",
            width_expr="2@30",
            length_m=120.0,
            frame_type=FrameType.MULTI_SPAN,
            roof_pitch_1_to_n=10.0,
            eave_height_m=6.5,
            ffl_level_m=0.0,
            sidewall_expr="16@7.5",
            expect_min_ridges=1,
            expect_min_columns=3,
        ),
        BuildingTemplate(
            id="ms_triple",
            name="04 — Multi-span triple (3@20)",
            description="Three equal 20 m spans with interior columns",
            width_expr="3@20",
            length_m=60.0,
            frame_type=FrameType.MULTI_SPAN,
            roof_pitch_1_to_n=10.0,
            eave_height_m=8.0,
            ffl_level_m=0.0,
            sidewall_expr="10@6",
            expect_min_ridges=1,
            expect_min_columns=4,
        ),
        BuildingTemplate(
            id="ms_uneven",
            name="05 — Multi-span uneven (20+40)",
            description="Uneven spans; ridge offset from mid column",
            width_expr="20+40",
            length_m=48.0,
            frame_type=FrameType.MULTI_SPAN,
            roof_pitch_1_to_n=10.0,
            eave_height_m=8.0,
            ffl_level_m=0.0,
            sidewall_expr="8@6",
            expect_min_ridges=1,
            expect_min_columns=3,
        ),
        BuildingTemplate(
            id="mg_twin",
            name="06 — Multi-gable twin (2@30)",
            description="Two ridges with valley at interior column",
            width_expr="2@30",
            length_m=90.0,
            frame_type=FrameType.MULTI_GABLE,
            roof_pitch_1_to_n=10.0,
            eave_height_m=7.5,
            ffl_level_m=0.0,
            sidewall_expr="15@6",
            expect_min_ridges=2,
            expect_min_columns=3,
        ),
        BuildingTemplate(
            id="mg_triple",
            name="07 — Multi-gable triple (3@25)",
            description="Three gables across 75 m width",
            width_expr="3@25",
            length_m=100.0,
            frame_type=FrameType.MULTI_GABLE,
            roof_pitch_1_to_n=8.0,
            eave_height_m=8.0,
            ffl_level_m=0.0,
            sidewall_expr="10@10",
            expect_min_ridges=3,
            expect_min_columns=4,
        ),
        BuildingTemplate(
            id="sg_steep_pitch",
            name="08 — Steep roof (1:5)",
            description="Steeper pitch single gable for 2D ridge height check",
            width_expr="24",
            length_m=48.0,
            frame_type=FrameType.SINGLE_GABLE,
            roof_pitch_1_to_n=5.0,
            eave_height_m=6.0,
            ffl_level_m=0.0,
            sidewall_expr="8@6",
            expect_min_ridges=1,
            expect_min_columns=2,
        ),
        BuildingTemplate(
            id="sg_ffl_blockwall",
            name="09 — FFL + blockwall",
            description="Raised FFL and masonry blockwall annotation",
            width_expr="18",
            length_m=54.0,
            frame_type=FrameType.SINGLE_GABLE,
            roof_pitch_1_to_n=10.0,
            eave_height_m=8.0,
            ffl_level_m=0.45,
            sidewall_expr="9@6",
            blockwall_height_m=3.0,
            expect_min_ridges=1,
            expect_min_columns=2,
        ),
        BuildingTemplate(
            id="sg_with_mezzanine",
            name="10 — Single gable + mezzanine",
            description="Office mezzanine strip on left side",
            width_expr="25",
            length_m=60.0,
            frame_type=FrameType.SINGLE_GABLE,
            roof_pitch_1_to_n=10.0,
            eave_height_m=10.0,
            ffl_level_m=0.0,
            sidewall_expr="10@6",
            mezzanine_enabled=True,
            mezz_width_m=8.0,
            mezz_height_m=4.0,
            mezz_col_spacing_m=6.0,
            expect_min_ridges=1,
            expect_min_columns=2,
            expect_has_mezzanine=True,
        ),
        BuildingTemplate(
            id="ms_with_crane",
            name="11 — Multi-span + EOT crane",
            description="Twin span with crane runway annotation",
            width_expr="2@25",
            length_m=75.0,
            frame_type=FrameType.MULTI_SPAN,
            roof_pitch_1_to_n=10.0,
            eave_height_m=12.0,
            ffl_level_m=0.0,
            sidewall_expr="10@7.5",
            crane_enabled=True,
            crane_name="Crane 1",
            crane_capacity_kn=245.0,
            crane_runway_height_m=9.0,
            expect_min_ridges=1,
            expect_min_columns=3,
            expect_has_crane=True,
        ),
        BuildingTemplate(
            id="full_featured",
            name="12 — Full featured (mezz + crane)",
            description="Multi-gable with mezzanine, crane, FFL, blockwall",
            width_expr="2@30",
            length_m=120.0,
            frame_type=FrameType.MULTI_GABLE,
            roof_pitch_1_to_n=10.0,
            eave_height_m=14.0,
            ffl_level_m=0.3,
            sidewall_expr="16@7.5",
            blockwall_height_m=3.0,
            dead_kn_m2=0.35,
            collateral_kn_m2=0.2,
            live_kn_m2=0.75,
            mezzanine_enabled=True,
            mezz_width_m=10.0,
            mezz_height_m=4.5,
            mezz_col_spacing_m=7.5,
            crane_enabled=True,
            crane_name="Crane A",
            crane_capacity_kn=200.0,
            crane_runway_height_m=10.0,
            expect_min_ridges=2,
            expect_min_columns=3,
            expect_has_mezzanine=True,
            expect_has_crane=True,
        ),
    )


TEMPLATES: Tuple[BuildingTemplate, ...] = _templates()


def list_templates() -> List[BuildingTemplate]:
    return list(TEMPLATES)


def get_template(template_id: str) -> BuildingTemplate:
    for tpl in TEMPLATES:
        if tpl.id == template_id:
            return tpl
    raise KeyError(f"Unknown template id: {template_id}")


def templates_by_id() -> Dict[str, BuildingTemplate]:
    return {t.id: t for t in TEMPLATES}
