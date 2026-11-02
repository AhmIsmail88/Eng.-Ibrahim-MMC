"""Ctrl+S saves the open form (SPEC 3.6) without wiring it into every dialog.

Installed once on the application: when a dialog with a Save/OK button has focus,
Ctrl+S presses that button exactly as a click would (validation included). Nothing
happens when the button is disabled or no form is open, so a stray Ctrl+S never
saves anything unexpected.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

_SAVE_ROLES = (QDialogButtonBox.StandardButton.Save, QDialogButtonBox.StandardButton.Ok)


def save_button(dialog: QDialog):
    for box in dialog.findChildren(QDialogButtonBox):
        for role in _SAVE_ROLES:
            button = box.button(role)
            if button is not None and button.isVisible() and button.isEnabled():
                return button
    return None


class DialogSaveShortcut(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.KeyPress:
            return False
        key_event: QKeyEvent = event  # type: ignore[assignment]
        if (key_event.key() != Qt.Key.Key_S
                or key_event.modifiers() != Qt.KeyboardModifier.ControlModifier):
            return False
        dialog = QApplication.activeModalWidget() or QApplication.activeWindow()
        if not isinstance(dialog, QDialog):
            return False
        button = save_button(dialog)
        if button is None:
            return False
        button.click()
        return True


def install(app: QApplication) -> DialogSaveShortcut:
    handler = DialogSaveShortcut(app)
    app.installEventFilter(handler)
    return handler
