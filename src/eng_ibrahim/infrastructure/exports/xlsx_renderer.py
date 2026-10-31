"""XLSX export (SPEC 17.2): real numbers, frozen header, autofilter, formula-injection safe."""
from __future__ import annotations

from pathlib import Path

import xlsxwriter

from ...application.services.report_service import ReportResult

_DANGEROUS = ("=", "+", "-", "@")


def _safe(value: str) -> str:
    return f"'{value}" if value and value.startswith(_DANGEROUS) else value


def write_xlsx(path: Path, report: ReportResult, title: str,
               column_titles: list[str], meta_lines: list[str],
               total_labels: dict[str, str]) -> None:
    workbook = xlsxwriter.Workbook(str(path), {"in_memory": True})
    sheet = workbook.add_worksheet(report.code)
    bold = workbook.add_format({"bold": True})
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#EEF3F9", "border": 1})
    money = workbook.add_format({"num_format": "#,##0.00"})
    number = workbook.add_format({"num_format": "#,##0.###"})
    text_fmt = workbook.add_format({"text_wrap": False})

    sheet.right_to_left()
    sheet.write(0, 0, title, bold)
    row = 1
    for line in meta_lines:
        sheet.write(row, 0, line)
        row += 1
    row += 1
    header_row = row
    for col, label in enumerate(column_titles):
        sheet.write(header_row, col, label, header_fmt)
    for index, data in enumerate(report.rows, start=1):
        for col, column in enumerate(report.columns):
            value = data.get(column.key, "")
            if column.numeric:
                try:
                    sheet.write_number(header_row + index, col, float(value),
                                       money if "." in str(value) else number)
                    continue
                except (TypeError, ValueError):
                    pass
            sheet.write_string(header_row + index, col, _safe(str(value)), text_fmt)
    last_col = max(0, len(report.columns) - 1)
    sheet.autofilter(header_row, 0, header_row + len(report.rows), last_col)
    sheet.freeze_panes(header_row + 1, 0)
    for col, column in enumerate(report.columns):
        sheet.set_column(col, col, column.width)

    if report.totals:
        total_row = header_row + len(report.rows) + 2
        sheet.write(total_row, 0, total_labels.get("totals", "Totals"), bold)
        for col, column in enumerate(report.columns):
            if column.key in report.totals:
                value = report.totals[column.key]
                try:
                    sheet.write_number(total_row, col, float(value), money)
                except (TypeError, ValueError):
                    sheet.write(total_row, col, value, bold)
    workbook.close()
