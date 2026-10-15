"""Mezzanine section UI — multi-level cards matching STAGen-style inputs."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.geometry.peb_frame import MezzanineInput, MezzanineLevel
from app.geometry.spacing import parse_spacing_list, spacing_total


class MezzLevelCard(QFrame):
    """One mezzanine level editor card."""

    remove_requested = Signal(object)  # self

    def __init__(
        self,
        level_index: int,
        parent: Optional[QWidget] = None,
        *,
        level: Optional[MezzanineLevel] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mezzLevelCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._index = level_index
        lv = level or MezzanineLevel()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel(f"Level {level_index}")
        self.title.setStyleSheet("color: #4C8DFF; font-weight: 600;")
        head.addWidget(self.title)
        head.addStretch(1)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedWidth(28)
        self.remove_btn.setToolTip("Remove this level")
        self.remove_btn.setStyleSheet("color: #E25555; border: none; font-weight: 700;")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        head.addWidget(self.remove_btn)
        root.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def _lab(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setObjectName("sectionCaption")
            lab.setWordWrap(True)
            return lab

        def _edit(text: str) -> QLineEdit:
            e = QLineEdit(text)
            e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            e.setMinimumWidth(0)
            return e

        self.height_edit = _edit(f"{lv.height_m:g}")
        self.start_edit = _edit(f"{lv.start_m:g}")
        self.width_edit = _edit(f"{lv.width_m:g}")
        sp_txt = "+".join(f"{s:g}" for s in lv.col_spacings_m) if lv.col_spacings_m else "3@5"
        # Prefer compact N@V when uniform
        if lv.col_spacings_m and len(set(lv.col_spacings_m)) == 1:
            sp_txt = f"{len(lv.col_spacings_m)}@{lv.col_spacings_m[0]:g}"
        self.col_sp_edit = _edit(sp_txt)
        self.joist_edit = _edit(f"{lv.joist_spacing_m:g}")

        self.dead_edit = _edit(f"{lv.dead_kn_m2:g}")
        self.coll_edit = _edit(f"{lv.collateral_kn_m2:g}")
        self.live_edit = _edit(f"{lv.live_kn_m2:g}")
        self.blockwall_edit = _edit(f"{lv.blockwall_kn_m:g}")

        # 2-column layout so the sidebar does not clip fields
        pairs = [
            ("Height (m)", self.height_edit),
            ("Start (m)", self.start_edit),
            ("Width (m)", self.width_edit),
            ("Col. Sp. (m)", self.col_sp_edit),
            ("Joist Sp. (m)", self.joist_edit),
            ("Floor Dead (kN/m²)", self.dead_edit),
            ("Floor Coll.", self.coll_edit),
            ("Floor Live (kN/m²)", self.live_edit),
            ("Blockwall (kN/m)", self.blockwall_edit),
        ]
        for i, (label, edit) in enumerate(pairs):
            row, col = divmod(i, 2)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(_lab(label))
            cell.addWidget(edit)
            grid.addLayout(cell, row, col)

        root.addLayout(grid)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setMinimumWidth(0)

    def set_level_index(self, index: int) -> None:
        self._index = index
        self.title.setText(f"Level {index}")

    def read_level(self) -> MezzanineLevel:
        spacings = parse_spacing_list(
            self.col_sp_edit.text(), field_name="Mezz column spacing"
        )
        width = float(self.width_edit.text() or 0)
        # If width blank/zero, derive from spacings
        if width <= 0 and spacings:
            width = spacing_total(spacings)
            self.width_edit.setText(f"{width:g}")
        return MezzanineLevel(
            height_m=float(self.height_edit.text() or 0),
            start_m=float(self.start_edit.text() or 0),
            width_m=width,
            col_spacings_m=tuple(spacings),
            joist_spacing_m=float(self.joist_edit.text() or 0),
            dead_kn_m2=float(self.dead_edit.text() or 0),
            collateral_kn_m2=float(self.coll_edit.text() or 0),
            live_kn_m2=float(self.live_edit.text() or 0),
            blockwall_kn_m=float(self.blockwall_edit.text() or 0),
        )


class MezzanineSection(QWidget):
    """Full MEZZANINE group: add/remove levels, connection, flat-roof mode."""

    changed = Signal()
    flat_roof_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.addStretch(1)
        self.add_btn = QPushButton("+ Add Level")
        self.add_btn.setFlat(True)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet("color: #4C8DFF; border: none; font-weight: 600;")
        self.remove_all_btn = QPushButton("− Remove Mezzanine")
        self.remove_all_btn.setFlat(True)
        self.remove_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_all_btn.setStyleSheet("color: #E25555; border: none; font-weight: 600;")
        head.addWidget(self.add_btn)
        head.addWidget(self.remove_all_btn)
        root.addLayout(head)

        opts = QHBoxLayout()
        self.connection = QComboBox()
        self.connection.addItem("Pinned", "pinned")
        self.connection.addItem("Fixed", "fixed")
        self.connection.setMinimumWidth(0)
        self.connection.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.connection.setToolTip("Mezzanine column base connection")
        opts.addWidget(self.connection)
        self.flat_roof = QCheckBox("Flat Roof (Mezz Only)")
        self.flat_roof.setToolTip(
            "Flat (zero-slope) roof with mezzanine floors only — no sloped roof. "
            "Greys out Roof Slope, Purlin, Girt, Eave Height, Frame Type and Roof Loads."
        )
        opts.addWidget(self.flat_roof)
        opts.addStretch(1)
        root.addLayout(opts)

        self.levels_host = QVBoxLayout()
        self.levels_host.setSpacing(8)
        root.addLayout(self.levels_host)

        self._cards: List[MezzLevelCard] = []

        self.add_btn.clicked.connect(self._on_add_level)
        self.remove_all_btn.clicked.connect(self.clear_mezzanine)
        self.flat_roof.toggled.connect(self._on_flat_toggled)
        self.connection.currentIndexChanged.connect(lambda _i: self.changed.emit())

    def _on_flat_toggled(self, checked: bool) -> None:
        if checked and not self._cards:
            self._on_add_level()
        self.flat_roof_toggled.emit(checked)
        self.changed.emit()

    def _on_add_level(self) -> None:
        idx = len(self._cards) + 1
        default = MezzanineLevel(
            height_m=3.5,
            start_m=0.0,
            width_m=15.0,
            col_spacings_m=(5.0, 5.0, 5.0),
            joist_spacing_m=1.5,
        )
        self._add_card(idx, default)
        self.changed.emit()

    def _add_card(self, index: int, level: MezzanineLevel) -> MezzLevelCard:
        card = MezzLevelCard(index, self, level=level)
        card.remove_requested.connect(self._on_remove_card)
        for edit in card.findChildren(QLineEdit):
            edit.textChanged.connect(lambda _text: self.changed.emit())
        self._cards.append(card)
        self.levels_host.addWidget(card)
        return card

    def _on_remove_card(self, card: MezzLevelCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
            self._renumber()
            if not self._cards:
                self.flat_roof.setChecked(False)
            self.changed.emit()

    def _renumber(self) -> None:
        for i, card in enumerate(self._cards, start=1):
            card.set_level_index(i)

    def clear_mezzanine(self) -> None:
        for card in list(self._cards):
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
        self.flat_roof.setChecked(False)
        self.changed.emit()

    def has_levels(self) -> bool:
        return bool(self._cards)

    def set_from_input(self, mz: MezzanineInput) -> None:
        self.clear_mezzanine()
        self.flat_roof.blockSignals(True)
        self.flat_roof.setChecked(mz.flat_roof_mezz_only)
        self.flat_roof.blockSignals(False)
        conn = (mz.connection_type or "pinned").lower()
        idx = self.connection.findData(conn)
        if idx >= 0:
            self.connection.setCurrentIndex(idx)
        levels = mz.resolved_levels() if mz.enabled else ()
        for i, lv in enumerate(levels, start=1):
            self._add_card(i, lv)
        self.flat_roof_toggled.emit(self.flat_roof.isChecked())

    def set_legacy(
        self,
        *,
        enabled: bool,
        width_m: float,
        height_m: float,
        col_spacing_m: float,
    ) -> None:
        self.clear_mezzanine()
        if not enabled:
            return
        n = max(1, int(round(width_m / col_spacing_m))) if col_spacing_m > 0 else 1
        spacings = tuple([col_spacing_m] * n) if col_spacing_m > 0 else (width_m,)
        self._add_card(
            1,
            MezzanineLevel(
                height_m=height_m,
                start_m=0.0,
                width_m=width_m,
                col_spacings_m=spacings,
            ),
        )

    def read_input(self) -> MezzanineInput:
        if not self._cards:
            return MezzanineInput(enabled=False)
        levels = []
        for card in self._cards:
            levels.append(card.read_level())
        primary = levels[0]
        return MezzanineInput(
            enabled=True,
            flat_roof_mezz_only=self.flat_roof.isChecked(),
            connection_type=str(self.connection.currentData() or "pinned"),
            levels=tuple(levels),
            width_m=primary.width_m,
            height_m=primary.height_m,
            col_spacing_m=primary.col_spacings_m[0] if primary.col_spacings_m else 0.0,
            dead_kn_m2=primary.dead_kn_m2,
            live_kn_m2=primary.live_kn_m2,
            collateral_kn_m2=primary.collateral_kn_m2,
        )
