"""reference lists: archive flag on asset types, units and currencies (SPEC 3.8)

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_TABLES = ("asset_types", "units", "currencies")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("is_active", sa.Integer(), nullable=False,
                                          server_default="1"))
            batch_op.create_check_constraint(op.f(f"ck_{table}_is_active_bool"),
                                            "is_active IN (0,1)")


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(op.f(f"ck_{table}_is_active_bool"), type_="check")
            batch_op.drop_column("is_active")
