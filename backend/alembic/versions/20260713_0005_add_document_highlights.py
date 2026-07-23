"""Add user document highlights.

Revision ID: 20260713_0005
Revises: 20260706_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20260713_0005"
down_revision = "20260706_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "document_highlights" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "document_highlights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=True),
        sa.Column("suffix", sa.Text(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="yellow"),
    )
    op.create_index("idx_document_highlights_user_document", "document_highlights", ["user_id", "document_id"])
    op.create_index("idx_document_highlights_document_created", "document_highlights", ["document_id", "created_at"])
    op.create_index(op.f("ix_document_highlights_deleted_at"), "document_highlights", ["deleted_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "document_highlights" in sa.inspect(bind).get_table_names():
        op.drop_table("document_highlights")
