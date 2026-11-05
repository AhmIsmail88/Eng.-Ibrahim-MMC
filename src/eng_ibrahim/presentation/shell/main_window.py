from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QRect, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import config
from ...application.context import AppContext
from ...application.services.backup_service import BackupService
from ...application.services.pm_service import PMService
from ...application.services.status_service import StatusService
from ...domain.enums import Language, ThemeMode
from .. import icons
from ..branding import load_app_icon, logo_pixmap
from ..icons import ICON_SIZE
from ..pages.assets import AssetsPage
from ..pages.audit import AuditPage
from ..pages.base import BasePage, local_time
from ..pages.dashboard import DashboardPage
from ..pages.failures import FailuresPage
from ..pages.inspections import InspectionsPage
from ..pages.master_data import MasterDataPage
from ..pages.notifications import NotificationsPage
from ..pages.parts import PartsPage
from ..pages.placeholder import PlaceholderPage
from ..pages.pm_calendar import PMCalendarPage
from ..pages.preventive import PMPage
from ..pages.purchases import PurchasesPage
from ..pages.reports import ReportsPage
from ..pages.settings import SettingsPage
from ..pages.suppliers import SuppliersPage
from ..pages.technicians import TechniciansPage
from ..pages.users import UsersPage
from ..pages.vehicles import VehiclesPage
from ..pages.work_orders import WorkOrdersPage
from ..theme.manager import ThemeManager
from ..theme.tokens import DARK, LIGHT
from ..widgets.global_search import KIND_TO_NAV, GlobalSearchDialog
from ..widgets.help_dialog import HelpDialog
from ..widgets.nav_button import NavButton
from ..workers.backup_worker import BackupWorker

log = logging.getLogger(__name__)


# key, icon name (presentation/icons.py), phase that implements it (0 = exists now)
NAV_ITEMS: list[tuple[str, str, int]] = [
    ("nav.dashboard", "dashboard", 0),
    ("nav.assets", "assets", 1),
    ("nav.work_orders", "work_orders", 2),
    ("nav.preventive", "preventive", 3),
    ("nav.corrective", "corrective", 2),
    ("nav.pm_calendar", "calendar", 0),
    ("nav.vehicles", "vehicles", 1),
    ("nav.checklists", "checklists", 3),
    ("nav.spare_parts", "spare_parts", 4),
    ("nav.technicians", "technicians", 1),
    ("nav.master_data", "master_data", 0),
    ("nav.audit", "audit", 0),
    ("nav.notifications", "notifications", 0),
    ("nav.suppliers", "suppliers", 1),
    ("nav.purchases", "purchases", 1),
    ("nav.reports", "reports", 5),
    ("nav.users", "users", 0),
    ("nav.settings", "settings", 0),
]
# Sections that only have a "coming later" placeholder stay out of the menu.
UNFINISHED: set[str] = set()
SIDEBAR_WIDE, SIDEBAR_NARROW = 230, 64
JOBS_DELAY_MS = 4000
JOBS_CHECK_MS = 60 * 60 * 1000

DEFAULT_SIZE, MIN_SIZE = (1440, 900), (1100, 700)


