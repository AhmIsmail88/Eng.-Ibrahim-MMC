"""In-app user guide (F1): the HTML guide for the current language, with in-page links."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from ...application.context import AppContext
from ...localization.service import guide_path


class HelpDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ctx.tr("help.title"))
        self.resize(820, 680)
        lay = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setObjectName("guide")
        self.browser.setOpenExternalLinks(True)
        self.browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft if ctx.localizer.is_rtl
                                        else Qt.LayoutDirection.LeftToRight)
        path = guide_path(ctx.localizer.language)
        self.browser.setSearchPaths([str(path.parent)])
        self.browser.setSource(QUrl.fromLocalFile(str(path)))
        lay.addWidget(self.browser)
