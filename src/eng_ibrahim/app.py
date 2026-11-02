"""Composition / bootstrap (SPEC 20.2). Keep logic out of here; wire only."""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from . import config
from .application.context import AppContext
from .application.services.auth_service import AuthService
from .application.services.settings_service import SettingsService
from .domain.enums import Language, ThemeMode
from .domain.exceptions import DatabaseStartupError
from .infrastructure.database.engine import Database
from .infrastructure.database.migration_runner import (
    MigrationReport,
    ensure_database,
    quick_check,
)
from .infrastructure.logging.setup import setup_logging
from .infrastructure.storage.preferences import PreferencesStore
from .localization.service import Localizer
from .presentation.branding import load_app_icon
from .presentation.shell.first_run_wizard import FirstRunWizard
from .presentation.shell.login_dialog import LoginDialog
from .presentation.shell.main_window import MainWindow
from .presentation.shell.startup_error import RETRY, StartupErrorDialog
from .presentation.theme.manager import ThemeManager
from .presentation.widgets import dialog_shortcuts

log = logging.getLogger("eng_ibrahim")


def build_context(paths: config.AppPaths) -> tuple[AppContext, MigrationReport]:
    """Open/migrate the DB and wire services. Raises DatabaseStartupError (never wipes data)."""
    report = ensure_database(paths)
    db = Database(paths.db_file)
    prefs = PreferencesStore(paths.preferences_file)
    try:
        lang = Language(prefs.get("language"))
    except ValueError:
        lang = Language.AR
    ctx = AppContext(
        paths=paths, db=db, prefs=prefs, localizer=Localizer(lang),
        settings=SettingsService(db), schema_revision=report.current_revision,
        db_ok=quick_check(paths.db_file),
    )
    return ctx, report


def _install_excepthook(loc: Localizer, log_dir: Path) -> None:
    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Unhandled exception:\n%s", text)
        box = QMessageBox(QMessageBox.Icon.Critical, loc.tr("common.error"),
                          f"{exc}\n\nLogs: {log_dir}")
        box.setDetailedText(text)
        box.exec()
    sys.excepthook = hook


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_DIR_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setWindowIcon(load_app_icon())

    paths = config.get_paths()
    paths.ensure()
    setup_logging(paths.logs)
    log.info("Starting %s %s (data: %s)", config.APP_NAME, config.APP_VERSION, paths.root)

    boot_prefs = PreferencesStore(paths.preferences_file)
    boot_loc = Localizer(boot_prefs.get("language") if boot_prefs.get("language") in ("ar", "en")
                         else "ar")

    lock = QLockFile(str(paths.root / "app.lock"))
    lock.setStaleLockTime(0)  # stale detection relies on PID liveness
    if not lock.tryLock(200):
        QMessageBox.information(None, config.APP_NAME, boot_loc.tr("startup.already_running"))
        return 0

    dialog_shortcuts.install(app)  # Ctrl+S saves the open form (SPEC 3.6)
    theme = ThemeManager(app, ThemeMode(boot_prefs.get("theme")))
    theme.apply()

    while True:
        try:
            ctx, report = build_context(paths)
            break
        except DatabaseStartupError as exc:
            log.error("Startup DB error: %s", exc)
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if boot_loc.is_rtl
                                   else Qt.LayoutDirection.LeftToRight)
            if StartupErrorDialog(boot_loc, paths, str(exc)).exec() != RETRY:
                lock.unlock()
                return 1

    _install_excepthook(ctx.localizer, paths.logs)
    log.info("DB ready (revision %s, new=%s)", report.current_revision, report.created_new)

    just_onboarded = False
    if not ctx.settings.is_first_run_completed():
        wizard = FirstRunWizard(ctx)
        if wizard.exec() != wizard.DialogCode.Accepted:
            ctx.db.dispose()
            lock.unlock()
            return 0
        just_onboarded = True

    # Login gate (SPEC 21.3, ADR-025). Owner mode = one active password-less account.
    auth = AuthService(ctx.db)
    if just_onboarded:
        # The wizard just created and authenticated this account; asking again is noise.
        ctx.current_user = auth.sole_active_user()
    elif auth.login_required():
        login = LoginDialog(ctx, auth)
        if login.exec() != login.DialogCode.Accepted or login.user is None:
            ctx.db.dispose()
            lock.unlock()
            return 0
        ctx.current_user = login.user
        log.info("Login: %s (%s)", login.user.username, login.user.role)
    else:
        ctx.current_user = auth.sole_active_user()

    window = MainWindow(ctx, theme, scheduled_jobs=True)
    window.show()
    code = app.exec()
    ctx.db.dispose()
    lock.unlock()
    return code
