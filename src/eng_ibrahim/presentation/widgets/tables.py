"""Shared table behaviour: content-aware column widths and an empty-state message.

`QHeaderView.Stretch` gives every column the same width, which truncates codes and
titles while short columns (status, priority) waste space. `fit_columns` sizes each
column to its content and hands the spare width to the widest one; when space runs
out it shrinks only the wide columns so short values stay fully readable.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableView,
    QTableWidget,
)
from shiboken6 import isValid

_PADDING = 24
_MIN_WIDE = 56
_SHORT = 120
_MIN_SHORT = 40


def _water_fill(columns: list[int], wanted: dict[int, int], floor: int,
                room: int) -> dict[int, int]:
    """Cap the widest columns at one common width so `columns` fit in `room`."""
    if not columns:
        return {}
    low, high = 0.0, float(max(wanted[c] for c in columns))
    for _ in range(24):
        cap = (low + high) / 2
        if sum(max(min(floor, wanted[c]), min(wanted[c], cap)) for c in columns) > room:
            high = cap
        else:
            low = cap
    return {c: int(max(min(floor, wanted[c]), min(wanted[c], low))) for c in columns}


class _ColumnFitter(QObject):
    def __init__(self, table: QTableView) -> None:
        super().__init__(table)
        self._table = table
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.fit)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.viewport().installEventFilter(self)
        model = table.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset,
                       model.dataChanged, model.headerDataChanged, model.layoutChanged):
            signal.connect(self.schedule)
        self.schedule()

    def schedule(self, *_args) -> None:
        if isValid(self._timer):
            self._timer.start()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Resize:
            self.schedule()
        return False

    def fit(self) -> None:
        table = self._table
        if not isValid(table):
            return
        header = table.horizontalHeader()
        columns = [c for c in range(header.count()) if not header.isSectionHidden(c)]
        if not columns:
            return
        wanted = {c: max(table.sizeHintForColumn(c), header.sectionSizeHint(c)) + _PADDING // 2
                  for c in columns}
        available = table.viewport().width()
        if available <= 0:
            return
        total = sum(wanted.values())
        if total <= available:
            # Spare room is shared in proportion to content, so wide text gets most of it.
            widths = {c: wanted[c] + (available - total) * wanted[c] // total for c in columns}
        else:
            # Shrink in priority order: long text first (down to a readable floor), then
            # short values (codes, states, dates) only by what is still missing. The
            # identifier column (WO-2026-000003, PMP-101) stays whole while it takes at
            # most half the row.
            first = columns[0]
            fixed = {first: wanted[first]} if wanted[first] * 2 <= available else {}
            rest_cols = [c for c in columns if c not in fixed]
            long_cols = [c for c in rest_cols if wanted[c] > _SHORT]
            short_cols = [c for c in rest_cols if wanted[c] <= _SHORT]
            room = available - sum(fixed.values())
            short_room = room - _MIN_WIDE * len(long_cols)
            if sum(wanted[c] for c in short_cols) <= short_room:
                widths = {**fixed, **{c: wanted[c] for c in short_cols},
                          **_water_fill(long_cols, wanted, _MIN_WIDE,
                                        room - sum(wanted[c] for c in short_cols))}
            else:
                widths = {**fixed, **dict.fromkeys(long_cols, _MIN_WIDE),
                          **_water_fill(short_cols, wanted, _MIN_SHORT, short_room)}
        # Hand rounding leftovers to the widest column so the row fills the viewport exactly.
        rest = available - sum(widths.values())
        if rest > 0:
            widths[max(columns, key=lambda c: widths[c])] += rest
        for c in columns:
            header.resizeSection(c, widths[c])


class _EmptyState(QObject):
    def __init__(self, table: QTableView, text: Callable[[], str]) -> None:
        super().__init__(table)
        self._table = table
        self._text = text
        self.label = QLabel(table.viewport())
        self.label.setObjectName("emptyState")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        table.viewport().installEventFilter(self)
        model = table.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self.update)
        self.update()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.update()
        return False

    def update(self, *_args) -> None:
        # The model still signals while its table is being destroyed.
        if not (isValid(self._table) and isValid(self.label)):
            return
        empty = self._table.model().rowCount() == 0
        if empty:
            self.label.setText(self._text())
            self.label.setGeometry(self._table.viewport().rect().adjusted(16, 16, -16, -16))
        self.label.setVisible(empty)


def _strip_required_marks(table: QTableWidget) -> None:
    """Headers reuse form labels ("Title *"); the required-field star means nothing there."""
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        if item is not None and item.text().rstrip().endswith("*"):
            item.setText(item.text().rstrip().rstrip("*").rstrip())


def fit_columns(table: QTableView) -> None:
    """Content-aware column widths; idempotent per table."""
    if table.property("_fitted"):
        return
    table.setProperty("_fitted", True)
    if isinstance(table, QTableWidget):
        table.model().headerDataChanged.connect(lambda *_a: _strip_required_marks(table))
        _strip_required_marks(table)
    table.setWordWrap(False)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(34)
    if table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectItems:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    _ColumnFitter(table)


def set_empty_text(table: QTableView, text: Callable[[], str]) -> None:
    """Show `text()` centred in the table while it has no rows (re-read on every change)."""
    existing = table.findChild(_EmptyState)
    if existing is not None:
        existing._text = text
        existing.update()
        return
    _EmptyState(table, text)


def polish_table(table: QTableView, empty_text: Callable[[], str]) -> None:
    fit_columns(table)
    set_empty_text(table, empty_text)
