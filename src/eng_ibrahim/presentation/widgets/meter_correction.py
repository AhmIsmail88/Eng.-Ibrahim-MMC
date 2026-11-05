"""'Correct the last reading' option shared by the asset and vehicle reading dialogs."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...application.context import AppContext


class CorrectionBox(QWidget):
    """Unchecked: a normal reading. Checked: replaces the last reading, reason required."""

    def __init__(self, ctx: AppContext, last: tuple[str, str] | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self.check = QCheckBox(ctx.tr("meter.correct"))
        self.reason = QLineEdit()
        self.reason.setPlaceholderText(ctx.tr("meter.correct_reason"))
        self.reason.setEnabled(False)
        self._ctx = ctx
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        self.check.toggled.connect(self.reason.setEnabled)
        self.check.toggled.connect(self.hint.setVisible)
        lay.addWidget(self.check)
        lay.addWidget(self.reason)
        lay.addWidget(self.hint)
        self.set_last(last)

    def set_last(self, last: tuple[str, str] | None) -> None:
        """The reading a correction would replace (changes with the chosen meter)."""
        # Each number keeps its own direction inside Arabic text (U+2066…U+2069).
        self.hint.setText(self._ctx.tr(
            "meter.correct_hint",
            value=f"⁦{last[0]}⁩" if last else "—",
            at=f"⁦{last[1][:16].replace('T', ' ')}⁩" if last else "—"))
        self.check.setEnabled(last is not None)
        if last is None:
            self.check.setChecked(False)

    def correction_reason(self) -> str | None:
        """None for a normal reading; the (possibly empty) reason for a correction."""
        return self.reason.text() if self.check.isChecked() else None
