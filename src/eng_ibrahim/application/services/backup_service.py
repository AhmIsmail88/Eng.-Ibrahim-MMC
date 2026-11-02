"""Backup / restore (SPEC 23): consistent SQLite snapshot + attachments + manifest.

The archive is a plain ZIP named `.eibak`. A backup is only reported as successful
after the copied database passes `PRAGMA integrity_check` and every checksum matches.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select

from ...config import APP_VERSION, AppPaths
from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import BackupHistory
from ..dto.result import Result
from .settings_service import SettingsService

MANIFEST = "manifest.json"
ARCHIVE_FORMAT = 1
BACKUP_FOLDER = "backup_folder"
BACKUP_RETENTION = "backup_retention"
AUTO_BACKUP = "auto_backup_enabled"
DEFAULT_RETENTION = 10
AUTO_INTERVAL = timedelta(hours=24)
STALE_AFTER = timedelta(days=7)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_ok(db_file: Path) -> bool:
    conn = sqlite3.connect(db_file)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    finally:
        conn.close()


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: str
    app_version: str
    schema_revision: str
    db_bytes: int
    files: int


class BackupService:
    def __init__(self, db: Database, paths: AppPaths,
                 schema_revision: str = "") -> None:
        self._db = db
        self._paths = paths
        self._schema = schema_revision

    # ---------------- settings ----------------
    def folder(self) -> Path:
        """The folder chosen in the first-run wizard, else the default under DATA_ROOT."""
        chosen = SettingsService(self._db).get(BACKUP_FOLDER)
        return Path(chosen) if chosen else self._paths.backups

    def retention(self) -> int:
        try:
            return max(1, int(SettingsService(self._db).get(BACKUP_RETENTION, DEFAULT_RETENTION)))
        except (TypeError, ValueError):
            return DEFAULT_RETENTION

    def auto_enabled(self) -> bool:
        return bool(SettingsService(self._db).get(AUTO_BACKUP, True))

    def set_auto_enabled(self, enabled: bool) -> None:
        SettingsService(self._db).set(AUTO_BACKUP, bool(enabled))

    # ---------------- schedule ----------------
    def age(self, now: datetime | None = None) -> timedelta | None:
        """Time since the last successful backup, or None when there has never been one."""
        last = self.last_backup()
        if not last:
            return None
        try:
            stamp = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return (now or datetime.now(UTC)) - stamp

    def is_due(self, now: datetime | None = None) -> bool:
        age = self.age(now)
        return age is None or age >= AUTO_INTERVAL

    def is_stale(self, now: datetime | None = None) -> bool:
        """Worth a warning in the status bar: never backed up, or not for a week."""
        age = self.age(now)
        return age is None or age >= STALE_AFTER

    def run_scheduled(self, now: datetime | None = None) -> Result[Path] | None:
        """Daily automatic backup (SPEC 23). Returns None when nothing was due."""
        if not self.auto_enabled() or not self.is_due(now):
            return None
        return self.create()

    # ---------------- create ----------------
    def create(self, destination: Path | None = None) -> Result[Path]:
        """Write an archive; a backup into the regular folder also applies retention."""
        result = self._create(Path(destination) if destination else self.folder())
        if result.ok and destination is None:
            self.prune(keep=self.retention(), directory=self.folder())
        return result

    def _create(self, backups: Path) -> Result[Path]:
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        target = backups / f"ENG_IBRAHIM_BACKUP_{stamp}.eibak"
        suffix = 2
        while target.exists():  # two backups in the same second must not overwrite
            target = backups / f"ENG_IBRAHIM_BACKUP_{stamp}_{suffix}.eibak"
            suffix += 1
        tmp_zip = target.with_suffix(".zip.tmp")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                stage = Path(tmp)
                snapshot = stage / "maintenance.sqlite3"
                src = sqlite3.connect(self._paths.db_file)
                dst = sqlite3.connect(snapshot)
                try:
                    src.backup(dst)  # online backup API, WAL-safe
                finally:
                    dst.close()
                    src.close()
                if not _integrity_ok(snapshot):
                    return self._fail("integrity_check failed on the snapshot")
                files = []
                for file in sorted(self._paths.attachments.rglob("*")):
                    if file.is_file():
                        rel = file.relative_to(self._paths.root).as_posix()
                        files.append({"path": rel, "sha256": _sha256(file),
                                      "bytes": file.stat().st_size})
                manifest = {
                    "format": ARCHIVE_FORMAT,
                    "app_version": APP_VERSION,
                    "schema_revision": self._schema,
                    "created_at": datetime.now(UTC).isoformat(),
                    "database": {"path": "data/maintenance.sqlite3",
                                 "sha256": _sha256(snapshot),
                                 "bytes": snapshot.stat().st_size},
                    "files": files,
                }
                (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
                with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(stage / MANIFEST, MANIFEST)
                    zf.write(snapshot, "data/maintenance.sqlite3")
                    for file in sorted(self._paths.attachments.rglob("*")):
                        if file.is_file():
                            rel = file.relative_to(self._paths.root).as_posix()
                            zf.write(file, rel)
            tmp_zip.replace(target)
        except (OSError, sqlite3.Error) as exc:
            tmp_zip.unlink(missing_ok=True)
            return self._fail(str(exc))
        self._record(target, "success")
        return Result.success(target)

    def prune(self, keep: int = 10, directory: Path | None = None) -> int:
        """Keep the newest `keep` archives; never delete the last successful one."""
        folder = Path(directory) if directory else self.folder()
        if keep < 1 or not folder.exists():
            return 0
        # Names embed the creation timestamp (YYYY-MM-DD_HHMMSS), so name order is
        # chronological and deterministic even when two files share an mtime.
        archives = sorted(folder.glob("ENG_IBRAHIM_BACKUP_*.eibak"),
                          key=lambda p: p.name, reverse=True)
        removed = 0
        for archive in archives[keep:]:
            try:
                archive.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def last_backup(self) -> str | None:
        with self._db.session() as s:
            row = s.scalars(select(BackupHistory)
                            .where(BackupHistory.status == "success")
                            .order_by(BackupHistory.created_at.desc()).limit(1)).first()
            return row.created_at if row else None

    # ---------------- inspect ----------------
    def inspect(self, archive: Path) -> Result[BackupInfo]:
        try:
            with zipfile.ZipFile(archive) as zf:
                manifest = json.loads(zf.read(MANIFEST))
        except (OSError, KeyError, ValueError) as exc:
            return Result.failure("err.backup_invalid", str(exc))
        database = manifest.get("database", {})
        return Result.success(BackupInfo(
            path=archive, created_at=str(manifest.get("created_at", "")),
            app_version=str(manifest.get("app_version", "")),
            schema_revision=str(manifest.get("schema_revision", "")),
            db_bytes=int(database.get("bytes", 0)),
            files=len(manifest.get("files", []))))

    # ---------------- verify ----------------
    def verify(self, archive: Path) -> Result[dict]:
        try:
            with zipfile.ZipFile(archive) as zf:
                manifest = json.loads(zf.read(MANIFEST))
                database = manifest.get("database", {})
                with tempfile.TemporaryDirectory() as tmp:
                    extracted = Path(zf.extract(database["path"], tmp))
                    if _sha256(extracted) != database.get("sha256"):
                        return Result.failure("err.backup_corrupt")
                    if not _integrity_ok(extracted):
                        return Result.failure("err.backup_corrupt")
                    for entry in manifest.get("files", []):
                        member = Path(zf.extract(entry["path"], tmp))
                        if _sha256(member) != entry["sha256"]:
                            return Result.failure("err.backup_corrupt")
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            return Result.failure("err.backup_invalid")
        return Result.success(manifest)

    # ---------------- restore ----------------
    def restore(self, archive: Path) -> Result[None]:
        checked = self.verify(archive)
        if not checked.ok:
            return checked
        revision = str((checked.value or {}).get("schema_revision", ""))
        if self._schema and revision and revision > self._schema:
            return Result.failure("err.backup_newer_schema", revision)
        safety = self.create(self.folder() / "pre-restore")
        if not safety.ok:
            return Result.failure("err.backup_safety_failed")
        live = self._paths.attachments
        parked = live.with_name(live.name + ".pre-restore")
        try:
            self._db.dispose()
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(tmp)
                stage = Path(tmp)
                self._paths.data.mkdir(parents=True, exist_ok=True)
                # Stage the attachments beside the live folder before touching anything,
                # so a failed copy leaves the current files in place.
                incoming = live.with_name(live.name + ".restoring")
                if incoming.exists():
                    shutil.rmtree(incoming)
                if (stage / "attachments").exists():
                    shutil.copytree(stage / "attachments", incoming)
                else:
                    incoming.mkdir(parents=True)
                db_file = self._paths.db_file
                # Stale WAL/SHM pages from the old database would be replayed into the new one.
                for side in (db_file.with_name(db_file.name + "-wal"),
                             db_file.with_name(db_file.name + "-shm")):
                    side.unlink(missing_ok=True)
                shutil.copy2(stage / "data/maintenance.sqlite3", db_file)
                if parked.exists():
                    shutil.rmtree(parked)
                if live.exists():
                    live.rename(parked)
                incoming.rename(live)
                shutil.rmtree(parked, ignore_errors=True)
        except OSError as exc:
            if parked.exists() and not live.exists():
                parked.rename(live)
            return self._fail(str(exc))
        return Result.success()

    # ---------------- helpers ----------------
    def _record(self, target: Path, status: str) -> None:
        try:
            with self._db.unit_of_work() as s:
                s.add(BackupHistory(file_path=str(target), checksum_sha256=_sha256(target),
                                    bytes=target.stat().st_size, status=status))
        except Exception:  # a full backup must not fail because history could not be written
            pass

    def _fail(self, message: str) -> Result:
        try:
            with self._db.unit_of_work() as s:
                s.add(BackupHistory(file_path="", status="failed", error_summary=message))
        except Exception:
            pass
        return Result.failure("err.backup_failed", message)
