"""EXTENSIONS + EOT Crane — STAGen-style Left/Right toggles."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.geometry.peb_frame import (
    BuildingExtensions,
    CraneInput,
    RoofMonitorInput,
    SideCanopy,
    SideFascia,
    SideLeanTo,
    SideRoofExtension,
)


def _link_btn(text: str, *, danger: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setFlat(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    color = "#E25555" if danger else "#4C8DFF"
    btn.setStyleSheet(f"color: {color}; border: none; font-weight: 600; padding: 2px 6px;")
    return btn


def _lab(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("sectionCaption")
    lab.setWordWrap(True)
    return lab


def _edit(text: str = "", placeholder: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumWidth(0)
    e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if placeholder:
        e.setPlaceholderText(placeholder)
    return e


class SideToggleRow(QWidget):
    """Label + +Left/+Right (or -Left/-Right when active) with optional body."""

    changed = Signal()

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._left_on = False
        self._right_on = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        head = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-weight: 600;")
        head.addWidget(name)
        head.addStretch(1)
        self.left_btn = _link_btn("+ Left")
        self.right_btn = _link_btn("+ Right")
        head.addWidget(self.left_btn)
        head.addWidget(self.right_btn)
        root.addLayout(head)

        self.left_body = QWidget()
        self.right_body = QWidget()
        self.left_body.setVisible(False)
        self.right_body.setVisible(False)
        root.addWidget(self.left_body)
        root.addWidget(self.right_body)

        self.left_btn.clicked.connect(lambda: self._toggle("left"))
        self.right_btn.clicked.connect(lambda: self._toggle("right"))

    def _toggle(self, side: str) -> None:
        if side == "left":
            self._left_on = not self._left_on
            self.left_body.setVisible(self._left_on)
            self.left_btn.setText("− Left" if self._left_on else "+ Left")
            self.left_btn.setStyleSheet(
                f"color: {'#E25555' if self._left_on else '#4C8DFF'}; "
                "border: none; font-weight: 600; padding: 2px 6px;"
            )
        else:
            self._right_on = not self._right_on
            self.right_body.setVisible(self._right_on)
            self.right_btn.setText("− Right" if self._right_on else "+ Right")
            self.right_btn.setStyleSheet(
                f"color: {'#E25555' if self._right_on else '#4C8DFF'}; "
                "border: none; font-weight: 600; padding: 2px 6px;"
            )
        self.changed.emit()

    def set_side(self, side: str, on: bool) -> None:
        cur = self._left_on if side == "left" else self._right_on
        if cur != on:
            self._toggle(side)

    def left_on(self) -> bool:
        return self._left_on

    def right_on(self) -> bool:
        return self._right_on

    def clear_sides(self) -> None:
        if self._left_on:
            self._toggle("left")
        if self._right_on:
            self._toggle("right")


class ExtensionsSection(QWidget):
    """Lean-To, Roof Extension, Fascia, Canopy, Roof Monitor."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ---- Lean-To ----
        self.lean = SideToggleRow("Lean-To")
        self._build_lean_body(self.lean.left_body, "L")
        self._build_lean_body(self.lean.right_body, "R")
        root.addWidget(self.lean)

        # ---- Roof Extension ----
        self.roof_ext = SideToggleRow("Roof Extension")
        self._build_roof_ext_body(self.roof_ext.left_body, "L")
        self._build_roof_ext_body(self.roof_ext.right_body, "R")
        root.addWidget(self.roof_ext)

        # ---- Fascia ----
        self.fascia = SideToggleRow("Fascia")
        self._build_fascia_body(self.fascia.left_body, "L")
        self._build_fascia_body(self.fascia.right_body, "R")
        root.addWidget(self.fascia)

        # ---- Canopy ----
        self.canopy = SideToggleRow("Canopy")
        self._build_canopy_body(self.canopy.left_body, "L")
        self._build_canopy_body(self.canopy.right_body, "R")
        root.addWidget(self.canopy)

        # ---- Roof Monitor ----
        mon_head = QHBoxLayout()
        mon_lab = QLabel("Roof Monitor")
        mon_lab.setStyleSheet("font-weight: 600;")
        mon_head.addWidget(mon_lab)
        mon_head.addStretch(1)
        self.monitor_btn = _link_btn("+ Add")
        mon_head.addWidget(self.monitor_btn)
        root.addLayout(mon_head)

        self._monitor_body = QWidget()
        self._monitor_body.setVisible(False)
        self._monitor_on = False
        mg = QGridLayout(self._monitor_body)
        mg.setContentsMargins(4, 0, 0, 0)
        mg.setHorizontalSpacing(6)
        self.throat_edit = _edit("3")
        self.monitor_height_edit = _edit("1.5")
        self.extension_edit = _edit("0.75")
        mg.addWidget(_lab("Throat Width (m)"), 0, 0)
        mg.addWidget(_lab("Height (m)"), 0, 1)
        mg.addWidget(_lab("Extension (m)"), 0, 2)
        mg.addWidget(self.throat_edit, 1, 0)
        mg.addWidget(self.monitor_height_edit, 1, 1)
        mg.addWidget(self.extension_edit, 1, 2)
        root.addWidget(self._monitor_body)

        self.monitor_btn.clicked.connect(self._toggle_monitor)
        for row in (self.lean, self.roof_ext, self.fascia, self.canopy):
            row.changed.connect(self.changed.emit)
        for e in (self.throat_edit, self.monitor_height_edit, self.extension_edit):
            e.textChanged.connect(lambda _t: self.changed.emit())
        self._wire_field_changes()

    def _wire_field_changes(self) -> None:
        for w in self.findChildren(QLineEdit):
            w.textChanged.connect(lambda _t: self.changed.emit())
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(lambda _i: self.changed.emit())
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(lambda _c: self.changed.emit())

    def _build_lean_body(self, host: QWidget, prefix: str) -> None:
        g = QGridLayout(host)
        g.setContentsMargins(4, 0, 0, 0)
        g.setHorizontalSpacing(6)
        width = _edit("5")
        slope = _edit("1")
        conn = _edit("", placeholder="blank=eave")
        base = QComboBox()
        base.addItem("Pinned", "pinned")
        base.addItem("Fixed", "fixed")
        g.addWidget(_lab(f"{prefix} Width (m)"), 0, 0)
        g.addWidget(_lab(f"{prefix} Slope (:10)"), 0, 1)
        g.addWidget(_lab(f"{prefix} Conn. Ht"), 0, 2)
        g.addWidget(_lab(f"{prefix} Base"), 0, 3)
        g.addWidget(width, 1, 0)
        g.addWidget(slope, 1, 1)
        g.addWidget(conn, 1, 2)
        g.addWidget(base, 1, 3)
        host._width = width  # type: ignore[attr-defined]
        host._slope = slope  # type: ignore[attr-defined]
        host._conn = conn  # type: ignore[attr-defined]
        host._base = base  # type: ignore[attr-defined]

    def _build_roof_ext_body(self, host: QWidget, prefix: str) -> None:
        lay = QHBoxLayout(host)
        lay.setContentsMargins(4, 0, 0, 0)
        proj = _edit("0.8")
        lay.addWidget(_lab(f"{prefix} Proj (m)"))
        lay.addWidget(proj, 1)
        host._proj = proj  # type: ignore[attr-defined]

    def _build_fascia_body(self, host: QWidget, prefix: str) -> None:
        lay = QHBoxLayout(host)
        lay.setContentsMargins(4, 0, 0, 0)
        ht = _edit("1.25")
        cover = QCheckBox("Cover Ridge")
        lay.addWidget(_lab(f"{prefix} Height (m)"))
        lay.addWidget(ht, 1)
        lay.addWidget(cover)
        host._height = ht  # type: ignore[attr-defined]
        host._cover = cover  # type: ignore[attr-defined]

    def _build_canopy_body(self, host: QWidget, prefix: str) -> None:
        g = QGridLayout(host)
        g.setContentsMargins(4, 0, 0, 0)
        g.setHorizontalSpacing(6)
        width = _edit("3")
        ht = _edit("3")
        slope = _edit("1")
        g.addWidget(_lab(f"{prefix} Width (m)"), 0, 0)
        g.addWidget(_lab(f"{prefix} Ht on Col"), 0, 1)
        g.addWidget(_lab(f"{prefix} Slope (:10)"), 0, 2)
        g.addWidget(width, 1, 0)
        g.addWidget(ht, 1, 1)
        g.addWidget(slope, 1, 2)
        host._width = width  # type: ignore[attr-defined]
        host._ht = ht  # type: ignore[attr-defined]
        host._slope = slope  # type: ignore[attr-defined]

    def _toggle_monitor(self) -> None:
        self._monitor_on = not self._monitor_on
        self._monitor_body.setVisible(self._monitor_on)
        self.monitor_btn.setText("− Remove" if self._monitor_on else "+ Add")
        self.monitor_btn.setStyleSheet(
            f"color: {'#E25555' if self._monitor_on else '#4C8DFF'}; "
            "border: none; font-weight: 600; padding: 2px 6px;"
        )
        self.changed.emit()

    def _read_lean(self, host: QWidget, on: bool) -> SideLeanTo:
        if not on:
            return SideLeanTo(enabled=False)
        conn_txt = host._conn.text().strip()  # type: ignore[attr-defined]
        conn = float(conn_txt) if conn_txt else None
        return SideLeanTo(
            enabled=True,
            width_m=float(host._width.text() or 0),  # type: ignore[attr-defined]
            slope_x10=float(host._slope.text() or 1),  # type: ignore[attr-defined]
            conn_height_m=conn,
            base=str(host._base.currentData() or "pinned"),  # type: ignore[attr-defined]
        )

    def _read_roof_ext(self, host: QWidget, on: bool) -> SideRoofExtension:
        if not on:
            return SideRoofExtension(enabled=False)
        return SideRoofExtension(
            enabled=True,
            projection_m=float(host._proj.text() or 0),  # type: ignore[attr-defined]
        )

    def _read_fascia(self, host: QWidget, on: bool) -> SideFascia:
        if not on:
            return SideFascia(enabled=False)
        return SideFascia(
            enabled=True,
            height_m=float(host._height.text() or 0),  # type: ignore[attr-defined]
            cover_ridge=host._cover.isChecked(),  # type: ignore[attr-defined]
        )

    def _read_canopy(self, host: QWidget, on: bool) -> SideCanopy:
        if not on:
            return SideCanopy(enabled=False)
        return SideCanopy(
            enabled=True,
            width_m=float(host._width.text() or 0),  # type: ignore[attr-defined]
            height_on_col_m=float(host._ht.text() or 0),  # type: ignore[attr-defined]
            slope_x10=float(host._slope.text() or 1),  # type: ignore[attr-defined]
        )

    def read_extensions(self) -> BuildingExtensions:
        mon = RoofMonitorInput(enabled=False)
        if self._monitor_on:
            mon = RoofMonitorInput(
                enabled=True,
                throat_width_m=float(self.throat_edit.text() or 0),
                height_m=float(self.monitor_height_edit.text() or 0),
                extension_m=float(self.extension_edit.text() or 0),
            )
        return BuildingExtensions(
            lean_to_left=self._read_lean(self.lean.left_body, self.lean.left_on()),
            lean_to_right=self._read_lean(self.lean.right_body, self.lean.right_on()),
            roof_ext_left=self._read_roof_ext(
                self.roof_ext.left_body, self.roof_ext.left_on()
            ),
            roof_ext_right=self._read_roof_ext(
                self.roof_ext.right_body, self.roof_ext.right_on()
            ),
            fascia_left=self._read_fascia(self.fascia.left_body, self.fascia.left_on()),
            fascia_right=self._read_fascia(
                self.fascia.right_body, self.fascia.right_on()
            ),
            canopy_left=self._read_canopy(self.canopy.left_body, self.canopy.left_on()),
            canopy_right=self._read_canopy(
                self.canopy.right_body, self.canopy.right_on()
            ),
            roof_monitor=mon,
        )

    def read_monitor(self) -> RoofMonitorInput:
        return self.read_extensions().roof_monitor

    def clear(self) -> None:
        self.lean.clear_sides()
        self.roof_ext.clear_sides()
        self.fascia.clear_sides()
        self.canopy.clear_sides()
        if self._monitor_on:
            self._toggle_monitor()


