from __future__ import annotations

from sqlalchemy import desc, select

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import AppUser, BackupHistory


class StatusService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def last_successful_backup(self) -> str | None:
        with self._db.session() as s:
            return s.scalar(select(BackupHistory.created_at)
                            .where(BackupHistory.status == "success")
                            .order_by(desc(BackupHistory.created_at)).limit(1))

    def primary_profile_name(self) -> str:
        with self._db.session() as s:
            u = s.scalar(select(AppUser).where(AppUser.is_active == 1)
                         .order_by(AppUser.created_at).limit(1))
            return u.display_name if u else ""
