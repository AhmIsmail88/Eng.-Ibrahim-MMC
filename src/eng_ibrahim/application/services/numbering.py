"""Sequential, human-readable codes generated inside the caller's transaction (SPEC 10.8).

Never `MAX()+1`: `code_sequences` is incremented under the same transaction that
inserts the row, so two writers cannot produce the same number.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ...infrastructure.database.orm_models import CodeSequence


def next_number(session: Session, prefix: str, year: int | None = None) -> str:
    year = year or date.today().year
    row = session.get(CodeSequence, (prefix, year))
    if row is None:
        row = CodeSequence(prefix=prefix, year=year, next_value=1)
        session.add(row)
        session.flush()
    value = int(row.next_value)
    row.next_value = value + 1
    return f"{prefix}-{year}-{value:06d}"


def next_plain_number(session: Session, prefix: str) -> str:
    """Codes without a year segment (SPEC 10.8 uses `PM-000001` for plans)."""
    row = session.get(CodeSequence, (prefix, 0))
    if row is None:
        row = CodeSequence(prefix=prefix, year=0, next_value=1)
        session.add(row)
        session.flush()
    value = int(row.next_value)
    row.next_value = value + 1
    return f"{prefix}-{value:06d}"
