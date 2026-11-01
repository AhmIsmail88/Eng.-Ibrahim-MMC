from __future__ import annotations

import logging

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import config
from ...application.context import AppContext
from ...application.services.status_service import StatusService
from ...domain.enums import Language, ThemeMode
from ..branding import load_app_icon, logo_pixmap
from ..pages.assets import AssetsPage
from ..pages.audit import AuditPage
from ..pages.base import BasePage
from ..pages.dashboard import DashboardPage
from ..pages.failures import FailuresPage
from ..pages.inspections import InspectionsPage
from ..pages.master_data import MasterDataPage
from ..pages.notifications import NotificationsPage
from ..pages.parts import PartsPage
from ..pages.placeholder import PlaceholderPage
from ..pages.preventive import PMPage
from ..pages.reports import ReportsPage
from ..pages.settings import SettingsPage
from ..pages.technicians import TechniciansPage
from ..pages.users import UsersPage
from ..pages.work_orders import WorkOrdersPage
from ..theme.manager import ThemeManager

log = logging.getLogger(__name__)


def _glyph(widget, text: str) -> str:
    """Keep only characters the active font can draw (no tofu boxes in nav/header)."""
    from PySide6.QtGui import QFontMetrics
    metrics = QFontMetrics(widget.font())
    return "".join(ch for ch in text if ch == " " or metrics.inFontUcs4(ord(ch)))

# key, glyph, phase that implements it (0 = exists now)
NAV_ITEMS: list[tuple[str, str, int]] = [
    ("nav.dashboard", "◧", 0),
    ("nav.assets", "⚙", 1),
    ("nav.work_orders", "☰", 2),
    ("nav.preventive", "⟳", 3),
    ("nav.corrective", "⚠", 2),
    ("nav.vehicles", "◈", 1),
    ("nav.checklists", "✓", 3),
    ("nav.spare_parts", "▤", 4),
    ("nav.technicians", "☺", 1),
    ("nav.master_data", "▦", 0),
    ("nav.audit", "⌸", 0),
    ("nav.notifications", "◉", 0),
    ("nav.reports", "▥", 5),
    ("nav.users", "☷", 0),
    ("nav.settings", "⚒", 0),
]
SIDEBAR_WIDE, SIDEBAR_NARROW = 230, 64
DEFAULT_SIZE, MIN_SIZE = (1440, 900), (1100, 700)