class CraneSection(QWidget):
    """EOT Crane Data — yellow runway in 2D with animated trolley."""

    changed = Signal()

    MANUFACTURERS = (
        "Konecranes",
        "ABUS",
        "DEMAG",
        "Electromech",
        "Custom",
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.addStretch(1)
        self.add_btn = _link_btn("+ Add Crane")
        head.addWidget(self.add_btn)
        root.addLayout(head)

        self._card = QGroupBox("Crane #1")
        self._card.setVisible(False)
        cf = QFormLayout(self._card)

        self.mfr = QComboBox()
        for name in self.MANUFACTURERS:
            self.mfr.addItem(name, name)

        self.name_edit = QLineEdit("Crane 1")
        self.hook_edit = QLineEdit("4.5")
        self.capacity_edit = QLineEdit("50")
        self.bridge_edit = QLineEdit("0")
        self.trolley_edit = QLineEdit("0")
        self.wheels_edit = QLineEdit("2")
        self.span_edit = QLineEdit("1")

        self.remove_btn = QPushButton("Remove Crane")
        self.remove_btn.setStyleSheet("color: #E25555;")

        cf.addRow("Manufacturer", self.mfr)
        cf.addRow("Name", self.name_edit)
        cf.addRow("Hook Ht. (m)", self.hook_edit)
        cf.addRow("Cap. (kN)", self.capacity_edit)
        cf.addRow("Bridge (kN)", self.bridge_edit)
        cf.addRow("Trolley (kN)", self.trolley_edit)
        cf.addRow("Wheels/End", self.wheels_edit)
        cf.addRow("Span #", self.span_edit)
        cf.addRow(self.remove_btn)

        self.clearance_warn = QLabel("")
        self.clearance_warn.setObjectName("panelHint")
        self.clearance_warn.setWordWrap(True)
        self.clearance_warn.setStyleSheet("color: #E8913A;")
        self.clearance_warn.setVisible(False)

        root.addWidget(self._card)
        root.addWidget(self.clearance_warn)

        self._crane_active = False

        self.add_btn.clicked.connect(self._add_crane)
        self.remove_btn.clicked.connect(self.clear_crane)
        self.mfr.currentIndexChanged.connect(lambda _i: self.changed.emit())
        for e in (
            self.name_edit,
            self.hook_edit,
            self.capacity_edit,
            self.bridge_edit,
            self.trolley_edit,
            self.wheels_edit,
            self.span_edit,
        ):
            e.textChanged.connect(lambda _t: self.changed.emit())

    def _add_crane(self) -> None:
        self._crane_active = True
        self._card.setVisible(True)
        self.add_btn.setVisible(False)
        self.changed.emit()

    def clear_crane(self) -> None:
        self._crane_active = False
        self._card.setVisible(False)
        self.add_btn.setVisible(True)
        self.clearance_warn.setVisible(False)
        self.hook_edit.setText("4.5")
        self.capacity_edit.setText("50")
        self.name_edit.setText("Crane 1")
        self.changed.emit()

    def has_crane(self) -> bool:
        return self._crane_active

    def read_crane(self) -> CraneInput:
        if not self.has_crane():
            return CraneInput(enabled=False)
        hook = float(self.hook_edit.text() or 0)
        return CraneInput(
            enabled=True,
            name=self.name_edit.text().strip() or "Crane 1",
            manufacturer=str(self.mfr.currentData() or "Konecranes"),
            capacity_kn=float(self.capacity_edit.text() or 0),
            hook_height_m=hook,
            runway_height_m=hook,
            bridge_kn=float(self.bridge_edit.text() or 0),
            trolley_kn=float(self.trolley_edit.text() or 0),
            wheels_per_end=int(float(self.wheels_edit.text() or 2)),
            span_index=int(float(self.span_edit.text() or 1)),
        )

    def set_crane(self, crane: CraneInput) -> None:
        if not crane.enabled:
            self.clear_crane()
            return
        self._add_crane()
        idx = self.mfr.findData(crane.manufacturer)
        if idx >= 0:
            self.mfr.setCurrentIndex(idx)
        self.name_edit.setText(crane.name)
        h = crane.effective_height_m or crane.hook_height_m or 4.5
        self.hook_edit.setText(f"{h:g}")
        self.capacity_edit.setText(f"{crane.capacity_kn:g}")
        self.bridge_edit.setText(f"{crane.bridge_kn:g}")
        self.trolley_edit.setText(f"{crane.trolley_kn:g}")
        self.wheels_edit.setText(str(crane.wheels_per_end))
        self.span_edit.setText(str(crane.span_index))

    def set_legacy(
        self,
        *,
        enabled: bool,
        name: str,
        capacity_kn: float,
        runway_height_m: float,
    ) -> None:
        if not enabled:
            self.clear_crane()
            return
        self.set_crane(
            CraneInput(
                enabled=True,
                name=name,
                capacity_kn=capacity_kn,
                hook_height_m=runway_height_m,
                runway_height_m=runway_height_m,
            )
        )

    def update_clearance_warning(
        self, *, mezz_height_m: float = 0.0, min_headroom_m: float = 2.0
    ) -> None:
        if not self.has_crane() or mezz_height_m <= 0:
            self.clearance_warn.setVisible(False)
            return
        hook = float(self.hook_edit.text() or 0)
        clearance = hook - mezz_height_m
        if clearance < min_headroom_m:
            self.clearance_warn.setText(
                f"⚠ Crane passes {clearance:.2f} m above the mezzanine — "
                f"need ≥ {min_headroom_m:g} m headroom. Raise the crane or lower the floor."
            )
            self.clearance_warn.setVisible(True)
        else:
            self.clearance_warn.setVisible(False)
