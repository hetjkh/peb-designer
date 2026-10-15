"""Main application window — Milestone 1."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.models import StructuralModel
from app.core.preferences import get_preferences, set_preferences
from app.export.staad import export_staad_std
from app.export.staad_import import import_staad_std
from app.export.staad_audit import format_staad_audit
from app.gui.theme import normalize_theme, stylesheet_for
from app.gui.widgets.building_input_panel import BuildingInputPanel
from app.gui.widgets.frame_preview_2d import FramePreview2D
from app.gui.widgets.member_info_panel import MemberInfoPanel
from app.gui.widgets.preferences_dialog import PreferencesDialog
from app.gui.widgets.section_database_dialog import SectionDatabaseDialog
from app.database.plate_catalog import get_plate_catalog
from app.database.sections import SectionDatabase
from app.gui.widgets.staad_output_panel import StaadOutputPanel
from app.visualization.viewer_3d import StructuralViewer3D


class MainWindow(QMainWindow):
    """Primary desktop window for PEB Designer."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"PEB Designer  v{__version__}")
        self.resize(1440, 900)
        prefs = get_preferences()
        self._theme = normalize_theme(prefs.ui_theme)
        self.setStyleSheet(stylesheet_for(self._theme))

        self._model: Optional[StructuralModel] = None
        self._staad_text: str = ""

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._ensure_builtup_library()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"Code: {prefs.design_code}  |  STAAD: {prefs.staad_version}  |  "
            "Theme / Preferences / Section Database available in toolbar. "
            "Not validated for construction design."
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New Project (apply Preferences)", self)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)
        file_menu.addSeparator()

        import_action = QAction("Import STAAD reference (.std + matching .anl)...", self)
        import_action.triggered.connect(self._import_staad)
        file_menu.addAction(import_action)

        export_action = QAction("Export STAAD.Pro (.std)...", self)
        export_action.triggered.connect(self._export_staad)
        file_menu.addAction(export_action)
        file_menu.addSeparator()

        prefs_action = QAction("&Preferences...", self)
        prefs_action.triggered.connect(self._open_preferences)
        file_menu.addAction(prefs_action)

        section_db_action = QAction("Section &Database...", self)
        section_db_action.triggered.connect(self._open_section_database)
        file_menu.addAction(section_db_action)
        file_menu.addSeparator()

        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&View")
        theme_action = QAction("Toggle Light / Dark Theme", self)
        theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(theme_action)
        reset_cam = QAction("Reset Camera", self)
        reset_cam.triggered.connect(self._reset_camera)
        view_menu.addAction(reset_cam)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        project_label = QLabel("PROJECT WORKSPACE")
        project_label.setObjectName("eyebrow")
        toolbar.addWidget(project_label)
        toolbar.addSeparator()

        import_btn = QAction("Import STD", self)
        import_btn.triggered.connect(self._import_staad)
        toolbar.addAction(import_btn)

        spacer = QWidget()
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        prefs_btn = QAction("Preferences", self)
        prefs_btn.triggered.connect(self._open_preferences)
        toolbar.addAction(prefs_btn)

        section_db_btn = QAction("Section Database", self)
        section_db_btn.triggered.connect(self._open_section_database)
        toolbar.addAction(section_db_btn)

        self.theme_btn = QAction(self._theme_action_label(), self)
        self.theme_btn.triggered.connect(self._toggle_theme)
        toolbar.addAction(self.theme_btn)

    def _build_view_controls(self) -> QWidget:
        controls = QWidget()
        controls.setObjectName("viewerControls")
        row = QHBoxLayout(controls)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(16)
        caption = QLabel("DISPLAY")
        caption.setObjectName("eyebrow")
        row.addWidget(caption)
        self.node_ids_cb = QCheckBox("Node IDs")
        self.node_ids_cb.setChecked(True)
        self.node_ids_cb.toggled.connect(self._toggle_node_ids)
        row.addWidget(self.node_ids_cb)

        self.member_ids_cb = QCheckBox("Member IDs")
        self.member_ids_cb.setChecked(True)
        self.member_ids_cb.toggled.connect(self._toggle_member_ids)
        row.addWidget(self.member_ids_cb)

        self.loads_cb = QCheckBox("Loads")
        self.loads_cb.setChecked(True)
        self.loads_cb.toggled.connect(self._toggle_loads)
        row.addWidget(self.loads_cb)

        self.util_cb = QCheckBox("Utilization colors")
        self.util_cb.setChecked(True)
        self.util_cb.toggled.connect(self._toggle_util)
        row.addWidget(self.util_cb)
        self.reference_frame_combo = QComboBox()
        self.reference_frame_combo.setToolTip("Reference 2D geometry slice by Z station; this does not change the native export.")
        self.reference_frame_combo.setVisible(False)
        self.reference_frame_combo.currentIndexChanged.connect(self._on_reference_frame)
        row.addWidget(self.reference_frame_combo)
        row.addStretch(1)

        reset_btn = QPushButton("Reset camera")
        reset_btn.clicked.connect(self._reset_camera)
        row.addWidget(reset_btn)
        return controls

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        self.input_panel = BuildingInputPanel()
        self.input_panel.setMinimumWidth(400)
        self.input_panel.setMaximumWidth(560)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(20, 18, 20, 12)
        workspace_layout.setSpacing(12)
        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        eyebrow = QLabel("MODEL / WORKSPACE")
        eyebrow.setObjectName("eyebrow")
        heading_text.addWidget(eyebrow)
        title = QLabel("Dashboard")
        title.setObjectName("workspaceTitle")
        heading_text.addWidget(title)
        heading.addLayout(heading_text)
        heading.addStretch(1)
        badge = QLabel("2D + 3D  /  STAAD")
        badge.setObjectName("modelBadge")
        heading.addWidget(badge)
        workspace_layout.addLayout(heading)
        workspace_layout.addWidget(self._build_view_controls())

        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        right.setHandleWidth(10)
        self.tabs = QTabWidget()
        self.preview_2d = FramePreview2D()
        self.viewer = StructuralViewer3D()
        self.viewer.clear()
        self.tabs.addTab(self.preview_2d, "2D Preview")
        self.tabs.addTab(self.viewer, "3D Model")
        self.layout_preview = FramePreview2D()
        self.tabs.addTab(self.layout_preview, "Layout / clearances")
        self.tabs.currentChanged.connect(self._refresh_visible_view)

        right_side = QWidget()
        rs = QVBoxLayout(right_side)
        rs.setContentsMargins(14, 12, 14, 12)
        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("Select member"))
        self.member_combo = QComboBox()
        self.member_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.member_combo.setMinimumContentsLength(20)
        self.member_combo.currentIndexChanged.connect(self._on_member_combo)
        pick_row.addWidget(self.member_combo, stretch=1)
        rs.addLayout(pick_row)
        self.member_info = MemberInfoPanel()
        rs.addWidget(self.member_info, stretch=1)

        self.staad_panel = StaadOutputPanel()
        self.staad_panel.create_btn.clicked.connect(self._export_staad)
        self.staad_panel.copy_btn.clicked.connect(self._copy_staad)
        self.staad_panel.clear_btn.clicked.connect(self._clear_staad_output)

        self.results_tabs = QTabWidget()
        self.results_tabs.addTab(self.staad_panel, "STAAD output")
        self.results_tabs.addTab(right_side, "Member inspector")
        self.audit_panel = QTextEdit()
        self.audit_panel.setReadOnly(True)
        self.audit_panel.setPlaceholderText("Generate or import a model to inspect its review findings.")
        self.results_tabs.addTab(self.audit_panel, "Model audit")
        right.addWidget(self.tabs)
        right.addWidget(self.results_tabs)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 1)
        right.setSizes([480, 220])
        workspace_layout.addWidget(right, 1)

        splitter.addWidget(self.input_panel)
        splitter.addWidget(workspace)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 900])

        layout.addWidget(splitter, stretch=1)

        self.input_panel.model_generated.connect(self._on_model_generated)
        self.input_panel.model_cleared.connect(self._on_model_cleared)
        self.input_panel.inputs_pending.connect(self._on_inputs_pending)

    def _on_inputs_pending(self) -> None:
        if self._model and self._model.metadata.get("imported_from"):
            self._model = None
        self._staad_text = ""
        self.staad_panel.clear()
        self.member_info.clear()
        self.audit_panel.clear()
        self.statusBar().showMessage("Inputs changed; updating model. Previous view is pending refresh.")

    def _on_model_generated(self, model: StructuralModel, staad_text: str) -> None:
        self._model = model
        self.reference_frame_combo.setVisible(False)
        self.loads_cb.setEnabled(True)
        self.loads_cb.setToolTip("Show a sample of generated dead/wind member loads.")
        self._staad_text = staad_text
        self.audit_panel.setPlainText(format_staad_audit(model))
        self.preview_2d.set_model(model)
        self.layout_preview.set_from_metadata(model.metadata)
        self._viewer_pending = True
        self._refresh_visible_view()
        self.staad_panel.set_text(staad_text)
        self._fill_member_combo(model)
        msg = f"Generated {len(model.nodes)} nodes, {len(model.members)} members."
        if model.analysis:
            msg += f" Analysis: {model.analysis.status}."
        if model.design_results:
            n_fail = sum(1 for r in model.design_results.values() if r.status == "FAIL")
            msg += f" Design FAIL count: {n_fail}."
        msg += " Not validated for construction."
        self.statusBar().showMessage(msg)

    def _refresh_visible_view(self, *_args) -> None:
        if self.tabs.currentWidget() is self.viewer and self._model is not None and getattr(self, "_viewer_pending", False):
            self.viewer.display_model(self._model)
            self._viewer_pending = False

    def _on_model_cleared(self) -> None:
        self._model = None
        self.reference_frame_combo.setVisible(False)
        self.loads_cb.setEnabled(True)
        self._staad_text = ""
        self.preview_2d.clear_preview()
        self.layout_preview.clear_preview()
        self.viewer.clear()
        self.staad_panel.clear()
        self.member_combo.clear()
        self.member_info.clear()
        self.audit_panel.clear()
        self.statusBar().showMessage("Model cleared.")

    def _fill_member_combo(self, model: StructuralModel) -> None:
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        self.member_combo.addItem("—", None)
        for m in model.member_list():
            tag = f"M{m.id}  {m.member_type}  {m.section or ''}"
            if m.id in model.design_results:
                dr = model.design_results[m.id]
                tag += f"  [{dr.status} {dr.max_utilization:.2f}]"
            self.member_combo.addItem(tag, m.id)
        self.member_combo.blockSignals(False)

    def _on_member_combo(self, _index: int) -> None:
        if self._model is None:
            return
        mid = self.member_combo.currentData()
        if mid is None:
            self.member_info.clear()
            self.viewer.select_member(None)
            return
        self.viewer.select_member(int(mid))
        self.member_info.show_member(self._model, int(mid))

    def _copy_staad(self) -> None:
        if not self._prepare_current_model():
            return
        text = self.staad_panel.text()
        if not text.strip():
            QMessageBox.information(self, "Nothing to copy", "Generate a model first.")
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("STAAD input copied to clipboard.")

    def _clear_staad_output(self) -> None:
        self.staad_panel.clear()

    def _import_staad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import STAAD.Pro Input File",
            "",
            "STAAD Input (*.std);;All Files (*)",
        )
        if not path:
            return
        try:
            model = import_staad_std(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Import failed",
                f"Could not read STD file:\n{exc}",
            )
            return

        # Show raw file text in STAAD panel
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""

        self._model = model
        self._staad_text = raw
        self.loads_cb.setEnabled(False)
        self.loads_cb.setToolTip("Native local-axis, seismic and generated loads must be viewed in STAAD.Pro. Definitions are retained in STAAD output / Model audit.")
        self.input_panel._live_timer.stop()
        self.staad_panel.set_text(raw if raw else f"* Imported: {path}")
        self.viewer.display_model(model)
        self.tabs.setCurrentWidget(self.viewer)
        self._fill_member_combo(model)
        self.member_info.clear()
        self.audit_panel.setPlainText(format_staad_audit(model))
        self.results_tabs.setCurrentWidget(self.audit_panel)
        self.layout_preview.clear_preview()
        self._viewer_pending = False

        self.reference_frame_combo.blockSignals(True)
        self.reference_frame_combo.clear()
        for station in sorted({n.z for n in model.nodes.values()}):
            self.reference_frame_combo.addItem(f"2D: Z={station:g} m", station)
        self.reference_frame_combo.blockSignals(False)
        self.reference_frame_combo.setVisible(True)
        self._on_reference_frame()

        self.statusBar().showMessage(
            f"Imported STD: {len(model.nodes)} joints, {len(model.members)} members — shown in 3D."
        )
        QMessageBox.information(
            self,
            "STD imported",
            (
                f"Loaded:\n{path}\n\n"
                f"Joints: {len(model.nodes)}\n"
                f"Members: {len(model.members)}\n"
                f"Supports: {len(model.supports)}\n\n"
                f"Load cases: {len(model.load_cases)}\n"
                f"Combinations: {len(model.combinations)}\n"
                f"Matching native design results: {len(model.design_results)}\n\n"
                "See Model audit for failures, missing checks and native load details.\n"
                "Use Member inspector to see releases, section dimensions and design parameters.\n"
                "Sidebar changes generate a new model; they do not resize this reference."
            ),
        )

    def _on_reference_frame(self, *_args) -> None:
        if self._model and self._model.metadata.get("staad_native"):
            self.preview_2d.set_model(self._model, station=self.reference_frame_combo.currentData())

    def _export_staad(self) -> None:
        if not self._prepare_current_model():
            return
        if self._model is None or not self._model.nodes:
            QMessageBox.information(
                self,
                "No model",
                "Generate a model first, then create the STD file.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Create STAAD.Pro Input File",
            "peb_model.std",
            "STAAD Input (*.std);;All Files (*)",
        )
        if not path:
            return

        try:
            # Imported files contain commands outside our geometry parser;
            # retain their original text rather than silently stripping loads.
            written = Path(path)
            if written.suffix.lower() != ".std":
                written = written.with_suffix(".std")
            written.write_text(self._staad_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        self.statusBar().showMessage(f"Exported STAAD file: {written}")
        QMessageBox.information(
            self,
            "STD file created",
            (
                f"Saved:\n{written}\n\n"
                "In STAAD.Pro: File → Open → select this .std file."
            ),
        )

    def _prepare_current_model(self) -> bool:
        if self._model and self._model.metadata.get("imported_from"):
            from app.export.staad_import import preserved_staad_text
            try:
                self._staad_text = preserved_staad_text(self._model)
            except ValueError as exc:
                QMessageBox.warning(self, "Native model changed", str(exc))
                return False
            self.staad_panel.set_text(self._staad_text)
            return True
        if self.input_panel.flush_update():
            self.staad_panel.set_text(self._staad_text)
            return True
        QMessageBox.warning(self, "Inputs need attention", self.input_panel.status.text())
        return False

    def _toggle_node_ids(self, checked: bool) -> None:
        self.viewer.show_node_ids = checked

    def _toggle_member_ids(self, checked: bool) -> None:
        self.viewer.show_member_ids = checked

    def _toggle_loads(self, checked: bool) -> None:
        self.viewer.show_loads = checked

    def _toggle_util(self, checked: bool) -> None:
        self.viewer.show_utilization = checked

    def _theme_action_label(self) -> str:
        return "Dark Mode" if self._theme == "light" else "Light Mode"

    def _apply_theme(self, theme: str, *, persist: bool = True) -> None:
        self._theme = normalize_theme(theme)
        self.setStyleSheet(stylesheet_for(self._theme))
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText(self._theme_action_label())
        if persist:
            prefs = get_preferences()
            prefs.ui_theme = self._theme
            set_preferences(prefs, persist=True)
        self.statusBar().showMessage(f"Theme: {self._theme.title()} mode")

    def _toggle_theme(self) -> None:
        self._apply_theme("dark" if self._theme == "light" else "light")

    def _open_preferences(self) -> None:
        dialog = PreferencesDialog(self)
        dialog.preferences_saved.connect(self._on_preferences_saved)
        dialog.exec()

    def _open_section_database(self) -> None:
        dialog = SectionDatabaseDialog(self)
        dialog.catalog_saved.connect(self._on_section_database_saved)
        dialog.exec()

    def _ensure_builtup_library(self) -> None:
        """Sync BUILTUP rows from the plate catalog if only seed BUs exist."""
        try:
            db = SectionDatabase()
            builtups = [s for s in db.list_sections() if s.designation_type == "BUILTUP"]
            # Seed DB has 3 illustrative BUs; regenerate from catalog when small
            if len(builtups) < 20:
                db.sync_builtup_from_plate_catalog(get_plate_catalog())
                self.input_panel.refresh_sections()
        except Exception:
            pass

    def _on_section_database_saved(self, catalog) -> None:
        self.input_panel.refresh_sections()
        n_depths = len(catalog.web_depths_mm)
        self.statusBar().showMessage(
            f"Section Database saved — {n_depths} web depths; "
            "built-up library refreshed in section lists."
        )

    def _on_preferences_saved(self, prefs) -> None:
        # Update current form defaults without wiping user geometry edits
        self.input_panel.apply_preferences(prefs, reset_geometry=False)
        if getattr(prefs, "ui_theme", None):
            self._apply_theme(prefs.ui_theme, persist=False)
        self.statusBar().showMessage(
            f"Preferences saved — Code: {prefs.design_code}  |  "
            f"STAAD: {prefs.staad_version}  |  "
            f"Theme: {normalize_theme(prefs.ui_theme).title()}  |  "
            f"Dead/Coll: {prefs.roof_dead_kn_m2}/{prefs.roof_collateral_kn_m2} kN/m²  |  "
            f"Base: {prefs.ext_col_base}"
        )

    def _new_project(self) -> None:
        prefs = get_preferences()
        if prefs.plate_catalog:
            try:
                from app.database.plate_catalog import PlateCatalog, set_plate_catalog

                cat = PlateCatalog.from_dict(prefs.plate_catalog)
                set_plate_catalog(cat, persist=True)
                SectionDatabase().sync_builtup_from_plate_catalog(cat)
                self.input_panel.refresh_sections()
            except Exception:
                pass
        self.input_panel.apply_preferences(prefs, reset_geometry=True)
        self.input_panel.status.setText("Ready — new project defaults from Preferences")
        self._on_model_cleared()
        self.statusBar().showMessage(
            f"New project — defaults from Preferences ({prefs.design_code})."
        )

    def _reset_camera(self) -> None:
        self.viewer.reset_camera()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About PEB Designer",
            (
                f"<b>PEB Designer</b> v{__version__}<br><br>"
                "Independent PEB geometry, loads, analysis, and IS 800:2007 checks.<br>"
                "Analysis uses a built-in 2D direct-stiffness engine (OpenSees optional later).<br>"
                "Not affiliated with STAGen or Bentley STAAD.<br><br>"
                "<i>Not validated for real construction design.</i>"
            ),
        )
