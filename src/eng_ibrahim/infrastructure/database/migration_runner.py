"""Safe startup + migration (SPEC 19.1, 24.4).

Rules:
* Never create an empty DB over an existing damaged file.
* Take a pre-migration backup (SQLite online backup API) before upgrading an existing DB.
* Stop (raise DatabaseStartupError) if the upgrade fails; the backup remains.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from ...config import AppPaths, project_root
from ...domain.exceptions import DatabaseStartupError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationReport:
    created_new: bool
    previous_revision: str | None
    current_revision: str
    backup_file: Path | None


def _alembic_config(db_file: Path, script_location: Path | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(script_location or project_root() / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    return cfg


def head_revision(script_location: Path | None = None) -> str:
    cfg = _alembic_config(Path("unused.db"), script_location)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


def _is_sqlite_file(db_file: Path) -> bool:
    with db_file.open("rb") as fh:
        return fh.read(16) == b"SQLite format 3\x00"


def current_revision(db_file: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def quick_check(db_file: Path) -> bool:
    conn = sqlite3.connect(db_file)
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        return bool(row) and row[0] == "ok"
    finally:
        conn.close()


def backup_database(db_file: Path, target: Path) -> Path:
    """Online backup API + integrity validation of the produced copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    src = sqlite3.connect(db_file)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(tmp)
    try:
        ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()
    if not ok:
        tmp.unlink(missing_ok=True)
        raise DatabaseStartupError("Backup integrity validation failed")
    tmp.replace(target)
    return target


def ensure_database(paths: AppPaths, script_location: Path | None = None) -> MigrationReport:
    paths.ensure()
    db_file = paths.db_file
    head = head_revision(script_location)
    existed = db_file.exists() and db_file.stat().st_size > 0

    if existed:
        if not _is_sqlite_file(db_file):
            raise DatabaseStartupError(f"Not a SQLite database: {db_file}")
        try:
            if not quick_check(db_file):
                raise DatabaseStartupError(f"Database failed quick_check: {db_file}")
            previous = current_revision(db_file)
        except sqlite3.DatabaseError as exc:
            raise DatabaseStartupError(f"Cannot read database: {exc}") from exc
        if previous == head:
            return MigrationReport(False, previous, head, None)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_database(db_file, paths.backups / f"pre-migration-{stamp}.sqlite3")
    else:
        previous, backup = None, None

    try:
        command.upgrade(_alembic_config(db_file, script_location), "head")
    except Exception as exc:  # stop; keep backup; never continue on half-migrated DB
        log.exception("Migration failed")
        raise DatabaseStartupError(f"Migration failed: {exc}") from exc
    return MigrationReport(not existed, previous, head, backup)
