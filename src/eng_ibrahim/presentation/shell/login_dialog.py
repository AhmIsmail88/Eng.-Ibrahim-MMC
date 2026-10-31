"""Login screen (SPEC 21.3, ADR-025).

Shown only when `AuthService.login_required()` is true. The dialog returns an
`AuthUser`; the caller puts it on the AppContext. Failed attempts never reveal
whether the username exists.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ... import config
from ...application.context import AppContext
from ...application.services.auth_service import AuthService, AuthUser
from ..branding import logo_pixmap


class LoginDialog(QDialog):
    def __init__(self, ctx: AppContext, auth: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.auth = auth
        self.user: AuthUser | None = None
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build()
        self.retranslate()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 16)
        outer.setSpacing(12)

        self.logo = QLabel()
        self.logo.setPixmap(logo_pixmap(56))
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.logo)

        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.title)

        self.station = QLabel()
        self.station.setObjectName("hint")
        self.station.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.station)

        form = QFormLayout()
        form.setSpacing(10)
        self.username = QLineEdit()
        self.username.setObjectName("loginUsername")
        self.password = QLineEdit()
        self.password.setObjectName("loginPassword")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_user, self.lbl_pass = QLabel(), QLabel()
        form.addRow(self.lbl_user, self.username)
        form.addRow(self.lbl_pass, self.password)
        outer.addLayout(form)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.setVisible(False)
        outer.addWidget(self.error)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.try_login)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        last = self.ctx.prefs.get("last_username")
        if isinstance(last, str):
            self.username.setText(last)
            self.password.setFocus()
        else:
            self.username.setFocus()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        station = self.ctx.settings.get("station_name_ar" if self.ctx.localizer.is_rtl
                                        else "station_name_en", "") or ""
        self.setWindowTitle(tr("login.title"))
        self.title.setText(tr("login.title"))
        self.station.setText(f"{config.APP_NAME} · {station}" if station else config.APP_NAME)
        self.lbl_user.setText(tr("login.username"))
        self.lbl_pass.setText(tr("login.password"))
        self.username.setPlaceholderText(tr("login.username_hint"))
        self.password.setPlaceholderText(tr("login.password_hint"))
        self.ok_button.setText(tr("login.submit"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("common.cancel"))
        if self.error.isVisible() and self.error.text():
            self.error.setText(self.error.text())  # keep the current message

    @property
    def ok_button(self):
        return self.buttons.button(QDialogButtonBox.StandardButton.Ok)

    def try_login(self) -> None:
        result = self.auth.authenticate(self.username.text(), self.password.text())
        if not result.ok:
            self.error.setText(self.ctx.tr(result.error_code or "err.login_failed"))
            self.error.setVisible(True)
            self.password.selectAll()
            self.password.setFocus()
            return
        self.user = result.value
        if self.user is not None:
            self.ctx.prefs.set("last_username", self.user.username)
        self.accept()
