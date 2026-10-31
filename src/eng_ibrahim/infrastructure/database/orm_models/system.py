from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UuidPk, utcnow_iso


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, onupdate=utcnow_iso)


class AppUser(Base, UuidPk):
    __tablename__ = "app_users"
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)
    __table_args__ = (
        CheckConstraint("role IN ('admin','editor','reports','viewer')",
                        name="role_valid"),
        CheckConstraint("is_active IN (0,1)", name="is_active_bool"),
    )


Index("uq_app_users_username_ci", func.lower(AppUser.username), unique=True)


class LocalRecoveryCode(Base, UuidPk):
    __tablename__ = "local_recovery_codes"
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)


class AuditLog(Base):
    """Append-only (SPEC 24.1). No FK cascade; history outlives targets."""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


class Notification(Base, UuidPk):
    __tablename__ = "notifications"
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64))
    condition_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[str | None] = mapped_column(String(32))
    dismissed_at: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)
    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','critical')", name="severity_valid"),
    )


Index("uq_notifications_active_condition", Notification.condition_key, unique=True,
      sqlite_where=Notification.dismissed_at.is_(None))


class CodeSequence(Base):
    __tablename__ = "code_sequences"
    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ImportBatch(Base, UuidPk):
    __tablename__ = "import_batches"
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    summary_json: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)


class BackupHistory(Base, UuidPk):
    __tablename__ = "backup_history"
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("status IN ('success','failed')", name="status_valid"),)


class ReportExportHistory(Base, UuidPk):
    __tablename__ = "report_export_history"
    report_id: Mapped[str] = mapped_column(String(64), nullable=False)
    filters_json: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    generated_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, nullable=False)
    output_path: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(36))
