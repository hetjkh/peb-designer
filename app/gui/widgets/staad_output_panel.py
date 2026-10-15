"""STAAD input text output panel."""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StaadOutputPanel(QWidget):
    """Shows generated STAAD.Pro input and copy/save/clear actions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("GENERATED FILE  /  .STD")
        title.setObjectName("eyebrow")
        header.addWidget(title)
        header.addStretch(1)

        self.create_btn = QPushButton("Create STD File")
        self.create_btn.setObjectName("accentButton")
        self.copy_btn = QPushButton("Copy Output")
        self.clear_btn = QPushButton("Clear Output")
        header.addWidget(self.create_btn)
        header.addWidget(self.clear_btn)
        header.addWidget(self.copy_btn)
        root.addLayout(header)

        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText(
            "STAAD input will appear here after generation…"
        )
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setObjectName("staadEditor")
        root.addWidget(self.editor)

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()

    def clear(self) -> None:
        self.editor.clear()
