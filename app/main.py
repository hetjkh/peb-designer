"""Application entry point."""

from __future__ import annotations

import os
import sys

# Ensure PyVistaQt binds to PySide6 (not PyQt).
os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from app.gui.main_window import MainWindow


def _apply_light_palette(app: QApplication) -> None:
    """Force a light UI palette so Windows dark mode cannot hide labels."""
    app.setStyle(QStyleFactory.create("Fusion"))

    palette = QPalette()
    window = QColor("#F5F5F5")
    base = QColor("#FFFFFF")
    text = QColor("#191919")
    disabled = QColor("#999999")
    highlight = QColor("#191919")
    button = QColor("#FAFAFA")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#EEEEEE"))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#888888"))

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.WindowText, text)
        palette.setColor(group, QPalette.ColorRole.Text, text)
        palette.setColor(group, QPalette.ColorRole.ButtonText, text)

    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled
    )
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled
    )

    app.setPalette(palette)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PEB Designer")
    app.setOrganizationName("PEB Designer")
    _apply_light_palette(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
