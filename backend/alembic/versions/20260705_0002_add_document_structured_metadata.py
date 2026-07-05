"""add document structured metadata

Revision ID: 20260705_0002
Revises: 20260705_0001
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260705_0002"
down_revision = "20260705_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("documents")}

    if "one_liner" not in existing:
        op.add_column("documents", sa.Column("one_liner", sa.Text(), nullable=True))
    if "audience" not in existing:
        op.add_column("documents", sa.Column("audience", sa.Text(), nullable=True))
    if "takeaways" not in existing:
        op.add_column("documents", sa.Column("takeaways", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("documents")}

    if "takeaways" in existing:
        op.drop_column("documents", "takeaways")
    if "audience" in existing:
        op.drop_column("documents", "audience")
    if "one_liner" in existing:
        op.drop_column("documents", "one_liner")
