"""User management (admin only) — SPEC 21.3 / ADR-025.

Creating accounts, changing roles, resetting passwords and disabling users all
pass through AuthService, which enforces the admin permission and the
"at least one active admin" rule. This page only mirrors those rules.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...application.context import AppContext
from ...application.services.auth_service import AuthService, AuthUser
from ...domain.permissions import assignable_roles
from ..widgets.tables import polish_table
from .base import BasePage, make_card, make_title, vbox


class _PasswordDialog(QDialog):
    """New password + confirmation (used for create and reset)."""

    def __init__(self, ctx: AppContext, title_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.title_key = title_key
        self.setModal(True)
        form = QFormLayout(self)
        self.pw1, self.pw2 = QLineEdit(), QLineEdit()
        for w in (self.pw1, self.pw2):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl1, self.lbl2 = QLabel(), QLabel()
        form.addRow(self.lbl1, self.pw1)
        form.addRow(self.lbl2, self.pw2)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.setWindowTitle(tr(self.title_key))
        self.lbl1.setText(tr("users.password"))
        self.lbl2.setText(tr("users.confirm_password"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("common.cancel"))

    def _accept(self) -> None:
        if self.pw1.text() != self.pw2.text():
            QMessageBox.warning(self, self.windowTitle(), self.ctx.tr("users.password_mismatch"))
            return
        self.accept()

    @property
    def password(self) -> str:
        return self.pw1.text()


class NewUserDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(420)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.username, self.display = QLineEdit(), QLineEdit()
        self.role = QComboBox()
        for r in assignable_roles():
            self.role.addItem("", r.value)
        self.lbl_user, self.lbl_display, self.lbl_role = QLabel(), QLabel(), QLabel()
        form.addRow(self.lbl_user, self.username)
        form.addRow(self.lbl_display, self.display)
        form.addRow(self.lbl_role, self.role)
        self.lbl_pw, self.pw1, self.pw2 = QLabel(), QLineEdit(), QLineEdit()
        for w in (self.pw1, self.pw2):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_pw2 = QLabel()
        form.addRow(self.lbl_pw, self.pw1)
        form.addRow(self.lbl_pw2, self.pw2)
        outer.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self.retranslate()

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.setWindowTitle(tr("users.new_user"))
        self.lbl_user.setText(tr("login.username"))
        self.lbl_display.setText(tr("users.display_name"))
        self.lbl_role.setText(tr("users.role"))
        self.lbl_pw.setText(tr("users.password"))
        self.lbl_pw2.setText(tr("users.confirm_password"))
        for i, r in enumerate(assignable_roles()):
            self.role.setItemText(i, tr(f"users.role.{r.value}"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("common.cancel"))

    def _accept(self) -> None:
        if self.pw1.text() != self.pw2.text():
            QMessageBox.warning(self, self.windowTitle(), self.ctx.tr("users.password_mismatch"))
            return
        self.accept()

    @property
    def payload(self) -> tuple[str, str, str, str]:
        return (self.username.text(), self.display.text(),
                self.role.currentData(), self.pw1.text())


class ChangePasswordDialog(QDialog):
    """Self-service password change (current + new + confirm)."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setModal(True)
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.current, self.new1, self.new2 = QLineEdit(), QLineEdit(), QLineEdit()
        for field in (self.current, self.new1, self.new2):
            field.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_current = QLabel(ctx.tr("users.current_password"))
        self.lbl_new = QLabel(ctx.tr("users.password"))
        self.lbl_confirm = QLabel(ctx.tr("users.confirm_password"))
        form.addRow(self.lbl_current, self.current)
        form.addRow(self.lbl_new, self.new1)
        form.addRow(self.lbl_confirm, self.new2)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(ctx.tr("common.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ctx.tr("common.cancel"))
        self.setWindowTitle(ctx.tr("users.change_password"))

    def _accept(self) -> None:
        if self.new1.text() != self.new2.text():
            QMessageBox.warning(self, self.windowTitle(), self.ctx.tr("users.password_mismatch"))
            return
        self.accept()

    def payload(self) -> tuple[str, str]:
        return self.current.text(), self.new1.text()


class UsersPage(BasePage):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.auth = AuthService(ctx.db)
        self._rows: list[AuthUser] = []
        self._build()
        self.retranslate()

    # ---------------- UI ----------------
    def _build(self) -> None:
        lay = vbox(self)
        self.title = make_title()
        lay.addWidget(self.title)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        card = make_card()
        card_lay = QVBoxLayout(card)
        bar = QHBoxLayout()
        self.btn_add = QPushButton()
        self.btn_role = QPushButton()
        self.btn_password = QPushButton()
        self.btn_toggle = QPushButton()
        self.btn_self = QPushButton()
        self.btn_refresh = QPushButton()
        for b in (self.btn_add, self.btn_role, self.btn_password, self.btn_toggle,
                  self.btn_self, self.btn_refresh):
            bar.addWidget(b)
        bar.addStretch(1)
        card_lay.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        polish_table(self.table, lambda: self.ctx.tr("common.no_data"))
        card_lay.addWidget(self.table)
        lay.addWidget(card, 1)

        self.btn_add.clicked.connect(self._add_user)
        self.btn_role.clicked.connect(self._change_role)
        self.btn_password.clicked.connect(self._reset_password)
        self.btn_toggle.clicked.connect(self._toggle_active)
        self.btn_self.clicked.connect(self._change_own_password)
        self.btn_refresh.clicked.connect(self.refresh)

        admin = self.ctx.is_admin
        for b in (self.btn_add, self.btn_role, self.btn_password, self.btn_toggle):
            b.setEnabled(admin)
            b.setVisible(admin)

    def retranslate(self) -> None:
        tr = self.ctx.tr
        self.title.setText(tr("users.title"))
        self.hint.setText(tr("users.hint"))
        self.btn_add.setText(tr("users.add"))
        self.btn_role.setText(tr("users.change_role"))
        self.btn_password.setText(tr("users.reset_password"))
        self.btn_toggle.setText(tr("users.toggle_active"))
        self.btn_refresh.setText(tr("common.refresh"))
        self.btn_self.setText(tr("users.change_password"))
        if self.ctx.current_user is not None:
            self.hint.setText(tr("users.signed_in",
                                 name=self.ctx.current_user.display_name,
                                 role=tr(f"users.role.{self.ctx.current_user.role}")))
        headers = ("login.username", "users.display_name", "users.role",
                   "users.status", "users.created")
        self.table.setHorizontalHeaderLabels([tr(k) for k in headers])
        self.refresh()

    # ---------------- data ----------------
    def refresh(self) -> None:
        self._rows = self.auth.list_users()
        self.table.setRowCount(len(self._rows))
        for i, u in enumerate(self._rows):
            active = self.ctx.tr("users.active" if u.is_active else "users.inactive")
            for col, text in enumerate((u.username, u.display_name,
                                        self.ctx.tr(f"users.role.{u.role}"),
                                        active, u.created_at)):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, u.id)
                self.table.setItem(i, col, item)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        row = self.table.currentRow()
        has = 0 <= row < len(self._rows)
        for b in (self.btn_role, self.btn_password, self.btn_toggle):
            b.setEnabled(self.ctx.is_admin and has)
        if has:
            self.btn_toggle.setText(self.ctx.tr(
                "users.deactivate" if self._rows[row].is_active else "users.activate"))

    def _selected(self) -> AuthUser | None:
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    # ---------------- commands ----------------
    def _change_own_password(self) -> None:
        if self.ctx.current_user is None:
            return
        dialog = ChangePasswordDialog(self.ctx, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current, new = dialog.payload()
        result = self.auth.change_password(self.ctx.current_user.id, current, new)
        if not result.ok:
            QMessageBox.warning(self, self.ctx.tr("users.change_password"),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        QMessageBox.information(self, self.ctx.tr("users.change_password"),
                                self.ctx.tr("users.password_changed"))

    def _add_user(self) -> None:
        dlg = NewUserDialog(self.ctx, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        username, display, role, password = dlg.payload
        result = self.auth.create_user(self.ctx.current_user, username, display, role, password)
        self._finish(result, "users.user_created")

    def _change_role(self) -> None:
        user = self._selected()
        if user is None:
            return
        roles = [r.value for r in assignable_roles()]
        from PySide6.QtWidgets import QInputDialog
        current = roles.index(user.role) if user.role in roles else 0
        choice, ok = QInputDialog.getItem(
            self, self.ctx.tr("users.change_role"), self.ctx.tr("users.role"),
            [self.ctx.tr(f"users.role.{r}") for r in roles], current, False)
        if not ok:
            return
        role = roles[[self.ctx.tr(f"users.role.{r}") for r in roles].index(choice)]
        self._finish(self.auth.set_role(self.ctx.current_user, user.id, role), "users.role_changed")

    def _reset_password(self) -> None:
        user = self._selected()
        if user is None:
            return
        dlg = _PasswordDialog(self.ctx, "users.reset_password", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.auth.reset_password(self.ctx.current_user, user.id, dlg.password)
        if not result.ok:
            QMessageBox.warning(self, self.windowTitle(),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        QMessageBox.information(
            self, self.windowTitle(),
            self.ctx.tr("users.recovery_code", code=result.value or ""))
        self.refresh()

    def _toggle_active(self) -> None:
        user = self._selected()
        if user is None:
            return
        want_active = not user.is_active
        if not want_active:
            answer = QMessageBox.question(
                self, self.windowTitle(),
                self.ctx.tr("users.confirm_deactivate", username=user.username))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._finish(self.auth.set_active(self.ctx.current_user, user.id, want_active),
                     "users.updated")

    def _finish(self, result, success_key: str) -> None:
        if not result.ok:
            QMessageBox.warning(self, self.windowTitle(),
                                self.ctx.tr(result.error_code or "err.invalid"))
            return
        self.refresh()
        self.ctx.extras["toast"] = self.ctx.tr(success_key)
