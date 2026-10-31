"""Migration for legacy databases created before ADR-025 (roles v1.0).

Fresh databases get the target shape directly from `0001` (edited before the
first release, see docs/DECISIONS.md IMP-012). This migration exists only to
upgrade a database created by the earlier scaffold, where `app_users` still
allowed ('admin','maintenance_engineer','storekeeper','viewer') and a NULL
password. It detects that legacy shape and rebuilds the table; on a fresh
database it is a no-op.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_RESET_SENTINEL = "!reset-required"


def _create_table_sql(bind) -> str:
    row = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='app_users'"
    ).fetchone()
    return (row[0] or "") if row else ""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":  # pragma: no cover - 1.0 ships SQLite only
        return
    sql = _create_table_sql(bind).lower()
    if not sql or "maintenance_engineer" not in sql:
        return  # already in the ADR-025 shape

    # Roles are collapsed first so the copy below never violates the new CHECK.
    bind.exec_driver_sql(
        "UPDATE app_users SET role = 'editor' "
        "WHERE role IN ('maintenance_engineer','storekeeper')"
    )
    bind.exec_driver_sql(
        "UPDATE app_users SET role = 'viewer' "
        "WHERE role NOT IN ('admin','editor','reports','viewer')"
    )
    # A legacy password-less account cannot log in anyway; mark it for reset.
    bind.exec_driver_sql(
        "UPDATE app_users SET password_hash = ? "
        "WHERE password_hash IS NULL OR TRIM(password_hash) = ''",
        (_RESET_SENTINEL,),
    )

    # Deferred FK checks let us replace the parent table inside one transaction
    # (local_recovery_codes references app_users.id; ids are preserved).
    bind.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    bind.exec_driver_sql(
        """
        CREATE TABLE app_users_new (
            id VARCHAR(36) NOT NULL,
            username VARCHAR(64) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL,
            is_active INTEGER NOT NULL,
            created_at VARCHAR(32) NOT NULL,
            CONSTRAINT pk_app_users PRIMARY KEY (id),
            CONSTRAINT ck_app_users_is_active_bool CHECK (is_active IN (0,1)),
            CONSTRAINT ck_app_users_role_valid
                CHECK (role IN ('admin','editor','reports','viewer'))
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO app_users_new
            (id, username, display_name, password_hash, role, is_active, created_at)
        SELECT id, username, display_name, password_hash,
               CASE role
                   WHEN 'admin' THEN 'admin'
                   WHEN 'editor' THEN 'editor'
                   WHEN 'reports' THEN 'reports'
                   ELSE 'viewer'
               END,
               is_active, created_at
        FROM app_users
        """
    )
    bind.exec_driver_sql("DROP TABLE app_users")
    bind.exec_driver_sql("ALTER TABLE app_users_new RENAME TO app_users")
    bind.exec_driver_sql("DROP INDEX IF EXISTS uq_app_users_username_ci")
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX uq_app_users_username_ci ON app_users (lower(username))"
    )


def downgrade() -> None:
    """Best-effort rollback to the 0001 shape (roles are collapsed again)."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":  # pragma: no cover
        return
    sql = _create_table_sql(bind).lower()
    if "maintenance_engineer" in sql:
        return
    bind.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    bind.exec_driver_sql(
        """
        CREATE TABLE app_users_old (
            id VARCHAR(36) NOT NULL,
            username VARCHAR(64) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255),
            role VARCHAR(32) NOT NULL,
            is_active INTEGER NOT NULL,
            created_at VARCHAR(32) NOT NULL,
            CONSTRAINT pk_app_users PRIMARY KEY (id),
            CONSTRAINT ck_app_users_is_active_bool CHECK (is_active IN (0,1)),
            CONSTRAINT ck_app_users_role_valid
                CHECK (role IN ('admin','maintenance_engineer','storekeeper','viewer'))
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO app_users_old
            (id, username, display_name, password_hash, role, is_active, created_at)
        SELECT id, username, display_name, password_hash,
               CASE role
                   WHEN 'admin' THEN 'admin'
                   WHEN 'viewer' THEN 'viewer'
                   ELSE 'maintenance_engineer'
               END,
               is_active, created_at
        FROM app_users
        """
    )
    bind.exec_driver_sql("DROP TABLE app_users")
    bind.exec_driver_sql("ALTER TABLE app_users_old RENAME TO app_users")
    bind.exec_driver_sql("DROP INDEX IF EXISTS uq_app_users_username_ci")
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX uq_app_users_username_ci ON app_users (lower(username))"
    )
