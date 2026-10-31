"""SQLite engine + session factory + Unit of Work (SPEC 19.1)."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def _apply_pragmas(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("PRAGMA synchronous = NORMAL")
    cur.close()


def create_sqlite_engine(db_file: Path) -> Engine:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    event.listen(engine, "connect", _apply_pragmas)
    return engine


class Database:
    """Owns engine + short-lived sessions. No global session is ever shared."""

    def __init__(self, db_file: Path) -> None:
        self.db_file = db_file
        self.engine = create_sqlite_engine(db_file)
        self._factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def session(self) -> Session:
        return self._factory()

    @contextmanager
    def unit_of_work(self) -> Iterator[Session]:
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
