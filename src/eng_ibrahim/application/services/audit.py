from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ...infrastructure.database.orm_models import AuditLog


def write_audit(session: Session, entity_type: str, entity_id: str | None, action: str, *,
                before: Any = None, after: Any = None, actor_id: str | None = None,
                reason: str | None = None) -> None:
    """Append-only audit entry. Callers must never include secrets in before/after."""
    session.add(AuditLog(
        entity_type=entity_type, entity_id=entity_id, action=action,
        before_json=json.dumps(before, ensure_ascii=False) if before is not None else None,
        after_json=json.dumps(after, ensure_ascii=False) if after is not None else None,
        actor_id=actor_id, reason=reason,
    ))
