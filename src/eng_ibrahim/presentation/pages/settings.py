from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from ... import config
from ...application.context import AppContext
from ...application.services.backup_service import BackupService
from ...domain.enums import Language, ThemeMode
from .base import BasePage, make_card, make_title, set_ltr_value, vbox


class SettingsPage(BasePage):
    language_changed = Signal(str)
    theme_changed = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        lay = vbox(self)
        self.title = make_title()
        card = make_card()
        form = QFormLayout(card)
        form.setContentsMargins(24, 24, 24, 24)
        form.setVerticalSpacing(12)
        self.lang_label, self.theme_label = QLabel(), QLabel()
        self.lang_combo, self.theme_combo = QComboBox(), QComboBox()
        self.restart_note = QLabel()
        self.restart_note.setObjectName("hint")
        form.addRow(self.lang_label, self.lang_combo)
        form.addRow(self.theme_label, self.theme_combo)
        form.addRow(self.restart_note)

        about = make_card()
        af = QFormLayout(about)
        af.setContentsMargins(24, 24, 24, 24)
        af.setVerticalSpacing(8)
        self.about_title = QLabel()
        self.about_title.setStyleSheet("font-weight: 700;")
        self.ver_label, self.schema_label = QLabel(), QLabel()
        self.data_label, self.log_label = QLabel(), QLabel()
        self.ver_val, self.schema_val = QLabel(), QLabel()
        self.data_val, self.log_val = QLabel(), QLabel()
        for v in (self.ver_val, self.schema_val, self.data_val, self.log_val):
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setWordWrap(True)
        af.addRow(self.about_title)
        af.addRow(self.ver_label, self.ver_val)
        af.addRow(self.schema_label, self.schema_val)
        af.addRow(self.data_label, self.data_val)
        af.addRow(self.log_label, self.log_val)

        backup = make_card()
        bf = QFormLayout(backup)
        bf.setContentsMargins(24, 24, 24, 24)
        bf.setVerticalSpacing(10)
        self.backup_title = QLabel()
        self.backup_title.setStyleSheet("font-weight: 700;")
        self.last_label, self.last_val = QLabel(), QLabel()
        row = QWidget()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        self.btn_backup = QPushButton()
        self.btn_restore = QPushButton()
        self.btn_folder = QPushButton()
        for btn in (self.btn_backup, self.btn_restore, self.btn_folder):
            row_lay.addWidget(btn)
        row_lay.addStretch(1)
        bf.addRow(self.backup_title)
        bf.addRow(self.last_label, self.last_val)
        bf.addRow(row)

        lay.addWidget(self.title)
        lay.addWidget(card)
        lay.addWidget(backup)
        lay.addWidget(about)
        lay.addStretch(1)
        self._fill_combos()
        self.lang_combo.currentIndexChanged.connect(self._on_lang)
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        self.btn_backup.clicked.connect(self._backup_now)
        self.btn_restore.clicked.connect(self._restore)
        self.btn_folder.clicked.connect(self._open_folder)
        self.retranslate()

    def _service(self) -> BackupService:
        return BackupService(self.ctx.db, self.ctx.paths, self.ctx.schema_revision)

    def _refresh_backup(self) -> None:
        last = self._service().last_backup()
        self.last_val.setText(last[:19].replace("T", " ") if last
                              else self.ctx.tr("settings.never"))

    def _backup_now(self) -> None:
        result = self._service().create()
        if not result.ok:
            QMessageBox.critical(self, self.ctx.tr("settings.backup"),
                                 self.ctx.tr(result.error_code or "err.backup_failed"))
            return
        self._refresh_backup()
        QMessageBox.information(self, self.ctx.tr("settings.backup"),
                                self.ctx.tr("reports.saved", path=str(result.value)))

    def _restore(self) -> None:
        path, _f = QFileDialog.getOpenFileName(
            self, self.ctx.tr("settings.restore"), str(self.ctx.paths.backups),
            "ENG. IBRAHIM backup (*.eibak)")
        if not path:
            return
        answer = QMessageBox.warning(
            self, self.ctx.tr("settings.restore"), self.ctx.tr("settings.restore_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self._service().restore(__import__("pathlib").Path(path))
        if not result.ok:
            QMessageBox.critical(self, self.ctx.tr("settings.restore"),
                                 self.ctx.tr(result.error_code or "err.backup_invalid"))
            return
        QMessageBox.information(self, self.ctx.tr("settings.restore"),
                                self.ctx.tr("settings.restore_done"))

    def _open_folder(self) -> None:
        self.ctx.paths.backups.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.backups)))

    def _fill_combos(self) -> None:
        self.lang_combo.blockSignals(True)
        self.theme_combo.blockSignals(True)
        self.lang_combo.clear()
        self.theme_combo.clear()
        self.lang_combo.addItem(self.ctx.tr("settings.lang_ar"), Language.AR.value)
        self.lang_combo.addItem(self.ctx.tr("settings.lang_en"), Language.EN.value)
        self.theme_combo.addItem(self.ctx.tr("settings.theme_light"), ThemeMode.LIGHT.value)
        self.theme_combo.addItem(self.ctx.tr("settings.theme_dark"), ThemeMode.DARK.value)
        self.theme_combo.addItem(self.ctx.tr("settings.theme_system"), ThemeMode.SYSTEM.value)
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(self.ctx.localizer.language.value))
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.ctx.prefs.get("theme")))
        self.lang_combo.blockSignals(False)
        self.theme_combo.blockSignals(False)

    def _on_lang(self) -> None:
        self.language_changed.emit(self.lang_combo.currentData())

    def _on_theme(self) -> None:
        self.theme_changed.emit(self.theme_combo.currentData())

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("settings.title"))
        self.lang_label.setText(tr("settings.language"))
        self.theme_label.setText(tr("settings.theme"))
        self.restart_note.setText(tr("settings.restart_note"))
        self.about_title.setText(tr("settings.about"))
        self.ver_label.setText(tr("status.version"))
        self.schema_label.setText(tr("status.schema"))
        self.data_label.setText(tr("settings.app_data"))
        self.log_label.setText(tr("settings.log_folder"))
        rtl = self.ctx.localizer.is_rtl
        set_ltr_value(self.ver_val, config.APP_VERSION, rtl)
        set_ltr_value(self.schema_val, self.ctx.schema_revision, rtl)
        set_ltr_value(self.data_val, str(self.ctx.paths.root), rtl)
        set_ltr_value(self.log_val, str(self.ctx.paths.logs), rtl)
        self._fill_combos()
