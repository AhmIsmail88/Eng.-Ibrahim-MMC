"""Attachments metadata (SPEC 22). Files live under <DATA_ROOT>/attachments."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPk, utcnow_iso


class Attachment(Base, UuidPk):
    __tablename__ = "attachments"
    owner_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    relative_path: Mapped[str] = mapped_column(sa.String(400), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(sa.String(100))
    size_bytes: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    added_at: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=utcnow_iso)
    added_by: Mapped[str | None] = mapped_column(sa.String(36))


sa.Index("ix_attachments_owner", Attachment.owner_type, Attachment.owner_id)
