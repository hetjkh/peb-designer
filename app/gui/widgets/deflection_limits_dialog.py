"""Deflection Limits dialog — serviceability L/N and H/N denominators."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.geometry.peb_frame import DeflectionLimits


class DeflectionLimitsDialog(QDialog):
    """Edit vertical rafter and horizontal column sway deflection limits."""

    limits_saved = Signal(object)  # DeflectionLimits

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        limits: Optional[DeflectionLimits] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Deflection Limits")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._limits = limits or DeflectionLimits()
        self._build_ui()
        self.load_from(self._limits)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel("Deflection Limits")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        vert = QGroupBox("VERTICAL — Rafter")
        vf = QFormLayout(vert)
        self.total_edit = self._number_field()
        self.live_edit = self._number_field()
        vf.addRow("Total Load (DL+LL)  Span /", self.total_edit)
        vf.addRow("Live Load only  Span /", self.live_edit)
        root.addWidget(vert)

        horiz = QGroupBox("HORIZONTAL — Column Sway")
        hf = QFormLayout(horiz)
        hint = QLabel("H = eave height")
        hint.setObjectName("panelHint")
        hf.addRow(hint)
        self.wind_edit = self._number_field()
        self.seis_edit = self._number_field()
        hf.addRow("Wind / Crane  H /", self.wind_edit)
        hf.addRow("Seismic  H /", self.seis_edit)
        root.addWidget(horiz)

        row = QHBoxLayout()
        defaults_btn = QPushButton("Defaults")
        defaults_btn.clicked.connect(self._on_defaults)
        row.addWidget(defaults_btn)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Done")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        buttons.accepted.connect(self._on_done)
        row.addWidget(buttons)
        root.addLayout(row)

    def _number_field(self) -> QLineEdit:
        edit = QLineEdit()
        validator = QDoubleValidator(1.0, 1_000_000.0, 2, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        return edit

    def load_from(self, limits: DeflectionLimits) -> None:
        self.total_edit.setText(f"{limits.rafter_total_load_L_over:g}")
        self.live_edit.setText(f"{limits.rafter_live_load_L_over:g}")
        self.wind_edit.setText(f"{limits.column_wind_crane_H_over:g}")
        self.seis_edit.setText(f"{limits.column_seismic_H_over:g}")

    def read_limits(self) -> DeflectionLimits:
        def _f(edit: QLineEdit, fallback: float) -> float:
            text = edit.text().strip()
            if not text:
                return fallback
            return float(text)

        return DeflectionLimits(
            rafter_total_load_L_over=_f(self.total_edit, 120.0),
            rafter_live_load_L_over=_f(self.live_edit, 180.0),
            column_wind_crane_H_over=_f(self.wind_edit, 75.0),
            column_seismic_H_over=_f(self.seis_edit, 75.0),
        )

    def _on_defaults(self) -> None:
        self.load_from(DeflectionLimits())

    def _on_done(self) -> None:
        try:
            limits = self.read_limits()
        except ValueError:
            return
        self._limits = limits
        self.limits_saved.emit(limits)
        self.accept()

    def limits(self) -> DeflectionLimits:
        return self._limits
