"""Preferences dialog — defaults for new projects."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.preferences import (
    DESIGN_CODES,
    STAAD_VERSIONS,
    AppPreferences,
    get_preferences,
    set_preferences,
)


class PreferencesDialog(QDialog):
    """Edit application defaults used when starting / clearing a project."""

    preferences_saved = Signal(object)  # AppPreferences

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build_ui()
        self.load_from(get_preferences())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)

        title = QLabel("Preferences")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        hint = QLabel("Defaults applied when you open a New Project / Clear inputs.")
        hint.setWordWrap(True)
        hint.setObjectName("panelHint")
        root.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.design_code = QComboBox()
        for code in DESIGN_CODES:
            self.design_code.addItem(code, code)

        self.dead_edit = self._number_field(allow_zero=True)
        self.coll_edit = self._number_field(allow_zero=True)

        self.staad_version = QComboBox()
        self.staad_version.setEditable(True)
        for ver in STAAD_VERSIONS:
            self.staad_version.addItem(ver)

        self.purlin_edit = self._number_field()
        self.girt_edit = self._number_field()

        self.ext_base = QComboBox()
        self.ext_base.addItem("Auto", "auto")
        self.ext_base.addItem("Pinned", "pinned")
        self.ext_base.addItem("Fixed", "fixed")

        self.ui_theme = QComboBox()
        self.ui_theme.addItem("Light", "light")
        self.ui_theme.addItem("Dark", "dark")

        form.addRow("Design Code", self.design_code)
        form.addRow("Roof Dead Load (kN/m²)", self.dead_edit)
        form.addRow("Roof Collateral Load (kN/m²)", self.coll_edit)
        form.addRow("STAAD.Pro Version", self.staad_version)
        form.addRow("Purlin Spacing (m)", self.purlin_edit)
        form.addRow("Girt Spacing (m)", self.girt_edit)
        form.addRow("Ext. Col. Base", self.ext_base)
        form.addRow("UI Theme", self.ui_theme)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _number_field(self, allow_zero: bool = False) -> QLineEdit:
        edit = QLineEdit()
        bottom = 0.0 if allow_zero else 0.0001
        validator = QDoubleValidator(bottom, 1_000_000.0, 6, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        return edit

    def load_from(self, prefs: AppPreferences) -> None:
        idx = self.design_code.findData(prefs.design_code)
        if idx < 0:
            idx = self.design_code.findText(prefs.design_code)
        self.design_code.setCurrentIndex(max(0, idx))
        self.dead_edit.setText(str(prefs.roof_dead_kn_m2))
        self.coll_edit.setText(str(prefs.roof_collateral_kn_m2))
        self.staad_version.setCurrentText(prefs.staad_version)
        self.purlin_edit.setText(str(prefs.purlin_spacing_m))
        self.girt_edit.setText(str(prefs.girt_spacing_m))
        base_idx = self.ext_base.findData(prefs.ext_col_base)
        self.ext_base.setCurrentIndex(max(0, base_idx))
        theme_idx = self.ui_theme.findData(prefs.ui_theme)
        self.ui_theme.setCurrentIndex(max(0, theme_idx))

    def read_preferences(self) -> AppPreferences:
        def _f(edit: QLineEdit, fallback: float) -> float:
            text = edit.text().strip()
            if not text:
                return fallback
            return float(text)

        existing = get_preferences()
        return AppPreferences(
            design_code=str(self.design_code.currentData() or self.design_code.currentText()),
            roof_dead_kn_m2=_f(self.dead_edit, 0.3),
            roof_collateral_kn_m2=_f(self.coll_edit, 0.15),
            staad_version=self.staad_version.currentText().strip()
            or STAAD_VERSIONS[0],
            purlin_spacing_m=_f(self.purlin_edit, 1.5),
            girt_spacing_m=_f(self.girt_edit, 1.5),
            ext_col_base=str(self.ext_base.currentData() or "pinned"),
            ui_theme=str(self.ui_theme.currentData() or "light"),
            plate_catalog=existing.plate_catalog,
        )

    def _on_save(self) -> None:
        try:
            prefs = self.read_preferences()
        except ValueError:
            return
        set_preferences(prefs, persist=True)
        self.preferences_saved.emit(prefs)
        self.accept()
