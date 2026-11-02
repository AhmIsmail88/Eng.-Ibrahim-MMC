"""purchase requests (P1)

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_requests",
        sa.Column("request_no", sa.String(length=24), nullable=False),
        sa.Column("supplier_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("estimated_total_minor", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"],
                                name=op.f("fk_purchase_requests_supplier_id_suppliers")),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"],
                                name=op.f("fk_purchase_requests_warehouse_id_warehouses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_requests")),
        sa.UniqueConstraint("request_no", name=op.f("uq_purchase_requests_request_no")),
        sa.CheckConstraint("status IN ('Draft','Approved','Received','Cancelled')",
                           name=op.f("ck_purchase_requests_status_valid")),
        sa.CheckConstraint("estimated_total_minor >= 0",
                           name=op.f("ck_purchase_requests_total_nonneg")),
    )
    op.create_table(
        "purchase_request_lines",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("part_id", sa.String(length=36), nullable=False),
        sa.Column("quantity_decimal", sa.String(length=40), nullable=False),
        sa.Column("estimated_cost_minor", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"],
                                name=op.f("fk_purchase_request_lines_part_id_parts")),
        sa.ForeignKeyConstraint(["request_id"], ["purchase_requests.id"],
                                name=op.f("fk_purchase_request_lines_request_id_purchase_requests")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_request_lines")),
        sa.CheckConstraint("estimated_cost_minor >= 0",
                           name=op.f("ck_purchase_request_lines_cost_nonneg")),
    )


def downgrade() -> None:
    op.drop_table("purchase_request_lines")
    op.drop_table("purchase_requests")