class MainWindow(QMainWindow):
    language_changed = Signal(str)

    def __init__(self, ctx: AppContext, theme: ThemeManager,
                 scheduled_jobs: bool = False) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(*MIN_SIZE)
        self._pages: dict[str, BasePage] = {}
        self._frames: dict[str, QScrollArea] = {}
        self._nav_buttons: dict[str, NavButton] = {}
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
        self.stack.setFocus()  # no focus ring on the first header button at start-up
        self._backup_running = False
        if scheduled_jobs:
            # Shortly after start-up, then hourly so a window left open for days still
            # gets its daily jobs. The checks are cheap; the backup runs off the UI thread.
            QTimer.singleShot(JOBS_DELAY_MS, self.run_scheduled_jobs)
            self._jobs_timer = QTimer(self)
            self._jobs_timer.setInterval(JOBS_CHECK_MS)
            self._jobs_timer.timeout.connect(self.run_scheduled_jobs)
            self._jobs_timer.start()

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
        # A launcher for the global search dialog: clicking or focusing it opens the dialog.
        self.search = QLineEdit()
        self.search.setObjectName("headerSearch")
        self.search.setReadOnly(True)
        self.search.setMinimumWidth(300)
        self.search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search.installEventFilter(self)
        self.btn_notifications = QToolButton()
        self.btn_notifications.clicked.connect(lambda: self.navigate("nav.notifications"))
        self.btn_theme = QToolButton()
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_settings = QToolButton()
        self.btn_settings.clicked.connect(lambda: self.navigate("nav.settings"))
        self.btn_help = QToolButton()
        self.btn_help.clicked.connect(self.show_help)
        self.btn_collapse = QToolButton()
        self.btn_collapse.clicked.connect(self.toggle_sidebar)
        for b in (self.btn_collapse, self.btn_help, self.btn_notifications, self.btn_theme,
                  self.btn_settings):
            b.setObjectName("headerIcon")
            b.setIconSize(ICON_SIZE)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_collapse)
        lay.addWidget(logo)
        lay.addLayout(titles)
        lay.addSpacing(24)
        lay.addWidget(self.search)
        lay.addStretch(1)
        for b in (self.btn_help, self.btn_notifications, self.btn_theme, self.btn_settings):
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
            btn = NavButton()
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setVisible(key not in UNFINISHED)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        # 17 sections do not fit a 700px-high window; the menu scrolls instead of squeezing.
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("sidebarScroll")
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar)
        self._apply_sidebar_width()
        return self.sidebar_scroll

    def _apply_sidebar_width(self) -> None:
        self.sidebar_scroll.setFixedWidth(SIDEBAR_NARROW if self._collapsed else SIDEBAR_WIDE)
        self.sidebar.setProperty("collapsed", self._collapsed)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        for key, btn in self._nav_buttons.items():
            label = self.ctx.tr(key)
            btn.set_label("" if self._collapsed else label)
            btn.setToolTip(label)
            btn.setAccessibleName(label)

    def _apply_icons(self) -> None:
        """Icons are drawn in theme colours, so they are rebuilt on every theme change."""
        tokens = DARK if self.theme.effective is ThemeMode.DARK else LIGHT
        names = {k: n for k, n, _ in NAV_ITEMS}
        for key, btn in self._nav_buttons.items():
            btn.set_icon(icons.icon(names[key], tokens["sidebar_text"], tokens["on_primary"]))
        theme_icon = "sun" if self.theme.effective is ThemeMode.DARK else "moon"
        for btn, name in ((self.btn_collapse, "menu"),
                          (self.btn_notifications, "notifications"),
                          (self.btn_settings, "settings"),
                          (self.btn_help, "help"),
                          (self.btn_theme, theme_icon)):
            btn.setIcon(icons.icon(name, tokens["text2"]))

    def toggle_sidebar(self) -> None:
        self._collapsed = not self._collapsed
        self.ctx.prefs.set("sidebar_collapsed", self._collapsed)
        self._apply_sidebar_width()

    # ---------------- pages ----------------
    def _build_pages(self) -> None:
        for key, _g, phase in NAV_ITEMS:
            if key == "nav.dashboard":
                dashboard = DashboardPage(self.ctx)
                dashboard.open_requested.connect(self.open_filtered)
                page: BasePage = dashboard
            elif key == "nav.assets":
                page = AssetsPage(self.ctx)
            elif key == "nav.work_orders":
                page = WorkOrdersPage(self.ctx)
            elif key == "nav.corrective":
                page = FailuresPage(self.ctx)
            elif key == "nav.preventive":
                page = PMPage(self.ctx)
            elif key == "nav.pm_calendar":
                page = PMCalendarPage(self.ctx)
            elif key == "nav.vehicles":
                page = VehiclesPage(self.ctx)
            elif key == "nav.checklists":
                page = InspectionsPage(self.ctx)
            elif key == "nav.spare_parts":
                page = PartsPage(self.ctx)
            elif key == "nav.reports":
                page = ReportsPage(self.ctx)
            elif key == "nav.technicians":
                page = TechniciansPage(self.ctx)
            elif key == "nav.suppliers":
                page = SuppliersPage(self.ctx)
            elif key == "nav.purchases":
                page = PurchasesPage(self.ctx)
            elif key == "nav.master_data":
                page = MasterDataPage(self.ctx)
            elif key == "nav.audit":
                audit = AuditPage(self.ctx)
                audit.open_requested.connect(self.open_record)
                page = audit
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
            # A page never gets less than its minimum size; it scrolls instead of overlapping.
            frame = QScrollArea()
            frame.setObjectName("pageScroll")
            frame.setWidgetResizable(True)
            frame.setFrameShape(QFrame.Shape.NoFrame)
            frame.setWidget(page)
            self._frames[key] = frame
            self.stack.addWidget(frame)

    def navigate(self, key: str) -> None:
        page = self._pages[key]
        self.stack.setCurrentWidget(self._frames[key])
        self._nav_buttons[key].setChecked(True)
        page.refresh()

    def open_filtered(self, key: str, flt: object = None) -> None:
        """Open a screen pre-filtered (dashboard cards)."""
        self.navigate(key)
        page = self._pages[key]
        if hasattr(page, "apply_filter"):
            page.apply_filter(flt)

    def current_key(self) -> str:
        w = self.stack.currentWidget()
        return next(k for k, f in self._frames.items() if f is w)

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
        self.st_backup.setText(f"{tr('status.last_backup')}: "
                               f"{local_time(last) if last else tr('status.never')}")
        stale = self._backups().is_stale()
        self.st_backup.setObjectName("statusWarn" if stale else "")
        self.st_backup.setToolTip(tr("status.backup_stale") if stale else "")
        self.st_backup.style().unpolish(self.st_backup)
        self.st_backup.style().polish(self.st_backup)
        profile = (self.ctx.current_user.display_name if self.ctx.current_user
                   else status.primary_profile_name() or self.ctx.profile_name)
        self.st_profile.setText(f"{tr('status.profile')}: {profile}")
        self.st_version.setText(
            f"{tr('status.version')}: \u2066{config.APP_VERSION}\u2069  |  "
            f"{tr('status.schema')}: \u2066{self.ctx.schema_revision}\u2069")

    # ---------------- automatic backup ----------------
    def _backups(self) -> BackupService:
        return BackupService(self.ctx.db, self.ctx.paths, self.ctx.schema_revision)

    def run_scheduled_jobs(self) -> None:
        """Daily PM generation (SPEC 9.4), then the daily backup (SPEC 23)."""
        self.run_pm_generation()
        self.run_auto_backup()

    def run_pm_generation(self) -> int:
        user = self.ctx.current_user
        if user is None or not self.ctx.can_edit:
            return 0
        try:
            result = PMService(self.ctx.db).auto_generate_due(user)
        except Exception:  # a scheduler failure must never take the window down
            log.exception("Automatic PM generation failed")
            return 0
        count = len(result.value or []) if result.ok else 0
        if count:
            log.info("Automatic PM generation: %d work order(s)", count)
            self.statusBar().showMessage(self.ctx.tr("status.pm_generated", count=count),
                                         15000)
            self._pages[self.current_key()].refresh()
        return count

    def run_auto_backup(self) -> bool:
        """Start the daily backup when it is due; returns True when one was started."""
        service = self._backups()
        if self._backup_running or not service.auto_enabled() or not service.is_due():
            return False
        self._backup_running = True
        self.statusBar().showMessage(self.ctx.tr("status.backup_running"))
        worker = BackupWorker(service)
        worker.signals.finished.connect(self._auto_backup_done)
        worker.signals.failed.connect(self._auto_backup_failed)
        QThreadPool.globalInstance().start(worker)
        return True

    def _auto_backup_done(self, path: str) -> None:
        self._backup_running = False
        log.info("Automatic backup written: %s", path)
        self.statusBar().showMessage(self.ctx.tr("status.backup_done"), 8000)
        self.refresh_status()

    def _auto_backup_failed(self, message: str) -> None:
        self._backup_running = False
        log.error("Automatic backup failed: %s", message)
        self.statusBar().showMessage(self.ctx.tr("status.backup_failed"), 15000)
        self.refresh_status()

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
        self._apply_icons()

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
        self.search.setToolTip(tr("search.placeholder"))
        self.search.setAccessibleName(tr("header.search"))
        for btn, key in ((self.btn_notifications, "header.notifications"),
                         (self.btn_theme, "header.theme"),
                         (self.btn_settings, "header.settings"),
                         (self.btn_help, "help.tip"),
                         (self.btn_collapse, "sidebar.collapse")):
            btn.setToolTip(tr(key))
            btn.setAccessibleName(tr(key))
        self._apply_sidebar_width()
        self._apply_icons()
        for page in self._pages.values():
            page.retranslate()
            button = getattr(page, "btn_new", None)
            if isinstance(button, QPushButton):
                button.setToolTip("Ctrl+N")
            search = getattr(page, "search", None)
            if isinstance(search, QLineEdit):
                search.setToolTip("Ctrl+F")
        self.refresh_status()

    # ---------------- shortcuts ----------------
    def _build_shortcuts(self) -> None:
        """SPEC 3.6. Window-scoped, so none of them fires while a dialog is open."""
        for keys, action in (("F5", self._refresh_current),
                             ("Ctrl+N", self.shortcut_new),
                             ("Ctrl+K", self.open_global_search),
                             ("Ctrl+F", self.shortcut_search),
                             ("Ctrl+P", lambda: self._click_report("btn_pdf")),
                             ("Ctrl+E", lambda: self._click_report("btn_xlsx")),
                             ("Ctrl+L", self.toggle_language),
                             ("F1", self.show_help)):
            QShortcut(QKeySequence(keys), self, activated=action)

    def shortcut_new(self) -> None:
        """Create a record of the current screen's kind; elsewhere a new work order."""
        page = self._pages[self.current_key()]
        button = getattr(page, "btn_new", None)
        if not (isinstance(button, QPushButton) and button.isVisibleTo(page)):
            self.navigate("nav.work_orders")
            page = self._pages["nav.work_orders"]
            button = page.btn_new  # type: ignore[attr-defined]
        if button.isEnabled():
            button.click()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.search and event.type() == QEvent.Type.MouseButtonPress:
            self.open_global_search()
            return True
        return super().eventFilter(watched, event)

    def open_global_search(self) -> None:
        dialog = GlobalSearchDialog(self.ctx, self)
        dialog.chosen.connect(self.open_record)
        dialog.exec()

    def open_record(self, kind: str, record_id: str) -> bool:
        key = KIND_TO_NAV[kind]
        self.navigate(key)
        page = self._pages[key]
        return bool(page.select_record(record_id))  # type: ignore[attr-defined]

    def shortcut_search(self) -> None:
        search = getattr(self._pages[self.current_key()], "search", None)
        if isinstance(search, QLineEdit):
            search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            search.selectAll()

    def _click_report(self, name: str) -> None:
        """Print/export belong to the reports screen; open it when elsewhere."""
        if self.current_key() != "nav.reports":
            self.navigate("nav.reports")
            return
        button = getattr(self._pages["nav.reports"], name, None)
        if isinstance(button, QPushButton) and button.isEnabled():
            button.click()

    def toggle_language(self) -> None:
        current = self.ctx.localizer.language
        self.set_language((Language.EN if current is Language.AR else Language.AR).value)

    def show_help(self) -> None:
        """The user guide; its last section lists every shortcut."""
        HelpDialog(self.ctx, self).exec()

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
