"""Add stable public UUIDs to document highlights.

Revision ID: 20260802_0009
Revises: 20260801_0008
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260802_0009"
down_revision = "20260801_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("document_highlights")}
    if "uuid" not in columns:
        op.add_column("document_highlights", sa.Column("uuid", sa.String(length=36), nullable=True))
    rows = bind.execute(sa.text("SELECT id FROM document_highlights WHERE uuid IS NULL")).all()
    for (highlight_id,) in rows:
        bind.execute(
            sa.text("UPDATE document_highlights SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(uuid4()), "id": highlight_id},
        )
    with op.batch_alter_table("document_highlights") as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(length=36), nullable=False)
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("document_highlights")}
        if "ix_document_highlights_uuid" not in indexes:
            batch_op.create_index("ix_document_highlights_uuid", ["uuid"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("document_highlights")}
    if "uuid" in columns:
        with op.batch_alter_table("document_highlights") as batch_op:
            indexes = {index["name"] for index in sa.inspect(bind).get_indexes("document_highlights")}
            if "ix_document_highlights_uuid" in indexes:
                batch_op.drop_index("ix_document_highlights_uuid")
            batch_op.drop_column("uuid")
