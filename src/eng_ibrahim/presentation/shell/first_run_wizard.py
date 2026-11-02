"""UI-001 First Run Wizard (SPEC 21.1). Logic lives in FirstRunService; this is only UI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimeZone
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from ...application.context import AppContext
from ...application.services.first_run_service import FirstRunInput, FirstRunService
from ...domain.enums import Language
from ...infrastructure.database.orm_models import Currency
from ..branding import logo_pixmap

STEPS = ["welcome", "station", "currency", "user", "backup", "summary"]
DEFAULT_CURRENCY = "EGP"


class FirstRunWizard(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None, *,
                 show_recovery_dialog: bool = True) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.show_recovery_dialog = show_recovery_dialog
        self.setModal(True)
        self.setMinimumSize(640, 520)
        self.recovery_code: str | None = None
        self._build()
        self.retranslate()
        self._goto(0)

    # ---------- construction ----------
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        self.step_label = QLabel()
        self.step_label.setObjectName("hint")
        lay.addWidget(self.step_label)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        nav = QHBoxLayout()
        self.btn_cancel, self.btn_back, self.btn_next = QPushButton(), QPushButton(), QPushButton()
        self.btn_next.setObjectName("primary")
        self.btn_next.setDefault(True)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_back.clicked.connect(lambda: self._goto(self.stack.currentIndex() - 1))
        self.btn_next.clicked.connect(self._next)
        nav.addWidget(self.btn_cancel)
        nav.addStretch(1)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_next)
        lay.addLayout(nav)

        # 0 welcome
        w0 = QWidget()
        f0 = QVBoxLayout(w0)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72))
        self.welcome_title = QLabel()
        self.welcome_title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        self.welcome_body = QLabel()
        self.welcome_body.setWordWrap(True)
        self.lang_label = QLabel()
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("العربية", Language.AR.value)
        self.lang_combo.addItem("English", Language.EN.value)
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(self.ctx.localizer.language.value))
        self.lang_combo.currentIndexChanged.connect(self._lang_changed)
        for w in (logo, self.welcome_title, self.welcome_body, self.lang_label, self.lang_combo):
            f0.addWidget(w)
        f0.addStretch(1)
        self.stack.addWidget(w0)

        # 1 station
        w1 = QWidget()
        f1 = QFormLayout(w1)
        self.station_ar, self.station_en = QLineEdit(), QLineEdit()
        self.lbl_station_ar, self.lbl_station_en = QLabel(), QLabel()
        f1.addRow(self.lbl_station_ar, self.station_ar)
        f1.addRow(self.lbl_station_en, self.station_en)
        self.stack.addWidget(w1)

        # 2 currency/timezone
        w2 = QWidget()
        f2 = QFormLayout(w2)
        self.currency, self.timezone = QComboBox(), QComboBox()
        with self.ctx.db.session() as s:
            codes = []
            for code, name in s.execute(select(Currency.code, Currency.name)).all():
                self.currency.addItem(f"{code} – {name}", code)
                codes.append(code)
        # Currencies are seeded in the same transaction as first-run; before that table is empty.
        if self.currency.count() == 0:
            from ...infrastructure.database.seed_reference_data import CURRENCIES
            for code, _minor, name in CURRENCIES:
                self.currency.addItem(f"{code} – {name}", code)
        self.currency.setCurrentIndex(max(0, self.currency.findData(DEFAULT_CURRENCY)))
        system_tz = QTimeZone.systemTimeZoneId().data().decode()
        zones = sorted({z.data().decode() for z in QTimeZone.availableTimeZoneIds()} | {system_tz})
        self.timezone.addItems(zones)
        self.timezone.setCurrentText(system_tz)
        self.timezone.setEditable(False)
        self.lbl_currency, self.lbl_tz, self.currency_note = QLabel(), QLabel(), QLabel()
        self.currency_note.setObjectName("hint")
        self.currency_note.setWordWrap(True)
        f2.addRow(self.lbl_currency, self.currency)
        f2.addRow(self.currency_note)
        f2.addRow(self.lbl_tz, self.timezone)
        self.stack.addWidget(w2)

        # 3 user
        w3 = QWidget()
        f3 = QFormLayout(w3)
        self.username, self.display_name = QLineEdit("admin"), QLineEdit()
        self.password, self.password2 = QLineEdit(), QLineEdit()
        for pw in (self.password, self.password2):
            pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_user, self.lbl_disp, self.lbl_pw, self.lbl_pw2 = (QLabel() for _ in range(4))
        self.pw_note = QLabel()
        self.pw_note.setObjectName("hint")
        self.pw_note.setWordWrap(True)
        f3.addRow(self.lbl_user, self.username)
        f3.addRow(self.lbl_disp, self.display_name)
        f3.addRow(self.lbl_pw, self.password)
        f3.addRow(self.lbl_pw2, self.password2)
        f3.addRow(self.pw_note)
        self.stack.addWidget(w3)

        # 4 backup folder
        w4 = QWidget()
        f4 = QVBoxLayout(w4)
        self.lbl_backup = QLabel()
        row = QHBoxLayout()
        self.backup_edit = QLineEdit(str(self.ctx.paths.backups))
        self.btn_browse = QPushButton()
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.backup_edit, 1)
        row.addWidget(self.btn_browse)
        f4.addWidget(self.lbl_backup)
        f4.addLayout(row)
        f4.addStretch(1)
        self.stack.addWidget(w4)

        # 5 summary
        w5 = QWidget()
        f5 = QVBoxLayout(w5)
        self.summary_title = QLabel()
        self.summary_title.setStyleSheet("font-weight: 700; font-size: 12pt;")
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.seed_note = QLabel()
        self.seed_note.setObjectName("hint")
        self.seed_note.setWordWrap(True)
        for w in (self.summary_title, self.summary, self.seed_note):
            f5.addWidget(w)
        self.stack.addWidget(w5)

    # ---------- behaviour ----------
    def _lang_changed(self) -> None:
        lang = self.lang_combo.currentData()
        self.ctx.localizer.set_language(lang)
        self.ctx.prefs.set("language", lang)
        from PySide6.QtWidgets import QApplication
        QApplication.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.ctx.localizer.is_rtl
            else Qt.LayoutDirection.LeftToRight)
        self.retranslate()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.ctx.tr("wizard.backup_folder"),
                                             self.backup_edit.text())
        if d:
            self.backup_edit.setText(d)

    def _input(self) -> FirstRunInput:
        return FirstRunInput(
            station_name_ar=self.station_ar.text(), station_name_en=self.station_en.text(),
            currency_code=self.currency.currentData(), timezone=self.timezone.currentText(),
            username=self.username.text(), display_name=self.display_name.text(),
            backup_folder=Path(self.backup_edit.text()),
            password=self.password.text(),
        )

    def _validate_step(self, idx: int) -> str | None:
        data = self._input()
        if STEPS[idx] == "station" and not (data.station_name_ar.strip()
                                            or data.station_name_en.strip()):
            return "err.station_name_required"
        if STEPS[idx] == "user":
            if not data.username.strip():
                return "err.username_required"
            if self.password.text() != self.password2.text():
                return "err.password_mismatch"
            if not self.password.text():
                return "err.password_required"
            if len(self.password.text()) < 8:
                return "err.password_too_short"
        return None

    def _next(self) -> None:
        idx = self.stack.currentIndex()
        err = self._validate_step(idx)
        if err:
            self.error.setText(self.ctx.tr(err))
            return
        if idx == len(STEPS) - 1:
            self._finish()
        else:
            self._goto(idx + 1)

    def _goto(self, idx: int) -> None:
        idx = max(0, min(idx, len(STEPS) - 1))
        self.stack.setCurrentIndex(idx)
        self.error.clear()
        if STEPS[idx] == "summary":
            self._fill_summary()
        self._update_nav()

    def _update_nav(self) -> None:
        tr = self.ctx.tr
        idx = self.stack.currentIndex()
        self.btn_back.setEnabled(idx > 0)
        last = idx == len(STEPS) - 1
        self.btn_next.setText(tr("wizard.create") if last else tr("wizard.next"))
        self.step_label.setText(f"{idx + 1}/{len(STEPS)} – {tr('wizard.step.' + STEPS[idx])}")

    def _fill_summary(self) -> None:
        tr = self.ctx.tr
        d = self._input()
        lines = [
            f"{tr('wizard.station_ar')}: {d.station_name_ar}",
            f"{tr('wizard.station_en')}: {d.station_name_en}",
            f"{tr('wizard.currency')}: {d.currency_code}",
            f"{tr('wizard.timezone')}: {d.timezone}",
            f"{tr('wizard.username')}: {d.username}",
            f"{tr('wizard.password')}: {'●●●●●●●●' if d.password else '—'}",
            f"{tr('wizard.backup_folder')}: {d.backup_folder}",
        ]
        self.summary.setPlainText("\n".join(lines))

    def _finish(self) -> None:
        result = FirstRunService(self.ctx.db).complete(self._input())
        if not result.ok:
            self.error.setText(self.ctx.tr(result.error_code or "err.invalid"))
            return
        out = result.value
        assert out is not None
        self.ctx.profile_name = self.display_name.text().strip() or self.username.text().strip()
        if out.recovery_code and self.show_recovery_dialog:
            RecoveryCodeDialog(self.ctx, out.recovery_code, self).exec()
        self.accept()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.setWindowTitle(tr("wizard.title"))
        self.btn_cancel.setText(tr("wizard.cancel"))
        self.btn_back.setText(tr("wizard.back"))
        self.welcome_title.setText(tr("wizard.welcome"))
        self.welcome_body.setText(tr("wizard.welcome_body"))
        self.lang_label.setText(tr("wizard.language"))
        self.lbl_station_ar.setText(tr("wizard.station_ar"))
        self.lbl_station_en.setText(tr("wizard.station_en"))
        self.lbl_currency.setText(tr("wizard.currency"))
        self.currency_note.setText(tr("wizard.currency_note"))
        self.lbl_tz.setText(tr("wizard.timezone"))
        self.lbl_user.setText(tr("wizard.username"))
        self.lbl_disp.setText(tr("wizard.display_name"))
        self.lbl_pw.setText(tr("wizard.password"))
        self.lbl_pw2.setText(tr("wizard.password_confirm"))
        self.pw_note.setText(tr("wizard.password_note"))
        self.lbl_backup.setText(tr("wizard.backup_folder"))
        self.btn_browse.setText(tr("wizard.browse"))
        self.summary_title.setText(tr("wizard.summary"))
        self.seed_note.setText(tr("wizard.seed_note"))
        self._update_nav()


class RecoveryCodeDialog(QDialog):
    """Shows the recovery code exactly once; OK stays disabled until user confirms saving it."""

    def __init__(self, ctx: AppContext, code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        tr = ctx.tr
        self.setWindowTitle(tr("wizard.recovery_title"))
        self.setModal(True)
        lay = QVBoxLayout(self)
        body = QLabel(tr("wizard.recovery_body"))
        body.setWordWrap(True)
        self.code_label = QLineEdit(code)
        self.code_label.setReadOnly(True)
        self.code_label.setStyleSheet("font-size: 16pt; font-family: Consolas, monospace;")
        self.code_label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.confirm = QCheckBox(tr("wizard.recovery_confirm"))
        self.ok = QPushButton(tr("wizard.done"))
        self.ok.setObjectName("primary")
        self.ok.setEnabled(False)
        self.confirm.toggled.connect(self.ok.setEnabled)
        self.ok.clicked.connect(self.accept)
        for w in (body, self.code_label, self.confirm, self.ok):
            lay.addWidget(w)
