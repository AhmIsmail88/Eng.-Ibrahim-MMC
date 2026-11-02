"""vehicle profile: department and maintenance contact (SPEC 6.1)

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("department", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("maintenance_contact", sa.String(length=160),
                                      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.drop_column("maintenance_contact")
        batch_op.drop_column("department")
