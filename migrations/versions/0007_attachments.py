"""attachments metadata (SPEC 22)

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=400), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("added_at", sa.String(length=32), nullable=False),
        sa.Column("added_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("relative_path", name=op.f("uq_attachments_relative_path")),
    )
    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.create_index("ix_attachments_owner", ["owner_type", "owner_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.drop_index("ix_attachments_owner")
    op.drop_table("attachments")
