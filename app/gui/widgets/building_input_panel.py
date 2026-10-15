"""Building input panel — geometry, loads, optional mezzanine/crane."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.models import StructuralModel, SupportType
from app.core.pipeline import PipelineOptions, run_pipeline
from app.core.preferences import AppPreferences, DESIGN_CODES, get_preferences
from app.database.materials import list_materials
from app.database.sections import SectionDatabase
from app.geometry.peb_frame import (
    BuildingGeometryInput,
    CraneInput,
    DeflectionLimits,
    FrameType,
    MezzanineInput,
    RoofLoadsInput,
    WindSeismicInput,
    coerce_frame_type,
    frame_allows_interior_columns,
    pitch_n_from_slope_x10,
    recommend_ext_col_base,
    resolve_width_spans,
    slope_x10_from_pitch_n,
    validate_building_input,
)
from app.geometry.spacing import parse_spacing_list, spacing_total
from app.geometry.validation import ValidationError
from app.gui.widgets.deflection_limits_dialog import DeflectionLimitsDialog
from app.gui.widgets.extensions_section import CraneSection, ExtensionsSection
from app.gui.widgets.mezzanine_section import MezzanineSection
from app.templates.catalog import BuildingTemplate, get_template, list_templates


class BuildingInputPanel(QWidget):
    """Left-side project inputs with Generate action."""

    model_generated = Signal(object, str)  # StructuralModel, staad_text
    model_cleared = Signal()
    preview_requested = Signal(object)  # BuildingGeometryInput or metadata-like
    inputs_pending = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._set_defaults()
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(350)
        self._live_timer.timeout.connect(lambda: self._on_generate(automatic=True))
        for widget in self.findChildren(QLineEdit):
            if widget not in (self.sidewall_edit, self.pitch_edit):
                widget.textChanged.connect(self._schedule_update)
        for widget in self.findChildren(QComboBox):
            if widget is not self.template_combo:
                widget.currentIndexChanged.connect(self._schedule_update)
        for widget in self.findChildren(QCheckBox) + self.findChildren(QRadioButton):
            widget.toggled.connect(self._schedule_update)
        for section in (self.mezz_section, self.extensions_section, self.crane_section):
            section.changed.connect(self._schedule_update)
        self._schedule_update()

    def _schedule_update(self, *_args) -> None:
        if not hasattr(self, "_live_timer"):
            return
        self.status.setText("Updating model...")
        self.inputs_pending.emit()
        self._live_timer.start()

    def flush_update(self) -> bool:
        """Ensure copy/export cannot use an older revision of the inputs."""
        if self._live_timer.isActive():
            return self._on_generate(automatic=True)
        return getattr(self, "_last_valid", False)

    def _build_ui(self) -> None:
        self.setObjectName("inputPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("inputHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 20, 20, 16)
        header_layout.setSpacing(7)
        caption = QLabel("PROJECT PARAMETERS")
        caption.setObjectName("eyebrow")
        header_layout.addWidget(caption)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("inputBody")
        body.setMinimumWidth(0)
        root = QVBoxLayout(body)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Building Inputs")
        title.setObjectName("panelTitle")
        self.panel_title = title
        header_layout.addWidget(title)
        self.section_hint = QLabel(
            "Width: 40 or 2@20. Int. Col. Spacing: 0 or 20+20. "
            "Bay spacing expands along the length. Roof Slope is X in X:10."
        )
        self.section_hint.setWordWrap(True)
        self.section_hint.setObjectName("panelHint")
        header_layout.addWidget(self.section_hint)
        outer.addWidget(header)

        # --- Templates ---
        tpl_box = QGroupBox("TEMPLATES")
        tpl_box.setCheckable(True)
        tpl_box.setChecked(True)
        tpl_l = QVBoxLayout(tpl_box)
        self.template_combo = QComboBox()
        self.template_combo.addItem("— Select a template —", None)
        for tpl in list_templates():
            self.template_combo.addItem(tpl.name, tpl.id)
        tpl_btn_row = QHBoxLayout()
        self.load_template_btn = QPushButton("Load Template")
        self.load_template_btn.clicked.connect(self._on_load_template)
        self.load_generate_btn = QPushButton("Load + Generate")
        self.load_generate_btn.setObjectName("primaryButton")
        self.load_generate_btn.clicked.connect(self._on_load_and_generate)
        tpl_btn_row.addWidget(self.load_template_btn)
        tpl_btn_row.addWidget(self.load_generate_btn)
        tpl_l.addWidget(self.template_combo)
        self.template_desc = QLabel("Choose a preset to fill inputs and test 2D cases.")
        self.template_desc.setWordWrap(True)
        self.template_desc.setObjectName("panelHint")
        tpl_l.addWidget(self.template_desc)
        tpl_l.addLayout(tpl_btn_row)
        root.addWidget(tpl_box)
        self.template_combo.currentIndexChanged.connect(self._on_template_combo_changed)

        # --- Geometry (matches Geometry options layout) ---
        geo = QGroupBox("GEOMETRY")
        geo.setCheckable(True)
        geo.setChecked(True)
        gf = QFormLayout(geo)
        self.width_edit = QLineEdit()
        self.width_edit.setToolTip("Building width centre-to-centre (m). Multi-span may use 2@20.")
        self.length_edit = self._number_field()
        self.length_edit.setToolTip("Building length centre-to-centre (m).")

        self.frame_type = QComboBox()
        self.frame_type.addItem("Clear Span", FrameType.CLEAR_SPAN)
        self.frame_type.addItem("Multi-Span", FrameType.MULTI_SPAN)
        self.frame_type.addItem("Multi-Gable", FrameType.MULTI_GABLE)
        self.frame_type.addItem("Mono-Slope", FrameType.MONO_SLOPE)
        self.frame_type.addItem("Asym Gable", FrameType.ASYM_GABLE)
        self.frame_type.setToolTip(
            "Clear Span: no interior columns\n"
            "Multi-Span: interior columns, taken from the width string\n"
            "Multi-Gable: repeated gables\n"
            "Mono-Slope: one slope across the width\n"
            "Asym Gable: two slopes about the ridge\n"
            "Interior columns are only accepted on the types that can carry them."
        )

        self.int_col_edit = QLineEdit()
        self.int_col_edit.setToolTip(
            "Where the interior columns go, as a spacing string: "
            "2@30+3@40 means two bays of 30 m then three of 40 m. "
            "0 = none. Multi-Span fills this from the building width and goes "
            "read-only. Clear Span, Asym Gable and single-span Mono-Slope take "
            "no interior columns — a spacing typed here is refused, not ignored."
        )

        self.eave_edit = self._number_field()
        self.blockwall_edit = self._number_field(allow_zero=True)
        self.slope_x10_edit = self._number_field()
        self.slope_x10_edit.setToolTip("Roof slope as X in X:10 (1.0 → 1:10 pitch).")
        self.bay_edit = QLineEdit()
        self.bay_edit.setToolTip("Equal spacing, e.g. 6; or complete bay list, e.g. 6+8+6 or 2@6+8.")

        ridge_row = QWidget()
        ridge_l = QHBoxLayout(ridge_row)
        ridge_l.setContentsMargins(0, 0, 0, 0)
        self.ridge_dist_edit = self._number_field()
        self.ridge_auto_cb = QCheckBox("auto")
        self.ridge_auto_cb.setChecked(True)
        self.ridge_auto_cb.setToolTip("When checked, ridge is at mid-width.")
        ridge_l.addWidget(self.ridge_dist_edit, 1)
        ridge_l.addWidget(self.ridge_auto_cb)

        self.purlin_edit = self._number_field()
        self.girt_edit = self._number_field()

        self.ext_base_combo = QComboBox()
        self.ext_base_combo.addItem("Auto", "auto")
        self.ext_base_combo.addItem("Pinned", SupportType.PINNED)
        self.ext_base_combo.addItem("Fixed", SupportType.FIXED)
        self.ext_base_combo.setToolTip(
            "Exterior (main frame) column base.\n"
            "Auto: use the recommended condition (derived from eave height + proportions).\n"
            "Pinned: no moment at base.\n"
            "Fixed: moment-resisting base.\n"
            "Auto suggests fixed bases for heavy cranes; an explicit selection is retained."
        )
        self.ext_base_hint = QLabel("")
        self.ext_base_hint.setObjectName("panelHint")
        self.ext_base_hint.setWordWrap(True)

        # Keep FFL available but secondary
        self.ffl_edit = self._number_field(allow_zero=True)
        # Legacy alias used by older helpers / clear path
        self.sidewall_edit = QLineEdit()
        self.sidewall_edit.hide()
        self.pitch_edit = QLineEdit()
        self.pitch_edit.hide()

        gf.addRow("Building Width (m, c/c)", self.width_edit)
        gf.addRow("Building Length (m, c/c)", self.length_edit)
        gf.addRow("Frame Type", self.frame_type)
        gf.addRow("Int. Col. Spacing (m)", self.int_col_edit)
        gf.addRow("Eave Height (m)", self.eave_edit)
        gf.addRow("Blockwall Height (m)", self.blockwall_edit)
        gf.addRow("Roof Slope (X:10)", self.slope_x10_edit)
        gf.addRow("Bay Spacing (m)", self.bay_edit)
        gf.addRow("Ridge Distance (m)", ridge_row)
        gf.addRow("Purlin Spacing (m)", self.purlin_edit)
        gf.addRow("Girt Spacing (m)", self.girt_edit)
        gf.addRow("Ext. Col. Base", self.ext_base_combo)
        gf.addRow(self.ext_base_hint)
        gf.addRow("FFL level (m)", self.ffl_edit)
        root.addWidget(geo)

        self.frame_type.currentIndexChanged.connect(self._on_frame_type_changed)
        self.width_edit.textChanged.connect(self._on_geometry_field_changed)
        self.int_col_edit.textChanged.connect(self._on_geometry_field_changed)
        self.eave_edit.textChanged.connect(self._on_geometry_field_changed)
        self.bay_edit.textChanged.connect(self._on_geometry_field_changed)
        self.length_edit.textChanged.connect(self._on_geometry_field_changed)
        self.slope_x10_edit.textChanged.connect(self._on_geometry_field_changed)
        self.ridge_dist_edit.textChanged.connect(self._on_geometry_field_changed)
        self.ridge_auto_cb.toggled.connect(self._on_ridge_auto_toggled)
        self.ext_base_combo.currentIndexChanged.connect(self._update_ext_base_hint)

        # --- Structural model (Milestone 2) ---
        struct = QGroupBox("STRUCTURAL MODEL")
        struct.setCheckable(True)
        struct.setChecked(True)
        sf = QFormLayout(struct)
        self.material_combo = QComboBox()
        for mat in list_materials():
            self.material_combo.addItem(f"Steel grade {mat.name} (fy {mat.fy_mpa:g} MPa)", mat.name)
        self.column_section_combo = QComboBox()
        self.rafter_section_combo = QComboBox()
        self.refresh_sections()
        # Keep support_combo as mirror of Ext. Col. Base for generate path
        self.support_combo = self.ext_base_combo
        self.design_code_label = QLabel("—")
        self.run_analysis_cb = QCheckBox("Run analysis (2D frame solver)")
        self.run_analysis_cb.setChecked(True)
        self.run_design_cb = QCheckBox("Run design checks (from Preferences code)")
        self.run_design_cb.setChecked(True)
        sf.addRow("Steel grade", self.material_combo)
        sf.addRow("Column section", self.column_section_combo)
        sf.addRow("Rafter section", self.rafter_section_combo)
        sf.addRow("Design code", self.design_code_label)
        sf.addRow(self.run_analysis_cb)
        sf.addRow(self.run_design_cb)
        self.export_mode = QComboBox()
        self.export_mode.addItem("2D frame - largest tributary width", True)
        self.export_mode.addItem("Full 3D model - stability review required", False)
        self.export_mode.setToolTip("2D exports a STAAD PLANE frame with its actual tributary loads. 3D includes longitudinal members; the built-in solver only checks transverse frames.")
        sf.addRow("STAAD export", self.export_mode)
        self.staad_analysis_combo = QComboBox()
        self.staad_analysis_combo.addItem("First-order linear", "linear")
        self.staad_analysis_combo.addItem("P-Delta + repeat loads (20 iterations)", "pdelta")
        self.staad_analysis_combo.setToolTip("Controls STAAD export. P-Delta includes small-delta effects and uses simultaneous repeat loads. App calculations remain first-order. Check STAAD convergence and displacements after running.")
        sf.addRow("STAAD analysis", self.staad_analysis_combo)
        self.secondary_connection_combo = QComboBox()
        self.secondary_connection_combo.addItem("Pinned purlin/girt ends", "pinned")
        self.secondary_connection_combo.addItem("Rigid purlin/girt ends", "rigid")
        self.secondary_connection_combo.setToolTip(
            "Pinned releases local MY and MZ at both ends of longitudinal purlins and girts in the STAAD SPACE export. Primary portal joints remain rigid."
        )
        sf.addRow("Secondary connections", self.secondary_connection_combo)
        root.addWidget(struct)

        derived = QGroupBox("DERIVED")
        derived.setCheckable(True)
        derived.setChecked(True)
        df = QFormLayout(derived)
        self.total_width_label = QLabel("—")
        self.ridge_label = QLabel("—")
        self.frames_label = QLabel("—")
        df.addRow("Total width", self.total_width_label)
        df.addRow("Max ridge height", self.ridge_label)
        df.addRow("Frames", self.frames_label)
        root.addWidget(derived)

        # --- Wind / Seismic PARAMETERS (IS ↔ ASCE panels) ---
        wind = QGroupBox("WIND / SEISMIC PARAMETERS")
        wind.setCheckable(True)
        wind.setChecked(True)
        wl = QVBoxLayout(wind)
        wl.setSpacing(10)

        top_row = QHBoxLayout()
        self.code_is = QRadioButton("IS Code")
        self.code_asce = QRadioButton("ASCE 7")
        self.code_is.setChecked(True)
        self._code_family_group = QButtonGroup(self)
        self._code_family_group.addButton(self.code_is, 0)
        self._code_family_group.addButton(self.code_asce, 1)
        top_row.addWidget(self.code_is)
        top_row.addWidget(self.code_asce)
        top_row.addSpacing(16)

        self.method_dm = QCheckBox("DM")
        self.method_adm = QCheckBox("ADM")
        self.method_sm = QCheckBox("SM")
        self.method_others = QCheckBox("Others")
        self.method_others.setChecked(True)
        self._asce_method_widgets = (
            self.method_dm,
            self.method_adm,
            self.method_sm,
            self.method_others,
        )
        for cb in self._asce_method_widgets:
            top_row.addWidget(cb)
        top_row.addStretch(1)
        wl.addLayout(top_row)

        self.method_dm.toggled.connect(self._on_ws_method_toggled)
        self.method_adm.toggled.connect(self._on_ws_method_toggled)
        self.method_sm.toggled.connect(self._on_ws_method_toggled)
        self.method_others.toggled.connect(self._on_ws_method_toggled)
        self.code_is.toggled.connect(self._on_ws_code_family_changed)
        self.code_asce.toggled.connect(self._on_ws_code_family_changed)

        def _field_label(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setObjectName("sectionCaption")
            return lab

        # Shared wind speed (used by both panels)
        self.wind_speed = QLineEdit("47")
        self.wind_speed.setToolTip("Basic wind speed Vb (m/s).")

        # ----- IS Code panel -----
        self._ws_is_panel = QWidget()
        is_grid = QGridLayout(self._ws_is_panel)
        is_grid.setContentsMargins(0, 0, 0, 0)
        is_grid.setHorizontalSpacing(12)
        is_grid.setVerticalSpacing(6)

        self.is_condition = QComboBox()
        for code in ("Enclosed", "Partially Enclosed", "Open"):
            self.is_condition.addItem(code, code)

        self.terrain_category = QComboBox()
        for code in ("1", "2", "3", "4"):
            self.terrain_category.addItem(code, code)
        self.terrain_category.setToolTip("IS 875 terrain category.")

        self.k1_edit = self._number_field(allow_zero=True)
        self.k1_edit.setText("1.00")
        self.k1_edit.setToolTip("k1 — risk coefficient.")
        self.k3_edit = self._number_field(allow_zero=True)
        self.k3_edit.setText("1.00")
        self.k3_edit.setToolTip("k3 — topography factor.")
        self.k4_edit = self._number_field(allow_zero=True)
        self.k4_edit.setText("1.0")
        self.k4_edit.setToolTip("k4 — importance factor.")

        self.is_zone = QComboBox()
        for code in ("I", "II", "III", "IV", "V"):
            self.is_zone.addItem(code, code)
        self.is_zone.setCurrentIndex(2)  # III
        self.is_zone.setToolTip("IS 1893 seismic zone.")

        self.soil_type = QComboBox()
        for code in ("I", "II", "III"):
            self.soil_type.addItem(code, code)
        self.soil_type.setCurrentIndex(1)  # II
        self.soil_type.setToolTip("IS 1893 soil type.")

        self.response_r_edit = self._number_field(allow_zero=True)
        self.response_r_edit.setText("5.00")
        self.response_r_edit.setToolTip("Response reduction factor R.")

        vb_lab = _field_label("Basic Wind Speed (m/s)")
        vb_lab.setToolTip("Vb reference — basic wind speed.")
        is_grid.addWidget(vb_lab, 0, 0)
        is_grid.addWidget(_field_label("Building Condition"), 0, 1)
        is_grid.addWidget(_field_label("Terrain Category"), 0, 2)
        is_grid.addWidget(self.wind_speed, 1, 0)
        is_grid.addWidget(self.is_condition, 1, 1)
        is_grid.addWidget(self.terrain_category, 1, 2)

        is_grid.addWidget(_field_label("k1 — Risk"), 2, 0)
        is_grid.addWidget(_field_label("k3 — Topography"), 2, 1)
        is_grid.addWidget(_field_label("k4 — Importance"), 2, 2)
        is_grid.addWidget(self.k1_edit, 3, 0)
        is_grid.addWidget(self.k3_edit, 3, 1)
        is_grid.addWidget(self.k4_edit, 3, 2)

        is_grid.addWidget(_field_label("Seismic Zone"), 4, 0)
        is_grid.addWidget(_field_label("Soil Type"), 4, 1)
        is_grid.addWidget(_field_label("Response Factor (R)"), 4, 2)
        is_grid.addWidget(self.is_zone, 5, 0)
        is_grid.addWidget(self.soil_type, 5, 1)
        is_grid.addWidget(self.response_r_edit, 5, 2)
        for c in range(3):
            is_grid.setColumnStretch(c, 1)
        wl.addWidget(self._ws_is_panel)
        manual = QFormLayout()
        self.k2_edit = self._number_field()
        self.k2_edit.setText("1.0")
        self.k2_edit.setToolTip("Engineer-specified k2 from the applicable terrain/height table; terrain selection does not look up this value.")
        self.uplift_edit = self._number_field(allow_zero=True)
        self.uplift_edit.setText("0")
        self.seismic_ah_edit = self._number_field(allow_zero=True)
        self.seismic_ah_edit.setText("0")
        manual.addRow("Wind k2 (user value)", self.k2_edit)
        manual.addRow("Net roof uplift (kN/m²)", self.uplift_edit)
        manual.addRow("Seismic Ah (0 = off)", self.seismic_ah_edit)
        manual_note = QLabel("Uplift is a separate uniform case. Ah creates ±X equivalent static cases from dead weight; enter an independently calculated coefficient. Zone/soil/R do not calculate Ah.")
        manual_note.setWordWrap(True)
        manual.addRow(manual_note)
        wl.addLayout(manual)

        # ----- ASCE 7 panel -----
        self._ws_asce_panel = QWidget()
        asce_grid = QGridLayout(self._ws_asce_panel)
        asce_grid.setContentsMargins(0, 0, 0, 0)
        asce_grid.setHorizontalSpacing(12)
        asce_grid.setVerticalSpacing(6)

        self.asce_wind_speed = QLineEdit("47")
        self.asce_wind_speed.setToolTip("Basic wind speed (m/s).")

        self.exposure = QComboBox()
        for code in ("A", "B", "C", "D"):
            self.exposure.addItem(code, code)
        self.exposure.setCurrentIndex(1)

        self.site = QComboBox()
        for code in ("A", "B", "C", "D", "E"):
            self.site.addItem(code, code)
        self.site.setCurrentIndex(1)

        self.condition = QComboBox()  # ASCE building condition
        for code in ("Enclosed", "Partially Enclosed", "Open"):
            self.condition.addItem(code, code)

        self.zone = QComboBox()  # ASCE seismic zone
        for code in ("—", "1", "2", "2A", "3", "4", "5"):
            self.zone.addItem(code, code)
        self._set_combo_data(self.zone, "2A")

        self.ss_edit = self._number_field(allow_zero=True)
        self.ss_edit.setText("0.365")
        self.s1_edit = self._number_field(allow_zero=True)
        self.s1_edit.setText("0.130")

        asce_grid.addWidget(_field_label("Wind Speed (m/s)"), 0, 0)
        asce_grid.addWidget(_field_label("Exposure Category"), 0, 1)
        asce_grid.addWidget(_field_label("Site Class"), 0, 2)
        asce_grid.addWidget(self.asce_wind_speed, 1, 0)
        asce_grid.addWidget(self.exposure, 1, 1)
        asce_grid.addWidget(self.site, 1, 2)

        asce_grid.addWidget(_field_label("Building Condition"), 2, 0)
        asce_grid.addWidget(_field_label("Seismic Zone"), 2, 1)
        asce_grid.addWidget(_field_label("Ss (g)"), 2, 2)
        asce_grid.addWidget(_field_label("S1 (g)"), 2, 3)
        asce_grid.addWidget(self.condition, 3, 0)
        asce_grid.addWidget(self.zone, 3, 1)
        asce_grid.addWidget(self.ss_edit, 3, 2)
        asce_grid.addWidget(self.s1_edit, 3, 3)
        for c in range(4):
            asce_grid.setColumnStretch(c, 1)
        wl.addWidget(self._ws_asce_panel)

        root.addWidget(wind)

        # --- Code / Load combination ---
        code_box = QGroupBox("CODE / LOAD COMBINATION")
        code_box.setCheckable(True)
        code_box.setChecked(True)
        code_l = QVBoxLayout(code_box)
        code_caption = QLabel("Load Combination Type")
        code_caption.setObjectName("sectionCaption")
        code_l.addWidget(code_caption)

        code_row = QHBoxLayout()
        self.combo_label = QComboBox()
        for code in DESIGN_CODES:
            self.combo_label.addItem(code, code)
        self.combo_label.setToolTip("Design / load combination code used for analysis & design.")
        self.combo_label.currentIndexChanged.connect(self._on_load_combo_changed)
        code_row.addWidget(self.combo_label, stretch=1)

        self.deflection_btn = QPushButton("Deflection Limits")
        self.deflection_btn.setToolTip(
            "Edit serviceability limits: rafter Span/N and column sway H/N."
        )
        self.deflection_btn.clicked.connect(self._open_deflection_limits)
        code_row.addWidget(self.deflection_btn)
        code_l.addLayout(code_row)

        self.deflection_summary = QLabel("")
        self.deflection_summary.setObjectName("panelHint")
        self.deflection_summary.setWordWrap(True)
        code_l.addWidget(self.deflection_summary)

        self._deflection_limits = DeflectionLimits()
        self._update_deflection_summary()
        root.addWidget(code_box)

        self._on_ws_code_family_changed()

        # --- Roof loads ---
        roof = QGroupBox("ROOF LOADS")
        roof.setCheckable(True)
        roof.setChecked(True)
        rf = QFormLayout(roof)
        self.dead_edit = self._number_field(allow_zero=True)
        self.coll_edit = self._number_field(allow_zero=True)
        self.live_edit = self._number_field(allow_zero=True)
        rf.addRow("Dead (kN/m²)", self.dead_edit)
        rf.addRow("Collateral (kN/m²)", self.coll_edit)
        rf.addRow("Live (kN/m²)", self.live_edit)
        note = QLabel(
            "Loads per horizontal plan area. End frames receive half a bay; interior frames receive half of each adjacent bay."
        )
        note.setWordWrap(True)
        note.setObjectName("panelHint")
        rf.addRow(note)
        root.addWidget(roof)

        # --- Mezzanine (multi-level) ---
        mezz = QGroupBox("MEZZANINE")
        mezz.setCheckable(True)
        mezz.setChecked(True)
        ml = QVBoxLayout(mezz)
        ml.setContentsMargins(8, 8, 8, 8)
        self.mezz_section = MezzanineSection()
        self.mezz_section.flat_roof_toggled.connect(self._on_mezz_flat_roof)
        ml.addWidget(self.mezz_section)
        root.addWidget(mezz)

        # --- Extensions (Roof Monitor) ---
        ext_box = QGroupBox("EXTENSIONS")
        ext_box.setCheckable(True)
        ext_box.setChecked(True)
        el = QVBoxLayout(ext_box)
        el.setContentsMargins(8, 8, 8, 8)
        self.extensions_section = ExtensionsSection()
        el.addWidget(self.extensions_section)
        root.addWidget(ext_box)

        # --- EOT Crane ---
        crane = QGroupBox("EOT CRANE DATA")
        crane.setCheckable(True)
        crane.setChecked(True)
        cl = QVBoxLayout(crane)
        cl.setContentsMargins(8, 8, 8, 8)
        self.crane_section = CraneSection()
        self.crane_section.changed.connect(self._update_ext_base_hint)
        self.crane_section.changed.connect(self._update_crane_clearance)
        self.mezz_section.changed.connect(self._update_crane_clearance)
        cl.addWidget(self.crane_section)
        root.addWidget(crane)

        footer = QWidget()
        footer.setObjectName("actionFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)
        footer_layout.setSpacing(8)
        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("Update now (auto update on)")
        self.generate_btn.setMinimumHeight(24)
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self.generate_btn, 1)
        btn_row.addWidget(self.clear_btn)
        footer_layout.addLayout(btn_row)

        self.status = QLabel("Ready")
        self.status.setObjectName("panelHint")
        self.status.setWordWrap(True)
        footer_layout.addWidget(self.status)
        root.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addWidget(footer)
        self._scroll = scroll
        self._body = body

        # Sidebar → section mapping (full toggle)
        self._sections = {
            "templates": tpl_box,
            "geometry": geo,
            "structural": struct,
            "derived": derived,
            "wind": wind,
            "code": code_box,
            "roof": roof,
            "mezzanine": mezz,
            "extensions": ext_box,
            "crane": crane,
        }
        self._actions = (self.generate_btn, self.clear_btn, self.status)
        self._nav_mode = "Dashboard"
        # A common label column keeps every section aligned. Long option text
        # must not dictate the width of the entire input panel.
        for form in (gf, sf, df, rf):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(10)
            for row in range(form.rowCount()):
                label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if label_item and isinstance(label_item.widget(), QLabel):
                    label_item.widget().setFixedWidth(118)
                    label_item.widget().setWordWrap(True)
        for combo in self.findChildren(QComboBox):
            combo.setMinimumContentsLength(8)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Descriptive selections need the full card width to remain readable.
        for form in (sf,):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            for row in range(form.rowCount()):
                label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if label_item and isinstance(label_item.widget(), QLabel):
                    label_item.widget().setMinimumWidth(0)
                    label_item.widget().setMaximumWidth(16777215)
        section_titles = {
            "templates": "Templates", "geometry": "Geometry",
            "structural": "Structural model", "derived": "Derived dimensions",
            "wind": "Wind / seismic", "code": "Code / load combination",
            "roof": "Roof loads",
            "mezzanine": "Mezzanine",
            "extensions": "EXTENSIONS",
            "crane": "EOT CRANE DATA",
        }
        for key, box in self._sections.items():
            box.setTitle(section_titles[key])
        self.run_analysis_cb.setText("Run 2D frame analysis")
        self.run_design_cb.setText("Run design checks")
        self.run_design_cb.setToolTip("Run design checks using the code selected in Preferences.")
        # Checkbox on group title collapses content
        for box in self._sections.values():
            box.toggled.connect(lambda checked, b=box: self._on_group_toggled(b, checked))

        self.crane_section.changed.connect(self._update_ext_base_hint)
        self._on_frame_type_changed()
        self._on_ridge_auto_toggled(self.ridge_auto_cb.isChecked())
        self.show_nav_section("Dashboard")

    def _on_group_toggled(self, box: QGroupBox, checked: bool) -> None:
        """Collapse/expand group body when the section checkbox is clicked."""
        layout = box.layout()
        if layout is None:
            return
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.setVisible(checked)
            elif item and item.layout() is not None:
                self._set_layout_visible(item.layout(), checked)

    @staticmethod
    def _set_layout_visible(layout, visible: bool) -> None:
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.setVisible(visible)
            elif item and item.layout() is not None:
                BuildingInputPanel._set_layout_visible(item.layout(), visible)

    def show_nav_section(self, name: str) -> None:
        """Show full section set for a sidebar item (others hidden)."""
        name = (name or "Dashboard").strip()
        self._nav_mode = name
        self.panel_title.setText({"Dashboard": "Building inputs", "3D Model": "Model parameters"}.get(name, name + " inputs"))

        # Which groups belong to each nav destination
        map_groups = {
            "Dashboard": list(self._sections.keys()),
            "Geometry": ["templates", "geometry", "derived"],
            "Loads": ["wind", "code", "roof", "mezzanine", "extensions", "crane"],
            "Analysis": ["structural", "derived"],
            "Design": ["structural", "derived"],
            "3D Model": ["geometry", "derived"],
            "Settings": list(self._sections.keys()),
            "Reports": list(self._sections.keys()),
            "Optimization": list(self._sections.keys()),
        }
        hints = {
            "Dashboard": "All project inputs in one place. Expand or collapse sections to organize your workspace.",
            "Geometry": "Full geometry options — width, frame type, bay spacing, ridge, bases. Generate updates the 2D preview.",
            "Loads": "Wind / seismic, code, roof loads, mezzanine, extensions and crane.",
            "Analysis": "Structural model + analysis options. Generate runs the 2D frame solver when enabled.",
            "Design": "Structural model + design checks (IS 800 from Preferences).",
            "3D Model": "Geometry summary while viewing the 3D model.",
            "Settings": "All sections visible — open Preferences from the dialog.",
        }
        keys = map_groups.get(name, ["geometry", "derived"])
        self.section_hint.setText(hints.get(name, self.section_hint.text()))

        for key, box in self._sections.items():
            show = key in keys
            box.setVisible(show)
            if show:
                box.setChecked(True)
                self._on_group_toggled(box, True)

        # Always keep generate actions available except pure 3D glance
        for w in self._actions:
            w.setVisible(True)

        # Scroll to the first visible section
        for key in keys:
            box = self._sections.get(key)
            if box is not None and box.isVisible():
                self._scroll.ensureWidgetVisible(box, 0, 40)
                break

    def toggle_nav_section(self, name: str) -> None:
        """Toggle focused section: click same sidebar item again → show all."""
        if self._nav_mode == name and name != "Dashboard":
            self.show_nav_section("Dashboard")
        else:
            self.show_nav_section(name)

    def _set_combo_data(self, combo: QComboBox, value: object) -> None:
        """Select combo item by userData; fall back to matching text / editable."""
        target = "" if value is None else str(value)
        idx = combo.findData(target)
        if idx < 0:
            # Try matching leading code in display text
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is not None and str(data) == target:
                    idx = i
                    break
                text = combo.itemText(i)
                if text == target or text.startswith(target + " ") or text.startswith(target + "—"):
                    idx = i
                    break
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setEditText(target)

    def _combo_data_text(self, combo: QComboBox) -> str:
        data = combo.currentData()
        if data is not None and str(data).strip():
            return str(data)
        text = combo.currentText().strip()
        # Editable wind speed may show "47 m/s — common"
        if " " in text:
            first = text.split()[0]
            try:
                float(first)
                return first
            except ValueError:
                pass
        return text

    def _parse_wind_speed(self) -> float:
        edit = self.asce_wind_speed if self.code_asce.isChecked() else self.wind_speed
        text = edit.text().strip()
        if not text:
            raise ValidationError(["Wind speed is required."])
        try:
            return float(text)
        except ValueError as exc:
            raise ValidationError(["Wind speed must be a number (m/s)."]) from exc

    def _on_ws_method_toggled(self, checked: bool) -> None:
        """Keep method flags coherent: Others vs DM/ADM/SM."""
        sender = self.sender()
        if sender is None or not checked:
            if not any(cb.isChecked() for cb in self._asce_method_widgets):
                self.method_others.blockSignals(True)
                self.method_others.setChecked(True)
                self.method_others.blockSignals(False)
            return
        if sender is self.method_others:
            for cb in (self.method_dm, self.method_adm, self.method_sm):
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        else:
            self.method_others.blockSignals(True)
            self.method_others.setChecked(False)
            self.method_others.blockSignals(False)

    def _on_ws_code_family_changed(self, *_args) -> None:
        asce = self.code_asce.isChecked()
        self._ws_is_panel.setVisible(not asce)
        self._ws_asce_panel.setVisible(asce)
        for cb in self._asce_method_widgets:
            cb.setVisible(asce)

        # Keep wind speeds in sync when switching
        if asce:
            if self.wind_speed.text().strip():
                self.asce_wind_speed.setText(self.wind_speed.text().strip())
        else:
            if self.asce_wind_speed.text().strip():
                self.wind_speed.setText(self.asce_wind_speed.text().strip())

        prefs = get_preferences()
        if asce:
            pick = next(
                (c for c in DESIGN_CODES if c.upper().startswith("ASCE")),
                prefs.design_code,
            )
        else:
            pick = next(
                (c for c in DESIGN_CODES if c.upper().startswith("IS800")),
                prefs.design_code,
            )
        self._set_combo_data(self.combo_label, pick)

    def _ws_code_family(self) -> str:
        return "ASCE7" if self.code_asce.isChecked() else "IS"

    def _on_load_combo_changed(self, *_args) -> None:
        code = self._combo_data_text(self.combo_label)
        self.design_code_label.setText(code or "—")
        if code.upper().startswith("ASCE") and not self.code_asce.isChecked():
            self.code_asce.setChecked(True)
        elif code.upper().startswith("IS800") and not self.code_is.isChecked():
            self.code_is.setChecked(True)

    def _update_deflection_summary(self) -> None:
        d = self._deflection_limits
        self.deflection_summary.setText(
            f"Rafter Span/{d.rafter_total_load_L_over:g} (DL+LL), "
            f"Span/{d.rafter_live_load_L_over:g} (LL)  ·  "
            f"Sway H/{d.column_wind_crane_H_over:g} (W/Crane), "
            f"H/{d.column_seismic_H_over:g} (Seismic)"
        )

    def _open_deflection_limits(self) -> None:
        dialog = DeflectionLimitsDialog(self, limits=self._deflection_limits)
        dialog.limits_saved.connect(self._on_deflection_limits_saved)
        dialog.exec()

    def _on_deflection_limits_saved(self, limits: DeflectionLimits) -> None:
        self._deflection_limits = limits
        self._update_deflection_summary()
        self._schedule_update()

    def _on_mezz_flat_roof(self, flat: bool) -> None:
        """Grey out roof/geometry fields that don't apply in mezz-only flat mode."""
        for w in (
            self.slope_x10_edit,
            self.purlin_edit,
            self.girt_edit,
            self.eave_edit,
            self.frame_type,
            self.dead_edit,
            self.coll_edit,
            self.live_edit,
            self.ridge_dist_edit,
            self.ridge_auto_cb,
            self.int_col_edit,
        ):
            w.setEnabled(not flat)
        self.extensions_section.setEnabled(not flat)
        self._update_crane_clearance()

    def _update_crane_clearance(self) -> None:
        mezz_h = 0.0
        try:
            mz = self.mezz_section.read_input()
            levels = mz.resolved_levels()
            if levels:
                mezz_h = max(lv.height_m for lv in levels)
        except Exception:
            mezz_h = 0.0
        self.crane_section.update_clearance_warning(mezz_height_m=mezz_h)

    def _number_field(self, allow_zero: bool = False) -> QLineEdit:
        edit = QLineEdit()
        bottom = 0.0 if allow_zero else 0.0001
        validator = QDoubleValidator(bottom, 1_000_000.0, 6, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        return edit

    def _set_defaults(self) -> None:
        prefs = get_preferences()
        self.apply_preferences(prefs, reset_geometry=True)

    def refresh_sections(self, *, prefer_column: str = "", prefer_rafter: str = "") -> None:
        """Reload section combos from the SQLite section database."""
        col_cur = prefer_column or str(self.column_section_combo.currentData() or "")
        raf_cur = prefer_rafter or str(self.rafter_section_combo.currentData() or "")
        self.column_section_combo.clear()
        self.rafter_section_combo.clear()
        try:
            sections = SectionDatabase().list_sections()
        except Exception:
            sections = []
        for sec in sections:
            self.column_section_combo.addItem(sec.name, sec.name)
            self.rafter_section_combo.addItem(sec.name, sec.name)
        for combo, name in (
            (self.column_section_combo, col_cur or "ISMB 400"),
            (self.rafter_section_combo, raf_cur or "ISMB 350"),
        ):
            idx = combo.findData(name)
            if idx < 0 and combo.count():
                idx = 0
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def apply_preferences(
        self, prefs: AppPreferences, *, reset_geometry: bool = False
    ) -> None:
        """Apply preference defaults to form fields.

        When reset_geometry is True (Clear / New Project), geometry defaults
        are also reset. Otherwise only preference-driven fields are updated.
        """
        if reset_geometry:
            self._deflection_limits = DeflectionLimits()
            self._update_deflection_summary()
            self.width_edit.setText("40")
            self.length_edit.setText("60")
            self.frame_type.setCurrentIndex(0)
            self.int_col_edit.setText("0")
            self.slope_x10_edit.setText("1.0")
            self.eave_edit.setText("6.5")
            self.ffl_edit.setText("0")
            self.bay_edit.setText("7.5")
            self.sidewall_edit.setText("7.5")
            self.blockwall_edit.setText("3")
            self.ridge_auto_cb.setChecked(True)
            self.ridge_dist_edit.setText("20")
            self.wind_speed.setText("47")
            self.asce_wind_speed.setText("47")
            self._set_combo_data(self.is_condition, "Enclosed")
            self._set_combo_data(self.condition, "Enclosed")
            self._set_combo_data(self.terrain_category, "1")
            self._set_combo_data(self.is_zone, "III")
            self._set_combo_data(self.soil_type, "II")
            self.k1_edit.setText("1.00")
            self.k3_edit.setText("1.00")
            self.k4_edit.setText("1.0")
            self.response_r_edit.setText("5.00")
            self.k2_edit.setText("1.0")
            self.uplift_edit.setText("0")
            self.seismic_ah_edit.setText("0")
            self._set_combo_data(self.exposure, "B")
            self._set_combo_data(self.zone, "2A")
            self._set_combo_data(self.site, "B")
            self.code_is.setChecked(True)
            self.method_dm.setChecked(False)
            self.method_adm.setChecked(False)
            self.method_sm.setChecked(False)
            self.method_others.setChecked(True)
            self.ss_edit.setText("0.365")
            self.s1_edit.setText("0.130")
            self.live_edit.setText("0.75")
            self.mezz_section.clear_mezzanine()
            self.extensions_section.clear()
            self.crane_section.clear_crane()
            idx_m = self.material_combo.findData("E350")
            if idx_m >= 0:
                self.material_combo.setCurrentIndex(idx_m)
            idx_c = self.column_section_combo.findData("ISMB 400")
            if idx_c >= 0:
                self.column_section_combo.setCurrentIndex(idx_c)
            idx_r = self.rafter_section_combo.findData("ISMB 350")
            if idx_r >= 0:
                self.rafter_section_combo.setCurrentIndex(idx_r)
            self.run_analysis_cb.setChecked(True)
            self.run_design_cb.setChecked(True)
            self.ext_base_combo.setCurrentIndex(0)  # Auto
            self.secondary_connection_combo.setCurrentIndex(0)
            self.staad_analysis_combo.setCurrentIndex(0)

        self.dead_edit.setText(str(prefs.roof_dead_kn_m2))
        self.coll_edit.setText(str(prefs.roof_collateral_kn_m2))
        self.purlin_edit.setText(str(prefs.purlin_spacing_m))
        self.girt_edit.setText(str(prefs.girt_spacing_m))
        self._set_combo_data(self.combo_label, prefs.design_code)
        self.design_code_label.setText(prefs.design_code)
        # Prefer IS/ASCE radio from design code when resetting family is not forced
        if prefs.design_code.upper().startswith("ASCE"):
            self.code_asce.setChecked(True)
        else:
            self.code_is.setChecked(True)
        self._on_ws_code_family_changed()

        # Preferences pin/fixed become selection unless already on Auto after reset
        if not reset_geometry:
            base = str(prefs.ext_col_base).lower()
            if base.startswith("fix"):
                idx_s = self.ext_base_combo.findData(SupportType.FIXED)
            elif base.startswith("auto"):
                idx_s = self.ext_base_combo.findData("auto")
            else:
                idx_s = self.ext_base_combo.findData(SupportType.PINNED)
            if idx_s >= 0:
                self.ext_base_combo.setCurrentIndex(idx_s)

        self._on_frame_type_changed()
        self._on_ridge_auto_toggled(self.ridge_auto_cb.isChecked())
        self._update_derived()
        self._update_ext_base_hint()

    def _current_frame_type(self) -> FrameType:
        raw = self.frame_type.currentData()
        return coerce_frame_type(raw if raw is not None else FrameType.CLEAR_SPAN)

    def _on_geometry_field_changed(self, *_args) -> None:
        self._sync_int_col_for_multi_span()
        self._sync_ridge_auto_value()
        self._update_derived()
        self._update_ext_base_hint()

    def _on_frame_type_changed(self, *_args) -> None:
        ft = self._current_frame_type()
        allows = frame_allows_interior_columns(ft)
        if not allows:
            self.int_col_edit.setText("0")
            self.int_col_edit.setReadOnly(True)
            self.int_col_edit.setEnabled(False)
        elif ft == FrameType.MULTI_SPAN:
            self.int_col_edit.setEnabled(True)
            self.int_col_edit.setReadOnly(True)
            self._sync_int_col_for_multi_span()
        else:
            self.int_col_edit.setEnabled(True)
            self.int_col_edit.setReadOnly(False)
            if not self.int_col_edit.text().strip():
                self.int_col_edit.setText("0")
        # Ridge distance mainly for clear / asym / multi-span
        ridge_useful = ft in (
            FrameType.CLEAR_SPAN,
            FrameType.ASYM_GABLE,
            FrameType.MULTI_SPAN,
        )
        self.ridge_dist_edit.setEnabled(ridge_useful)
        self.ridge_auto_cb.setEnabled(ridge_useful)
        self._update_derived()
        self._update_ext_base_hint()

    def _on_ridge_auto_toggled(self, checked: bool) -> None:
        self.ridge_dist_edit.setReadOnly(checked)
        self._sync_ridge_auto_value()
        self._update_derived()

    def _sync_ridge_auto_value(self) -> None:
        if not self.ridge_auto_cb.isChecked():
            return
        try:
            widths = parse_spacing_list(
                self.width_edit.text() or "0", field_name="Building width"
            )
            mid = spacing_total(widths) / 2.0
            self.ridge_dist_edit.blockSignals(True)
            self.ridge_dist_edit.setText(f"{mid:g}")
            self.ridge_dist_edit.blockSignals(False)
        except Exception:
            pass

    def _sync_int_col_for_multi_span(self) -> None:
        if self._current_frame_type() != FrameType.MULTI_SPAN:
            return
        text = (self.width_edit.text() or "").strip()
        try:
            widths = parse_spacing_list(text, field_name="Building width")
        except Exception:
            return
        if len(widths) >= 2:
            # Mirror width expression into int-col (read-only)
            self.int_col_edit.blockSignals(True)
            self.int_col_edit.setText(text)
            self.int_col_edit.blockSignals(False)
        elif len(widths) == 1:
            self.int_col_edit.blockSignals(True)
            self.int_col_edit.setText("0")
            self.int_col_edit.blockSignals(False)

    def _update_ext_base_hint(self, *_args) -> None:
        try:
            widths = parse_spacing_list(
                self.width_edit.text() or "0", field_name="Building width"
            )
            width = spacing_total(widths)
            eave = float(self.eave_edit.text() or "0")
        except Exception:
            self.ext_base_hint.setText("")
            return
        try:
            heavy = self.crane_section.has_crane() and float(self.crane_section.capacity_edit.text() or "0") >= 200
        except ValueError:
            self.ext_base_hint.setText("Enter a numeric crane capacity.")
            return
        rec, reason = recommend_ext_col_base(width, eave, heavy_crane=heavy)
        mode = self.ext_base_combo.currentData()
        if mode == "auto":
            self.ext_base_hint.setText(
                f"Ext. Col. Base — Auto → {rec.value.title()} recommended ({reason})"
            )
        else:
            label = "Pinned" if mode == SupportType.PINNED else "Fixed"
            self.ext_base_hint.setText(f"Ext. Col. Base — {label}")

    def _resolved_support_type(self) -> SupportType:
        heavy = self.crane_section.has_crane() and float(
            self.crane_section.capacity_edit.text() or "0"
        ) >= 200
        mode = self.ext_base_combo.currentData()
        try:
            widths = parse_spacing_list(
                self.width_edit.text() or "0", field_name="Building width"
            )
            width = spacing_total(widths)
            eave = float(self.eave_edit.text() or "0")
        except Exception:
            width, eave = 0.0, 0.0
        if mode == "auto":
            rec, _ = recommend_ext_col_base(width, eave, heavy_crane=heavy)
            return rec
        if isinstance(mode, SupportType):
            return mode
        return SupportType(str(mode))

    def _parse_float(self, edit: QLineEdit, name: str) -> float:
        text = edit.text().strip()
        if text == "":
            raise ValidationError([f"{name} is required."])
        try:
            import math
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("non-finite")
            return value
        except ValueError as exc:
            raise ValidationError([f"{name} must be a number."]) from exc

    def read_params(self) -> BuildingGeometryInput:
        try:
            widths = parse_spacing_list(
                self.width_edit.text(), field_name="Building Width"
            )
            int_raw = (self.int_col_edit.text() or "0").strip()
            if int_raw in ("", "0"):
                int_cols: list[float] = []
            else:
                int_cols = parse_spacing_list(
                    int_raw, field_name="Int. Col. Spacing"
                )
        except ValueError as exc:
            raise ValidationError([str(exc)]) from exc

        frame_type = self._current_frame_type()
        try:
            width_spans = resolve_width_spans(frame_type, widths, int_cols)
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ValidationError([str(exc)]) from exc

        length = self._parse_float(self.length_edit, "Building Length")
        bay_expr = self.bay_edit.text().strip()
        try:
            explicit_bays = parse_spacing_list(bay_expr, field_name="Bay Spacing")
        except ValueError as exc:
            raise ValidationError([str(exc)]) from exc
        is_list = any(token in bay_expr for token in ("+", "@", ","))
        bay = explicit_bays[0] if explicit_bays else 0
        if bay <= 0:
            raise ValidationError(["Bay Spacing must be > 0."])
        n = round(length / bay)
        if not is_list and (n < 1 or abs(n * bay - length) > 1e-6):
            raise ValidationError(
                [
                    "Building Length must be an integer multiple of Bay Spacing "
                    f"(length={length:g}, bay={bay:g})."
                ]
            )
        sidewalls = explicit_bays if is_list else [bay] * int(n)
        self.sidewall_edit.setText(f"{int(n)}@{bay:g}" if n > 1 else f"{bay:g}")

        slope_x = self._parse_float(self.slope_x10_edit, "Roof Slope (X:10)")
        try:
            pitch_n = pitch_n_from_slope_x10(slope_x)
        except ValueError as exc:
            raise ValidationError([str(exc)]) from exc

        ridge_auto = self.ridge_auto_cb.isChecked()
        ridge_dist = self._parse_float(self.ridge_dist_edit, "Ridge Distance")

        return BuildingGeometryInput(
            width_spans_m=tuple(width_spans),
            length_m=length,
            sidewall_spacings_m=tuple(sidewalls),
            eave_height_m=self._parse_float(self.eave_edit, "Eave Height"),
            roof_pitch_1_to_n=pitch_n,
            frame_type=frame_type,
            ffl_level_m=self._parse_float(self.ffl_edit, "FFL level"),
            blockwall_height_m=self._parse_float(
                self.blockwall_edit, "Blockwall Height"
            ),
            ridge_distance_m=ridge_dist,
            ridge_auto=ridge_auto,
            roof_loads=RoofLoadsInput(
                dead_kn_m2=self._parse_float(self.dead_edit, "Dead load"),
                collateral_kn_m2=self._parse_float(self.coll_edit, "Collateral load"),
                live_kn_m2=self._parse_float(self.live_edit, "Live load"),
            ),
            wind_seismic=WindSeismicInput(
                wind_speed_mps=self._parse_wind_speed(),
                building_condition=(
                    self._combo_data_text(self.condition)
                    if self.code_asce.isChecked()
                    else self._combo_data_text(self.is_condition)
                ),
                load_combination_label=self._combo_data_text(self.combo_label)
                or "User-defined",
                code_family=self._ws_code_family(),
                terrain_category=self._combo_data_text(self.terrain_category),
                k1_risk=self._parse_float(self.k1_edit, "k1"),
                k3_topography=self._parse_float(self.k3_edit, "k3"),
                k4_importance=self._parse_float(self.k4_edit, "k4"),
                is_seismic_zone=self._combo_data_text(self.is_zone),
                soil_type=self._combo_data_text(self.soil_type),
                response_factor_r=self._parse_float(self.response_r_edit, "Response Factor R"),
                exposure=self._combo_data_text(self.exposure),
                site_class=self._combo_data_text(self.site),
                asce_seismic_zone=self._combo_data_text(self.zone),
                use_dm=self.method_dm.isChecked(),
                use_adm=self.method_adm.isChecked(),
                use_sm=self.method_sm.isChecked(),
                use_others=self.method_others.isChecked(),
                ss_g=self._parse_float(self.ss_edit, "Ss"),
                s1_g=self._parse_float(self.s1_edit, "S1"),
                k2_override=self._parse_float(self.k2_edit, "Wind k2"),
                wind_roof_uplift_kn_m2=self._parse_float(self.uplift_edit, "Roof uplift"),
                seismic_ah=self._parse_float(self.seismic_ah_edit, "Seismic Ah"),
            ),
            mezzanine=self.mezz_section.read_input(),
            crane=self.crane_section.read_crane(),
            extensions=self.extensions_section.read_extensions(),
            roof_monitor=self.extensions_section.read_monitor(),
            load_combination_type=self._combo_data_text(self.combo_label)
            or "IS800-2007-LSD",
            deflection_limits=self._deflection_limits,
        )

    def _update_derived(self) -> None:
        try:
            params = self.read_params()
            errs = validate_building_input(params)
            if errs:
                self.total_width_label.setText("—")
                self.ridge_label.setText("—")
                self.frames_label.setText("—")
                return
            self.total_width_label.setText(f"{params.span_m:.3g} m")
            run = params.span_m / 2.0
            ft = coerce_frame_type(params.frame_type)
            if ft == FrameType.MULTI_GABLE and params.width_spans_m:
                run = max(params.width_spans_m) / 2.0
            elif ft == FrameType.MONO_SLOPE:
                run = params.span_m
            ridge = params.ffl_level_m + params.ridge_height_for_run(run)
            self.ridge_label.setText(f"{ridge:.3f} m")
            self.frames_label.setText(str(params.number_of_frames))
        except (ValidationError, ValueError, TypeError):
            self.total_width_label.setText("—")
            self.ridge_label.setText("—")
            self.frames_label.setText("—")

    def _on_generate(self, _checked=False, *, automatic=False) -> bool:
        if hasattr(self, "_live_timer"):
            self._live_timer.stop()
        self._last_valid = False
        try:
            params = self.read_params()
            prefs = get_preferences()
            support = self._resolved_support_type()
            design_code = (
                self._combo_data_text(self.combo_label) or prefs.design_code
            )
            options = PipelineOptions(
                column_section=str(self.column_section_combo.currentData() or "ISMB 400"),
                rafter_section=str(self.rafter_section_combo.currentData() or "ISMB 350"),
                material=str(self.material_combo.currentData() or "E350"),
                support_type=support,
                run_analysis=self.run_analysis_cb.isChecked(),
                run_design=self.run_design_cb.isChecked(),
                design_code=design_code,
                staad_version=prefs.staad_version,
                purlin_spacing_m=self._parse_float(self.purlin_edit, "Purlin Spacing"),
                girt_spacing_m=self._parse_float(self.girt_edit, "Girt Spacing"),
                export_plane=bool(self.export_mode.currentData()),
                secondary_connection=str(self.secondary_connection_combo.currentData()),
                staad_analysis=str(self.staad_analysis_combo.currentData()),
            )
            result = run_pipeline(params, options=options)
        except ValidationError as exc:
            if not automatic:
                QMessageBox.warning(
                    self,
                    "Invalid input",
                    "Please fix the following:\n" + "\n".join(f"• {m}" for m in exc.messages),
                )
            self.status.setText("Check input: " + "; ".join(exc.messages))
            return False
        except Exception as exc:  # noqa: BLE001
            if not automatic:
                QMessageBox.critical(self, "Generate failed", str(exc))
            self.status.setText("Check input: " + str(exc))
            return False

        model = result.model
        self.total_width_label.setText(f"{model.metadata['span_m']:.3g} m")
        self.ridge_label.setText(f"{model.metadata['ridge_height_m']:.3f} m")
        self.frames_label.setText(str(model.metadata['number_of_frames']))
        msg = (
            f"Ready — {len(model.nodes)} nodes, {len(model.members)} members"
        )
        if model.analysis:
            msg += f" | Analysis: {model.analysis.status}"
        if options.run_design:
            msg += f" | {result.design_summary}"
        self.status.setText(msg)
        warnings = model.metadata.get("audit_warnings", [])
        if warnings:
            self.status.setText(msg + "\n" + "\n".join(warnings))
        self._last_valid = True
        self.model_generated.emit(model, result.staad_text)
        return True

    def _on_clear(self) -> None:
        self._set_defaults()
        self.template_combo.setCurrentIndex(0)
        self.status.setText("Ready")
        self.model_cleared.emit()

    def _on_template_combo_changed(self, _index: int) -> None:
        tpl_id = self.template_combo.currentData()
        if not tpl_id:
            self.template_desc.setText("Choose a preset to fill inputs and test 2D cases.")
            return
        tpl = get_template(str(tpl_id))
        self.template_desc.setText(tpl.description)

    def _on_load_template(self) -> None:
        tpl = self._selected_template()
        if tpl is None:
            return
        self.apply_template(tpl)
        self.status.setText(f"Loaded template: {tpl.name}")

    def _on_load_and_generate(self) -> None:
        tpl = self._selected_template()
        if tpl is None:
            return
        self.apply_template(tpl)
        self._on_generate()

    def _selected_template(self) -> Optional[BuildingTemplate]:
        tpl_id = self.template_combo.currentData()
        if not tpl_id:
            QMessageBox.information(self, "No template", "Select a pre-built template first.")
            return None
        return get_template(str(tpl_id))

    def apply_template(self, tpl: BuildingTemplate) -> None:
        """Fill all input fields from a pre-built template."""
        self.extensions_section.clear()
        self.k1_edit.setText("1")
        self.k2_edit.setText("1")
        self.k3_edit.setText("1")
        self.k4_edit.setText("1")
        self.uplift_edit.setText("0")
        self.seismic_ah_edit.setText("0")
        self.width_edit.setText(tpl.width_expr)
        self.length_edit.setText(str(tpl.length_m))
        ft = coerce_frame_type(tpl.frame_type)
        idx = self.frame_type.findData(ft)
        if idx < 0:
            idx = self.frame_type.findData(ft.value)
        if idx >= 0:
            self.frame_type.setCurrentIndex(idx)
        self.slope_x10_edit.setText(f"{slope_x10_from_pitch_n(tpl.roof_pitch_1_to_n):g}")
        self.pitch_edit.setText(str(tpl.roof_pitch_1_to_n))
        self.eave_edit.setText(str(tpl.eave_height_m))
        self.ffl_edit.setText(str(tpl.ffl_level_m))
        self.sidewall_edit.setText(tpl.sidewall_expr)
        # Derive equal bay spacing from sidewall expression when possible
        try:
            sw = parse_spacing_list(tpl.sidewall_expr, field_name="Sidewall")
            if sw and abs(max(sw) - min(sw)) < 1e-9:
                self.bay_edit.setText(f"{sw[0]:g}")
            elif sw:
                self.bay_edit.setText(tpl.sidewall_expr)
            else:
                self.bay_edit.setText("7.5")
        except Exception:
            self.bay_edit.setText("7.5")
        # Int. col from multi-token width
        try:
            w = parse_spacing_list(tpl.width_expr, field_name="Width")
            if len(w) >= 2:
                self.int_col_edit.setText(tpl.width_expr)
            else:
                self.int_col_edit.setText("0")
        except Exception:
            self.int_col_edit.setText("0")
        self.ridge_auto_cb.setChecked(True)
        self.blockwall_edit.setText(str(tpl.blockwall_height_m))
        self.wind_speed.setText(f"{tpl.wind_speed_mps:g}")
        self.asce_wind_speed.setText(f"{tpl.wind_speed_mps:g}")
        self._set_combo_data(self.exposure, tpl.exposure)
        self._set_combo_data(self.is_condition, tpl.building_condition)
        self._set_combo_data(self.condition, tpl.building_condition)
        zone = tpl.seismic_zone
        if zone in ("I", "II", "III", "IV", "V"):
            self._set_combo_data(self.is_zone, zone)
        else:
            self._set_combo_data(self.zone, zone)
        self._set_combo_data(self.site, tpl.site_class)
        self.dead_edit.setText(str(tpl.dead_kn_m2))
        self.coll_edit.setText(str(tpl.collateral_kn_m2))
        self.live_edit.setText(str(tpl.live_kn_m2))
        self.mezz_section.set_legacy(
            enabled=tpl.mezzanine_enabled,
            width_m=tpl.mezz_width_m,
            height_m=tpl.mezz_height_m,
            col_spacing_m=tpl.mezz_col_spacing_m,
        )
        self.crane_section.set_legacy(
            enabled=tpl.crane_enabled,
            name=tpl.crane_name,
            capacity_kn=tpl.crane_capacity_kn,
            runway_height_m=tpl.crane_runway_height_m,
        )
        self._on_frame_type_changed()
        self._on_ridge_auto_toggled(True)
        self._update_derived()
        self._update_ext_base_hint()
