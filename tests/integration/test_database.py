import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from eng_ibrahim.domain.exceptions import DatabaseStartupError
from eng_ibrahim.infrastructure.database import migration_runner as mr
from eng_ibrahim.infrastructure.database.engine import Database
from eng_ibrahim.infrastructure.database.orm_models import AppUser, Location


def test_new_database_created_and_at_head(paths):
    report = mr.ensure_database(paths)
    assert report.created_new and report.backup_file is None
    assert report.current_revision == mr.head_revision()
    assert mr.current_revision(paths.db_file) == mr.head_revision()
    assert mr.quick_check(paths.db_file)


def test_second_start_is_noop_and_keeps_data(paths):
    mr.ensure_database(paths)
    db = Database(paths.db_file)
    with db.unit_of_work() as s:
        s.add(Location(code="L1", name_ar="موقع"))
    db.dispose()
    report = mr.ensure_database(paths)
    assert not report.created_new and report.backup_file is None
    db = Database(paths.db_file)
    with db.session() as s:
        assert s.query(Location).count() == 1
    db.dispose()


def test_pragmas_applied(paths):
    mr.ensure_database(paths)
    db = Database(paths.db_file)
    with db.session() as s:
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert s.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert s.execute(text("PRAGMA busy_timeout")).scalar() == 5000
    db.dispose()


def test_constraints_enforced_by_db(paths):
    mr.ensure_database(paths)
    db = Database(paths.db_file)
    with db.unit_of_work() as s:
        s.add(AppUser(username="Admin", display_name="A", password_hash="h"))
    with pytest.raises(IntegrityError):  # case-insensitive unique username
        with db.unit_of_work() as s:
            s.add(AppUser(username="ADMIN", display_name="B", password_hash="h"))
    with pytest.raises(IntegrityError):  # CHECK role
        with db.unit_of_work() as s:
            s.add(AppUser(username="x", display_name="X", role="root", password_hash="h"))
    with pytest.raises(IntegrityError):  # FK
        with db.unit_of_work() as s:
            s.add(Location(code="C", name_ar="ع", parent_id="missing"))
    with pytest.raises(IntegrityError):  # unique code
        with db.unit_of_work() as s:
            s.add(Location(code="D", name_ar="ع"))
            s.add(Location(code="D", name_ar="ع"))
    db.dispose()


def test_corrupt_file_is_never_overwritten(paths):
    paths.data.mkdir(parents=True, exist_ok=True)
    paths.db_file.write_bytes(b"this is definitely not sqlite data" * 10)
    before = paths.db_file.read_bytes()
    with pytest.raises(DatabaseStartupError):
        mr.ensure_database(paths)
    assert paths.db_file.read_bytes() == before


def test_pending_migration_takes_prebackup_and_stamps(paths):
    mr.ensure_database(paths)
    # simulate an older DB: remove alembic stamp -> pending migration against existing schema
    conn = sqlite3.connect(paths.db_file)
    conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()
    with pytest.raises(DatabaseStartupError):  # tables exist -> upgrade fails safely
        mr.ensure_database(paths)
    backups = list(paths.backups.glob("pre-migration-*.sqlite3"))
    assert len(backups) == 1 and paths.db_file.exists()
    assert mr.quick_check(backups[0])


def test_backup_api_produces_valid_copy(paths, tmp_path):
    mr.ensure_database(paths)
    out = mr.backup_database(paths.db_file, tmp_path / "b" / "copy.sqlite3")
    assert out.exists() and mr.quick_check(out)
    assert not list((tmp_path / "b").glob("*.tmp"))


def test_downgrade_roundtrip(paths):
    from alembic import command
    mr.ensure_database(paths)
    cfg = mr._alembic_config(paths.db_file)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert mr.current_revision(paths.db_file) == mr.head_revision()
