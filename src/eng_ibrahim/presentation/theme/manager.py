from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from ...domain.enums import ThemeMode
from ..fonts import resolve_ui_family
from .tokens import DARK, LIGHT

FONT_FAMILIES = ["Noto Sans Arabic", "Segoe UI", "Tahoma", "Inter", "Arial"]

_QSS = """
* {{ font-size: 10pt; }}
QMainWindow, QDialog, QWidget#pageRoot {{ background: {bg}; color: {text}; }}
QWidget {{ color: {text}; }}
QLabel {{ background: transparent; }}
QFrame#header {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#sidebar {{ background: {sidebar}; }}
QFrame#sidebar QPushButton {{ color: {sidebar_text}; background: transparent; border: none;
    border-radius: 10px; padding: 10px 14px; text-align: {align}; min-height: 22px; }}
QFrame#sidebar QPushButton:hover {{ background: rgba(255,255,255,0.10); }}
QFrame#sidebar QPushButton:checked {{ background: {blue}; color: {on_primary}; font-weight: 600; }}
QFrame#sidebar QPushButton:focus {{ border: 2px solid {teal}; }}
QFrame#card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QLabel#pageTitle {{ font-size: 18pt; font-weight: 700; color: {text}; }}
QLabel#hint, QLabel#statusText {{ color: {text2}; }}
QLabel#brandTitle {{ font-size: 13pt; font-weight: 700; color: {text}; }}
QLabel#brandSub {{ color: {text2}; font-size: 9pt; }}
QPushButton, QToolButton {{ min-height: 30px; padding: 4px 14px; border-radius: 8px;
    border: 1px solid {border}; background: {surface}; color: {text}; }}
QPushButton:hover, QToolButton:hover {{ border-color: {blue}; }}
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {blue}; }}
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled {{ color: {text2}; background: {bg}; }}
QPushButton#primary {{ background: {blue}; color: {on_primary}; border: 1px solid {blue}; font-weight: 600; }}
QLineEdit, QComboBox {{ min-height: 30px; padding: 2px 8px; border: 1px solid {border};
    border-radius: 8px; background: {surface}; color: {text}; }}
QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {blue}; }}
QStatusBar {{ background: {surface}; border-top: 1px solid {border}; color: {text2}; }}
QStatusBar QLabel {{ color: {text2}; padding: 0 8px; }}
QLabel#dbOk {{ color: {success}; font-weight: 600; }}
QLabel#dbBad {{ color: {danger}; font-weight: 600; }}
QCheckBox {{ spacing: 8px; }}
QToolTip {{ background: {navy}; color: #fff; border: 1px solid {border}; padding: 4px; }}
QTableWidget, QTableView, QTreeView, QListWidget, QPlainTextEdit, QTextEdit {{
    background: {surface}; color: {text}; alternate-background-color: {bg};
    gridline-color: {border}; border: 1px solid {border}; border-radius: 10px;
    selection-background-color: {blue}; selection-color: {on_primary};
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QHeaderView {{ background: {bg}; }}
QHeaderView::section {{ background: {bg}; color: {text2}; border: none;
    border-bottom: 1px solid {border}; padding: 6px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {bg}; border: none; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; background: {surface}; }}
QTabBar::tab {{ background: transparent; color: {text2}; padding: 6px 14px; margin: 2px; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {blue}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {text}; }}
QSplitter::handle {{ background: {border}; }}
QCalendarWidget QWidget {{ background: {surface}; color: {text}; }}
QScrollBar:vertical {{ background: {bg}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 6px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def build_palette(mode: ThemeMode) -> QPalette:
    """A full palette so unstyled areas (table viewports, menus) follow the theme too."""
    t = DARK if mode is ThemeMode.DARK else LIGHT
    palette = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"),
                      (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "bg"),
                      (QPalette.ColorRole.Text, "text"),
                      (QPalette.ColorRole.Button, "surface"),
                      (QPalette.ColorRole.ButtonText, "text"),
                      (QPalette.ColorRole.ToolTipBase, "navy"),
                      (QPalette.ColorRole.ToolTipText, "on_primary"),
                      (QPalette.ColorRole.PlaceholderText, "text2"),
                      (QPalette.ColorRole.Highlight, "blue"),
                      (QPalette.ColorRole.HighlightedText, "on_primary"),
                      (QPalette.ColorRole.Mid, "border"),
                      (QPalette.ColorRole.Midlight, "border"),
                      (QPalette.ColorRole.Dark, "navy"),
                      (QPalette.ColorRole.Light, "surface")):
        palette.setColor(role, QColor(t[key]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["text2"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,
                     QColor(t["text2"]))
    return palette


def build_qss(mode: ThemeMode, rtl: bool = False) -> str:
    tokens = DARK if mode is ThemeMode.DARK else LIGHT
    return _QSS.format(align="right" if rtl else "left", **tokens)


def resolve_mode(mode: ThemeMode) -> ThemeMode:
    if mode is ThemeMode.SYSTEM:
        scheme = QGuiApplication.styleHints().colorScheme()
        return ThemeMode.DARK if scheme == Qt.ColorScheme.Dark else ThemeMode.LIGHT
    return mode


class ThemeManager:
    def __init__(self, app: QApplication, mode: ThemeMode = ThemeMode.LIGHT) -> None:
        self.app = app
        self.mode = mode
        self.rtl = False
        self.effective = resolve_mode(mode)

    def apply(self, mode: ThemeMode | None = None) -> ThemeMode:
        if mode is not None:
            self.mode = mode
        self.effective = resolve_mode(self.mode)
        font = QFont()
        family = resolve_ui_family()
        if family:
            font.setFamilies([family])
        else:  # keep the list as a hint for platforms with lazy font enumeration
            font.setFamilies(FONT_FAMILIES)
        font.setPointSize(10)
        self.app.setFont(font)
        self.app.setPalette(build_palette(self.effective))
        self.app.setStyleSheet(build_qss(self.effective, self.rtl))
        return self.effective
