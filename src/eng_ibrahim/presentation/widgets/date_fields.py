"""Date fields read left-to-right everywhere (SPEC 3.4: numbers and dates stay LTR).

In a right-to-left window a QDateEdit inherits RTL and shows its sections reversed
("05-11-2026" for 2026-11-05). Installed once on the application, this filter fixes
every date field when it is first polished, including ones added later.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QDateEdit, QDateTimeEdit


class LtrDateFields(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Polish and isinstance(watched, QDateTimeEdit):
            watched.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            # Qt stores the sections reversed when a format is set while the field is still
            # RTL ("10:08 05-11-2026"), so the app's formats are set again after the switch.
            watched.setDisplayFormat("yyyy-MM-dd" if isinstance(watched, QDateEdit)
                                     else "yyyy-MM-dd HH:mm")
        return False


def install(app: QApplication) -> LtrDateFields:
    handler = LtrDateFields(app)
    app.installEventFilter(handler)
    return handler
