"""Geometry input panel for Milestone 1."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import StructuralModel
from app.geometry.peb_frame import BuildingGeometryInput, generate_peb_model
from app.geometry.validation import ValidationError, validate_geometry_input


class GeometryPanel(QWidget):
    """Collects PEB geometry inputs and emits a generated StructuralModel."""

    model_generated = Signal(object)  # StructuralModel
    model_cleared = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._set_defaults()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Building Geometry")
        title.setObjectName("panelTitle")
        root.addWidget(title)

        hint = QLabel(
            "Enter PEB dimensions, then generate the portal-frame model."
        )
        hint.setWordWrap(True)
        hint.setObjectName("panelHint")
        root.addWidget(hint)

        form_box = QGroupBox("Inputs")
        form = QFormLayout(form_box)

        self.span_edit = self._number_field()
        self.length_edit = self._number_field()
        self.eave_edit = self._number_field()
        self.slope_edit = self._number_field(allow_zero=True)
        self.bay_edit = self._number_field()

        form.addRow("Span (m)", self.span_edit)
        form.addRow("Length (m)", self.length_edit)
        form.addRow("Eave height (m)", self.eave_edit)
        form.addRow("Roof slope (°)", self.slope_edit)
        form.addRow("Bay spacing (m)", self.bay_edit)
        root.addWidget(form_box)

        derived_box = QGroupBox("Derived")
        derived = QFormLayout(derived_box)
        self.ridge_label = QLabel("—")
        self.frames_label = QLabel("—")
        self.bays_label = QLabel("—")
        derived.addRow("Ridge height", self.ridge_label)
        derived.addRow("Number of bays", self.bays_label)
        derived.addRow("Number of frames", self.frames_label)
        root.addWidget(derived_box)

        for edit in (
            self.span_edit,
            self.length_edit,
            self.eave_edit,
            self.slope_edit,
            self.bay_edit,
        ):
            edit.textChanged.connect(self._update_derived_preview)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Model")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self.clear_btn)
        root.addLayout(btn_row)

        self.export_hint = QLabel(
            "After generate: File → Export STAAD.Pro (.std) to open in STAAD."
        )
        self.export_hint.setWordWrap(True)
        self.export_hint.setObjectName("panelHint")
        root.addWidget(self.export_hint)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(140)
        self.status_box.setPlaceholderText("Validation and generation messages appear here.")
        root.addWidget(self.status_box)

        root.addStretch(1)

    def _number_field(self, allow_zero: bool = False) -> QLineEdit:
        edit = QLineEdit()
        bottom = 0.0 if allow_zero else 0.0001
        validator = QDoubleValidator(bottom, 1_000_000.0, 6, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        edit.setClearButtonEnabled(True)
        return edit

    def _set_defaults(self) -> None:
        # Typical warehouse-scale defaults for first-run demo
        self.span_edit.setText("20")
        self.length_edit.setText("60")
        self.eave_edit.setText("8")
        self.slope_edit.setText("10")
        self.bay_edit.setText("6")
        self._update_derived_preview()

    def _parse_float(self, edit: QLineEdit, name: str) -> float:
        text = edit.text().strip()
        if not text:
            raise ValidationError([f"{name} is required."])
        try:
            return float(text)
        except ValueError as exc:
            raise ValidationError([f"{name} must be a number."]) from exc

    def _read_inputs(self) -> BuildingGeometryInput:
        return BuildingGeometryInput(
            span_m=self._parse_float(self.span_edit, "Span"),
            length_m=self._parse_float(self.length_edit, "Length"),
            eave_height_m=self._parse_float(self.eave_edit, "Eave height"),
            roof_slope_deg=self._parse_float(self.slope_edit, "Roof slope"),
            bay_spacing_m=self._parse_float(self.bay_edit, "Bay spacing"),
        )

    def _update_derived_preview(self) -> None:
        try:
            params = self._read_inputs()
            messages = validate_geometry_input(
                span_m=params.span_m,
                length_m=params.length_m,
                eave_height_m=params.eave_height_m,
                roof_slope_deg=params.roof_slope_deg,
                bay_spacing_m=params.bay_spacing_m,
            )
            if messages:
                self.ridge_label.setText("—")
                self.bays_label.setText("—")
                self.frames_label.setText("—")
                return
            self.ridge_label.setText(f"{params.ridge_height_m:.3f} m")
            self.bays_label.setText(str(params.number_of_bays))
            self.frames_label.setText(str(params.number_of_frames))
        except ValidationError:
            self.ridge_label.setText("—")
            self.bays_label.setText("—")
            self.frames_label.setText("—")

    def _on_generate(self) -> None:
        try:
            params = self._read_inputs()
            model = generate_peb_model(params)
        except ValidationError as exc:
            self._show_errors(exc.messages)
            return
        except Exception as exc:  # noqa: BLE001 — surface unexpected errors in UI
            self._show_errors([f"Unexpected error: {exc}"])
            return

        self.status_box.setStyleSheet("color: #1B5E20;")
        self.status_box.setPlainText(
            "Model generated successfully.\n"
            f"• Nodes: {len(model.nodes)}\n"
            f"• Members: {len(model.members)}\n"
            f"• Frames: {model.metadata.get('number_of_frames')}\n"
            f"• Ridge height: {model.metadata.get('ridge_height_m'):.3f} m"
        )
        self.model_generated.emit(model)

    def _on_clear(self) -> None:
        self._set_defaults()
        self.status_box.clear()
        self.status_box.setStyleSheet("")
        self.model_cleared.emit()

    def _show_errors(self, messages: list[str]) -> None:
        text = "Please fix the following:\n" + "\n".join(f"• {m}" for m in messages)
        self.status_box.setStyleSheet("color: #B71C1C;")
        self.status_box.setPlainText(text)
        QMessageBox.warning(self, "Invalid geometry input", text)
