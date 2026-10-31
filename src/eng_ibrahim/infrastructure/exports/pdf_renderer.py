"""PDF export through Qt's text engine (Arabic shaping + RTL) — SPEC 17.2."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from ...application.services.report_service import ReportResult

_FONT = "'Noto Sans Arabic', 'Segoe UI', Tahoma, Arial, sans-serif"


def write_pdf(path: Path, report: ReportResult, title: str,
              column_titles: list[str], meta_lines: list[str],
              total_labels: dict[str, str]) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    writer.setResolution(96)
    writer.setTitle(title)

    head = "".join(f"<th>{escape(t)}</th>" for t in column_titles)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row.get(c.key, '')))}</td>"
                         for c in report.columns) + "</tr>"
        for row in report.rows
    ) or f"<tr><td colspan='{len(column_titles)}'>—</td></tr>"
    totals = ""
    if report.totals:
        cells = "".join(f"{escape(total_labels.get(k, k))}: {escape(str(v))} &nbsp; "
                        for k, v in report.totals.items())
        totals = f"<p><b>{escape(total_labels.get('totals', 'Totals'))}</b> — {cells}</p>"
    meta = " · ".join(escape(line) for line in meta_lines if line)

    document = QTextDocument()
    document.setHtml(f"""
        <html dir="rtl"><head><meta charset="utf-8"><style>
          body {{ font-family: {_FONT}; font-size: 10pt; color: #162B43; }}
          h1 {{ font-size: 16pt; margin: 0 0 6px 0; color: #11345A; }}
          .meta {{ color: #68798A; font-size: 9pt; margin: 0 0 10px 0; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border: 1px solid #C9D4E1; padding: 4px 6px; font-size: 9pt; }}
          th {{ background: #EEF3F9; color: #11345A; }}
          tr {{ page-break-inside: avoid; }}
        </style></head><body>
          <h1>{escape(title)}</h1>
          <p class="meta">{meta}</p>
          <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
          {totals}
        </body></html>""")
    document.print_(writer)