class MainWindow(QMainWindow):
    language_changed = Signal(str)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(*MIN_SIZE)
        self._pages: dict[str, BasePage] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._collapsed = bool(ctx.prefs.get("sidebar_collapsed"))

        root = QWidget()
        root.setObjectName("pageRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(root)
        self._build_pages()
        self._build_status_bar()
        self._build_shortcuts()
        self.retranslate()
        self.navigate("nav.dashboard")
        self.restore_geometry()

    # ---------------- header ----------------
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(40))
        logo.setAccessibleName("logo")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.brand_title = QLabel(config.APP_NAME)
        self.brand_title.setObjectName("brandTitle")
        self.brand_sub = QLabel()
        self.brand_sub.setObjectName("brandSub")
        titles.addWidget(self.brand_title)
        titles.addWidget(self.brand_sub)
        self.search = QLineEdit()
        self.search.setEnabled(False)  # global search arrives in a later phase (no dead controls)
        self.search.setMinimumWidth(280)
        self.btn_notifications = QToolButton()
        self.btn_notifications.setText(_glyph(self.btn_notifications, "🔔"))
        self.btn_notifications.setEnabled(False)
        self.btn_theme = QToolButton()
        self.btn_theme.setText(_glyph(self.btn_theme, "◐"))
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_settings = QToolButton()
        self.btn_settings.setText(_glyph(self.btn_settings, "⚒"))
        self.btn_settings.clicked.connect(lambda: self.navigate("nav.settings"))
        self.btn_collapse = QToolButton()
        self.btn_collapse.setText(_glyph(self.btn_collapse, "☰"))
        self.btn_collapse.clicked.connect(self.toggle_sidebar)
        lay.addWidget(self.btn_collapse)
        lay.addWidget(logo)
        lay.addLayout(titles)
        lay.addSpacing(24)
        lay.addWidget(self.search)
        lay.addStretch(1)
        for b in (self.btn_notifications, self.btn_theme, self.btn_settings):
            lay.addWidget(b)
        return header

    # ---------------- sidebar ----------------
    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        lay = QVBoxLayout(self.sidebar)
        lay.setContentsMargins(10, 16, 10, 16)
        lay.setSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for key, _glyph, _phase in NAV_ITEMS:
            if key == "nav.users" and not self.ctx.is_admin:
                continue  # admin-only screen; the service refuses anyway
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._apply_sidebar_width()
        return self.sidebar

    def _apply_sidebar_width(self) -> None:
        self.sidebar.setFixedWidth(SIDEBAR_NARROW if self._collapsed else SIDEBAR_WIDE)
        glyphs = {k: g for k, g, _ in NAV_ITEMS}
        for key, btn in self._nav_buttons.items():
            label = self.ctx.tr(key)
            icon = _glyph(btn, glyphs[key])
            if self._collapsed:
                btn.setText(icon or label[:1])
            else:
                btn.setText(f"{icon}   {label}" if icon else label)
            btn.setToolTip(label)
            btn.setAccessibleName(label)

    def toggle_sidebar(self) -> None:
        self._collapsed = not self._collapsed
        self.ctx.prefs.set("sidebar_collapsed", self._collapsed)
        self._apply_sidebar_width()

    # ---------------- pages ----------------
    def _build_pages(self) -> None:
        for key, _g, phase in NAV_ITEMS:
            if key == "nav.dashboard":
                page: BasePage = DashboardPage(self.ctx)
            elif key == "nav.assets":
                page = AssetsPage(self.ctx)
            elif key == "nav.work_orders":
                page = WorkOrdersPage(self.ctx)
            elif key == "nav.corrective":
                page = FailuresPage(self.ctx)
            elif key == "nav.preventive":
                page = PMPage(self.ctx)
            elif key == "nav.checklists":
                page = InspectionsPage(self.ctx)
            elif key == "nav.spare_parts":
                page = PartsPage(self.ctx)
            elif key == "nav.reports":
                page = ReportsPage(self.ctx)
            elif key == "nav.technicians":
                page = TechniciansPage(self.ctx)
            elif key == "nav.master_data":
                page = MasterDataPage(self.ctx)
            elif key == "nav.audit":
                page = AuditPage(self.ctx)
            elif key == "nav.notifications":
                page = NotificationsPage(self.ctx)
            elif key == "nav.users":
                page = UsersPage(self.ctx)
            elif key == "nav.settings":
                sp = SettingsPage(self.ctx)
                sp.language_changed.connect(self.set_language)
                sp.theme_changed.connect(self.set_theme)
                page = sp
            else:
                page = PlaceholderPage(self.ctx, key, phase)
            self._pages[key] = page
            self.stack.addWidget(page)

    def navigate(self, key: str) -> None:
        page = self._pages[key]
        self.stack.setCurrentWidget(page)
        self._nav_buttons[key].setChecked(True)
        page.refresh()

    def current_key(self) -> str:
        w = self.stack.currentWidget()
        return next(k for k, p in self._pages.items() if p is w)

    # ---------------- status bar ----------------
    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.st_db, self.st_backup = QLabel(), QLabel()
        self.st_profile, self.st_version = QLabel(), QLabel()
        for w in (self.st_db, self.st_backup, self.st_profile, self.st_version):
            sb.addWidget(w)

    def refresh_status(self) -> None:
        tr = self.ctx.tr
        status = StatusService(self.ctx.db)
        ok = self.ctx.db_ok
        self.st_db.setObjectName("dbOk" if ok else "dbBad")
        self.st_db.setText(("● " if ok else "✖ ") + tr("status.db_ok" if ok else "status.db_problem"))
        self.st_db.style().unpolish(self.st_db)
        self.st_db.style().polish(self.st_db)
        last = status.last_successful_backup()
        self.st_backup.setText(f"{tr('status.last_backup')}: {last or tr('status.never')}")
        profile = (self.ctx.current_user.display_name if self.ctx.current_user
                   else status.primary_profile_name() or self.ctx.profile_name)
        self.st_profile.setText(f"{tr('status.profile')}: {profile}")
        self.st_version.setText(
            f"{tr('status.version')}: \u2066{config.APP_VERSION}\u2069  |  "
            f"{tr('status.schema')}: \u2066{self.ctx.schema_revision}\u2069")

    # ---------------- language / theme ----------------
    def apply_direction(self) -> None:
        app = QGuiApplication.instance()
        direction = (Qt.LayoutDirection.RightToLeft if self.ctx.localizer.is_rtl
                     else Qt.LayoutDirection.LeftToRight)
        if app is not None:
            app.setLayoutDirection(direction)  # type: ignore[attr-defined]
        self.setLayoutDirection(direction)
        if self.theme.rtl != self.ctx.localizer.is_rtl:
            self.theme.rtl = self.ctx.localizer.is_rtl
            self.theme.apply()

    def set_language(self, lang: str) -> None:
        lang_enum = Language(lang)
        if lang_enum == self.ctx.localizer.language:
            return
        self.ctx.localizer.set_language(lang_enum)
        self.ctx.prefs.set("language", lang_enum.value)
        self.retranslate()
        self.language_changed.emit(lang_enum.value)

    def set_theme(self, mode: str) -> None:
        self.ctx.prefs.set("theme", mode)
        self.theme.apply(ThemeMode(mode))

    def toggle_theme(self) -> None:
        from ..theme.manager import resolve_mode
        current = resolve_mode(ThemeMode(self.ctx.prefs.get("theme")))
        nxt = ThemeMode.DARK if current is ThemeMode.LIGHT else ThemeMode.LIGHT
        self.set_theme(nxt.value)
        settings = self._pages["nav.settings"]
        if isinstance(settings, SettingsPage):
            settings.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.apply_direction()
        self.setWindowTitle(f"{config.APP_NAME} – {tr('app.subtitle')}")
        self.brand_sub.setText(tr("app.subtitle"))
        self.search.setPlaceholderText(tr("header.search"))
        self.search.setToolTip(tr("header.search_tip"))
        self.search.setAccessibleName(tr("header.search"))
        for btn, key in ((self.btn_notifications, "header.notifications"),
                         (self.btn_theme, "header.theme"),
                         (self.btn_settings, "header.settings"),
                         (self.btn_collapse, "sidebar.collapse")):
            btn.setToolTip(tr(key))
            btn.setAccessibleName(tr(key))
        self._apply_sidebar_width()
        for page in self._pages.values():
            page.retranslate()
        self.refresh_status()

    # ---------------- shortcuts ----------------
    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("F5"), self, activated=self._refresh_current)

    def _refresh_current(self) -> None:
        self._pages[self.current_key()].refresh()
        self.refresh_status()

    # ---------------- geometry ----------------
    def restore_geometry(self) -> None:
        saved = self.ctx.prefs.get("window")
        screen_geo = QGuiApplication.primaryScreen().availableGeometry()
        if isinstance(saved, dict):
            rect = QRect(saved.get("x", 0), saved.get("y", 0), saved.get("w", 0), saved.get("h", 0))
            on_screen = any(s.availableGeometry().intersects(rect)
                            for s in QGuiApplication.screens())
            if on_screen and rect.width() >= MIN_SIZE[0] and rect.height() >= MIN_SIZE[1]:
                self.setGeometry(rect)
                return
        w = min(DEFAULT_SIZE[0], screen_geo.width())
        h = min(DEFAULT_SIZE[1], screen_geo.height())
        self.resize(max(w, 0), max(h, 0))

    def closeEvent(self, event) -> None:
        g = self.geometry()
        self.ctx.prefs.set("window", {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()})
        super().closeEvent(event)
