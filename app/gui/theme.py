"""Shared monochrome design system for the desktop workspace."""
from pathlib import Path
from typing import Literal

ThemeName = Literal["light", "dark"]


def _stylesheet(dark: bool) -> str:
    colors = {
        "canvas": "#101010" if dark else "#F5F5F5",
        "surface": "#191919" if dark else "#FFFFFF",
        "field": "#202020" if dark else "#FFFFFF",
        "ink": "#F2F2F2" if dark else "#191919",
        "muted": "#A0A0A0" if dark else "#707070",
        "line": "#353535" if dark else "#E1E1E1",
        "hover": "#2B2B2B" if dark else "#F0F0F0",
        "disabled": "#777777" if dark else "#999999",
        "assets": (Path(__file__).parent / "assets").as_posix(),
        "variant": "light" if dark else "dark",
    }
    sheet = """
QWidget { color: @ink; background: @canvas; font-family: "Segoe UI", sans-serif; font-size: 12px; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QLabel#panelTitle { font-size: 16px; font-weight: 600; }
QLabel#workspaceTitle { font-size: 23px; font-weight: 600; }
QLabel#panelHint, QLabel#sectionCaption { color: @muted; }
QLabel#eyebrow { color: @muted; font-size: 10px; font-weight: 600; letter-spacing: 1px; }
QLabel#modelBadge { color: @muted; background: @surface; border: 1px solid @line; border-radius: 5px; padding: 6px 10px; }
QWidget#inputPanel, QWidget#inputHeader, QWidget#inputBody, QWidget#actionFooter { background: @surface; }
QWidget#inputHeader { border-bottom: 1px solid @line; }
QWidget#actionFooter { border-top: 1px solid @line; }
QMenuBar { background: @surface; border-bottom: 1px solid @line; padding: 2px 12px; }
QMenuBar::item { background: transparent; padding: 5px 10px; }
QMenuBar::item:selected { background: @hover; border-radius: 4px; }
QMenu { background: @surface; border: 1px solid @line; padding: 6px; }
QMenu::item { padding: 8px 26px 8px 12px; border-radius: 4px; }
QMenu::item:selected { background: @ink; color: @surface; }
QMenu::separator { height: 1px; background: @line; margin: 5px 8px; }
QToolBar { background: @surface; border-bottom: 1px solid @line; spacing: 8px; padding: 8px 16px; }
QToolBar::separator { background: @line; width: 1px; margin: 6px 8px; }
QWidget#toolbarSpacer { background: transparent; }
QPushButton, QToolButton { background: @surface; color: @ink; border: 1px solid @line; border-radius: 5px; padding: 7px 12px; font-weight: 600; }
QPushButton:hover, QToolButton:hover { background: @hover; border-color: @muted; }
QPushButton:pressed, QToolButton:pressed { background: @line; }
QPushButton:focus, QToolButton:focus { border-color: @ink; }
QPushButton#primaryButton, QPushButton#accentButton { background: @ink; color: @surface; border-color: @ink; }
QPushButton#primaryButton:hover, QPushButton#accentButton:hover { background: @muted; border-color: @muted; }
QPushButton:disabled, QToolButton:disabled { color: @disabled; background: @canvas; border-color: @line; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: @field; color: @ink; border: 1px solid @line; border-radius: 5px; padding: 6px 10px; min-height: 20px; selection-background-color: @ink; selection-color: @surface; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: @muted; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: @ink; }
QLineEdit:disabled, QComboBox:disabled, QLineEdit[readOnly="true"] { color: @disabled; background: @canvas; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none; }
QComboBox::down-arrow { image: url(@assets/chevron-down-@variant.svg); width: 12px; height: 12px; }
QComboBox QLineEdit { border: none; padding: 0; min-height: 20px; background: transparent; }
QComboBox QAbstractItemView { background: @surface; color: @ink; border: 1px solid @line; padding: 4px; outline: none; selection-background-color: @ink; selection-color: @surface; }
QComboBox QAbstractItemView::item { min-height: 28px; padding: 4px 8px; }
QCheckBox { spacing: 8px; min-height: 24px; }
QCheckBox:disabled { color: @disabled; }
QCheckBox::indicator { width: 30px; height: 18px; image: url(@assets/switch-off.svg); }
QCheckBox::indicator:checked { image: url(@assets/switch-on-@variant.svg); }
QCheckBox::indicator:disabled { image: url(@assets/switch-off.svg); }
QCheckBox:focus { color: @ink; }
QGroupBox { background: @surface; border: 1px solid @line; border-radius: 7px; margin-top: 13px; padding: 14px 10px 10px; font-size: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px; background: @surface; }
QGroupBox::indicator { width: 12px; height: 12px; image: url(@assets/chevron-right-@variant.svg); }
QGroupBox::indicator:checked { image: url(@assets/chevron-down-@variant.svg); }
QGroupBox QWidget { background: transparent; }
QGroupBox QLineEdit, QGroupBox QComboBox { background: @field; }
QGroupBox QLineEdit:disabled, QGroupBox QLineEdit[readOnly="true"] { background: @canvas; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: @surface; }
QTextEdit, QPlainTextEdit, QListWidget, QTableView { background: @surface; color: @ink; border: 1px solid @line; border-radius: 5px; padding: 10px; selection-background-color: @ink; selection-color: @surface; }
QTextEdit#staadEditor { font-family: "Cascadia Code", "Consolas", monospace; font-size: 12px; }
QTabWidget::pane { background: @surface; border: 1px solid @line; border-radius: 5px; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab { color: @muted; background: transparent; padding: 11px 18px; border-bottom: 2px solid transparent; margin-right: 4px; }
QTabBar::tab:hover { color: @ink; background: @hover; }
QTabBar::tab:selected { color: @ink; border-bottom: 2px solid @ink; font-weight: 600; }
QWidget#viewerControls { background: @surface; border: 1px solid @line; border-radius: 5px; }
QStatusBar { background: @surface; color: @muted; border-top: 1px solid @line; padding: 3px 8px; font-size: 11px; }
QStatusBar::item { border: none; }
QSplitter::handle { background: @canvas; }
QSplitter::handle:hover { background: @line; }
QDialog { background: @canvas; }
QToolTip { color: @ink; background: @surface; border: 1px solid @line; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle { background: @line; border-radius: 2px; min-height: 28px; min-width: 28px; }
QScrollBar::handle:hover { background: @muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""
    for key, value in colors.items():
        sheet = sheet.replace(f"@{key}", value)
    return sheet


LIGHT_STYLE = _stylesheet(False)
DARK_STYLE = _stylesheet(True)


def stylesheet_for(theme: ThemeName) -> str:
    return DARK_STYLE if theme == "dark" else LIGHT_STYLE


def normalize_theme(value: object) -> ThemeName:
    raw = str(value or "light").strip().lower()
    return "dark" if raw.startswith("dark") else "light"
