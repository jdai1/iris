"""Add source profile audiences.

Revision ID: 20260706_0004
Revises: 20260705_0003
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260706_0004"
down_revision = "20260705_0003b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("source_profile_analyses")}
    if "audiences" not in existing:
        op.add_column("source_profile_analyses", sa.Column("audiences", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("source_profile_analyses")}
    if "audiences" in existing:
        op.drop_column("source_profile_analyses", "audiences")
