"""Section Database dialog — stocked plate sizes for built-up sections."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.preferences import get_preferences, set_preferences
from app.database.plate_catalog import (
    MAX_FLANGE_THICKNESS_MM,
    MAX_FLANGE_WIDTH_MM,
    MAX_OVERALL_DEPTH_MM,
    MAX_WEB_THICKNESS_MM,
    PlateCatalog,
    format_mm_list,
    get_plate_catalog,
    parse_mm_list,
    set_plate_catalog,
)
from app.database.sections import SectionDatabase


class SectionDatabaseDialog(QDialog):
    """Edit plate sizes used to generate built-up sections."""

    catalog_saved = Signal(object)  # PlateCatalog

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Section Database")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self._build_ui()
        self.load_from(get_plate_catalog())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)

        title = QLabel("Section Database")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        hint = QLabel(
            "The plate sizes you stock, in mm, comma-separated. "
            "Built-up sections are generated from these only. "
            f"Maximum: depth {MAX_OVERALL_DEPTH_MM:g} · web {MAX_WEB_THICKNESS_MM:g} · "
            f"flange width {MAX_FLANGE_WIDTH_MM:g} · flange thickness {MAX_FLANGE_THICKNESS_MM:g}."
        )
        hint.setWordWrap(True)
        hint.setObjectName("panelHint")
        root.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.web_depths = QTextEdit()
        self.web_thicknesses = QTextEdit()
        self.flange_widths = QTextEdit()
        self.flange_thicknesses = QTextEdit()
        for w in (
            self.web_depths,
            self.web_thicknesses,
            self.flange_widths,
            self.flange_thicknesses,
        ):
            w.setAcceptRichText(False)
            w.setMaximumHeight(72)

        form.addRow("Web Depths (clear, mm)", self.web_depths)
        form.addRow("Web Thicknesses (mm)", self.web_thicknesses)
        form.addRow("Flange Widths (mm)", self.flange_widths)
        form.addRow("Flange Thicknesses (mm)", self.flange_thicknesses)
        root.addLayout(form)

        self.default_cb = QCheckBox("Also use this as the default for new projects")
        self.default_cb.setChecked(True)
        root.addWidget(self.default_cb)

        self.status = QLabel("")
        self.status.setObjectName("panelHint")
        root.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def load_from(self, catalog: PlateCatalog) -> None:
        self.web_depths.setPlainText(format_mm_list(catalog.web_depths_mm))
        self.web_thicknesses.setPlainText(format_mm_list(catalog.web_thicknesses_mm))
        self.flange_widths.setPlainText(format_mm_list(catalog.flange_widths_mm))
        self.flange_thicknesses.setPlainText(
            format_mm_list(catalog.flange_thicknesses_mm)
        )
        self.default_cb.setChecked(catalog.use_as_project_default)

    def read_catalog(self) -> PlateCatalog:
        return PlateCatalog(
            web_depths_mm=parse_mm_list(
                self.web_depths.toPlainText(), field_name="Web Depths"
            ),
            web_thicknesses_mm=parse_mm_list(
                self.web_thicknesses.toPlainText(), field_name="Web Thicknesses"
            ),
            flange_widths_mm=parse_mm_list(
                self.flange_widths.toPlainText(), field_name="Flange Widths"
            ),
            flange_thicknesses_mm=parse_mm_list(
                self.flange_thicknesses.toPlainText(),
                field_name="Flange Thicknesses",
            ),
            use_as_project_default=self.default_cb.isChecked(),
        )

    def _on_save(self) -> None:
        try:
            catalog = self.read_catalog()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid plate list", str(exc))
            return

        errors = catalog.validate()
        if errors:
            QMessageBox.warning(
                self,
                "Invalid Section Database",
                "\n".join(f"• {e}" for e in errors),
            )
            return

        set_plate_catalog(catalog, persist=True)

        # Keep a copy on preferences when marked as project default
        if catalog.use_as_project_default:
            prefs = get_preferences()
            prefs.plate_catalog = catalog.to_dict()
            set_preferences(prefs, persist=True)

        try:
            n = SectionDatabase().sync_builtup_from_plate_catalog(catalog)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Section sync failed", str(exc))
            return

        self.status.setText(f"Saved. Built-up library refreshed: {n} sections.")
        self.catalog_saved.emit(catalog)
        self.accept()
