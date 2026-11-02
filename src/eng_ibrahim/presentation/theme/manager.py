from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from ...config import project_root
from ...domain.enums import ThemeMode
from ..fonts import resolve_ui_family
from .tokens import DARK, LIGHT

FONT_FAMILIES = ["Cairo", "Noto Sans Arabic", "Segoe UI", "Tahoma", "Inter", "Arial"]

_QSS = """
* {{ font-size: 10pt; }}
QMainWindow, QDialog, QWidget#pageRoot {{ background: {bg}; color: {text}; }}
QWidget {{ color: {text}; }}
QLabel {{ background: transparent; }}
QFrame#header {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#sidebar, QScrollArea#sidebarScroll {{ background: {sidebar}; border: none; }}
QFrame#sidebar QPushButton {{ color: {sidebar_text}; background: transparent; border: none;
    border-radius: 8px; padding: 0; min-height: 38px; }}
QFrame#sidebar QLabel#navText {{ color: {sidebar_text}; }}
QFrame#sidebar QLabel#navText[active="true"] {{ color: {on_primary}; font-weight: 600; }}
QFrame#sidebar QPushButton:hover {{ background: rgba(255,255,255,0.08); }}
QFrame#sidebar QPushButton:checked {{ background: {blue}; color: {on_primary}; font-weight: 600; }}
QFrame#sidebar QPushButton:focus {{ border: 2px solid {teal}; }}
QScrollArea#sidebarScroll QScrollBar:vertical {{ background: {sidebar}; width: 6px; }}
QScrollArea#sidebarScroll QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.25); }}
QFrame#card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#kpiCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px;
    border-top: 4px solid {border}; }}
QFrame#kpiCard:hover, QFrame#kpiCard:focus {{ border-color: {blue}; }}
QFrame#kpiCard[tone="info"] {{ border-top-color: {blue}; }}
QFrame#kpiCard[tone="success"] {{ border-top-color: {success}; }}
QFrame#kpiCard[tone="warning"] {{ border-top-color: {warning}; }}
QFrame#kpiCard[tone="danger"] {{ border-top-color: {danger}; }}
QLabel#kpiValue {{ font-size: 22pt; font-weight: 700; color: {text}; }}
QLabel#kpiValue[tone="danger"] {{ color: {danger}; }}
QLabel#kpiValue[tone="warning"] {{ color: {warning}; }}
QLabel#kpiCaption {{ color: {text2}; }}
QLabel#sectionTitle {{ font-size: 11pt; font-weight: 600; color: {text}; }}
QLabel#fieldLabel {{ color: {text2}; }}
QLabel#emptyState {{ color: {text2}; font-size: 10.5pt; }}
QLabel#errorText {{ color: {danger}; font-weight: 600; }}
QScrollArea#pageScroll {{ background: {bg}; border: none; }}
QScrollArea#plainScroll, QWidget#scrollContent {{ background: transparent; border: none; }}
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
QPushButton#primary:hover {{ background: {teal}; border-color: {teal}; }}
QPushButton#primary:disabled {{ background: {border}; border-color: {border}; color: {text2}; }}
QToolButton#headerIcon {{ min-height: 0; min-width: 0; padding: 7px; border: none;
    border-radius: 8px; background: transparent; }}
QToolButton#headerIcon:hover {{ background: {bg}; }}
QLineEdit#headerSearch {{ background: {bg}; border-color: {bg}; color: {text2}; }}
QLineEdit#headerSearch:hover {{ border-color: {blue}; }}
QListWidget#searchResults::item {{ padding: 8px 10px; }}
QToolButton#headerIcon:focus {{ border: 2px solid {blue}; }}
QLineEdit, QComboBox {{ min-height: 30px; padding: 2px 8px; border: 1px solid {border};
    border-radius: 8px; background: {surface}; color: {text}; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding;
    subcontrol-position: center {arrow_side}; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {blue};
    border: 1px solid {border}; outline: none; }}
QStatusBar {{ background: {surface}; border-top: 1px solid {border}; color: {text2}; }}
QStatusBar QLabel {{ color: {text2}; padding: 0 8px; }}
QLabel#dbOk {{ color: {success}; font-weight: 600; }}
QLabel#dbBad {{ color: {danger}; font-weight: 600; }}
QStatusBar QLabel#statusWarn {{ color: {warning}; font-weight: 600; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {text2}; border-radius: 4px;
    background: {surface}; }}
QCheckBox::indicator:checked {{ background: {blue}; border-color: {blue}; image: url("{check}"); }}
QToolTip {{ background: {navy}; color: #fff; border: 1px solid {border}; padding: 4px; }}
QTableWidget, QTableView, QTreeView, QListWidget, QPlainTextEdit, QTextEdit {{
    background: {surface}; color: {text}; alternate-background-color: {bg};
    gridline-color: {border}; border: 1px solid {border}; border-radius: 10px;
    selection-background-color: {blue}; selection-color: {on_primary};
}}
QTableWidget::item, QTableView::item {{ padding: 4px 8px; border: none; }}
QTableWidget::item:hover, QTableView::item:hover {{ background: {hover}; }}
QTableWidget::item:selected, QTableView::item:selected {{ background: {blue}; color: {on_primary}; }}
QHeaderView {{ background: {bg}; }}
QHeaderView::section {{ background: {bg}; color: {text2}; border: none;
    border-bottom: 1px solid {border}; padding: 6px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {bg}; border: none; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; background: {surface}; }}
QTabBar::tab {{ background: transparent; color: {text2}; padding: 6px 14px; margin: 2px; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {blue}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar QToolButton {{ min-height: 0; padding: 0; border: none; border-radius: 4px;
    background: {surface}; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {border}; }}
QCalendarWidget QWidget {{ background: {surface}; color: {text}; }}
QScrollBar:vertical {{ background: {bg}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 6px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {bg}; height: 12px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 6px; min-width: 24px; }}
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


def _style_asset(name: str) -> str:
    return (Path(project_root()) / "assets" / "styles" / name).as_posix()


def build_qss(mode: ThemeMode, rtl: bool = False) -> str:
    dark = mode is ThemeMode.DARK
    tokens = DARK if dark else LIGHT
    return _QSS.format(
        arrow_side="left" if rtl else "right",
        chevron=_style_asset(f"chevron-down-{'dark' if dark else 'light'}.svg"),
        check=_style_asset("check.svg"),
        hover="rgba(255,255,255,0.05)" if dark else "rgba(22,120,211,0.06)",
        **tokens)


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
