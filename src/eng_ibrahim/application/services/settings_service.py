from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ...infrastructure.database.engine import Database
from ...infrastructure.database.orm_models import AppSetting

FIRST_RUN_DONE = "first_run_completed"


class SettingsService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        with self._db.session() as s:
            row = s.get(AppSetting, key)
            return json.loads(row.value_json) if row else default

    def set(self, key: str, value: Any) -> None:
        with self._db.unit_of_work() as s:
            self.set_in(s, key, value)

    @staticmethod
    def set_in(session: Session, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value_json=payload))
        else:
            row.value_json = payload

    def all(self) -> dict[str, Any]:
        from sqlalchemy import select
        with self._db.session() as s:
            return {r.key: json.loads(r.value_json) for r in s.scalars(select(AppSetting))}

    def is_first_run_completed(self) -> bool:
        return bool(self.get(FIRST_RUN_DONE, False))
