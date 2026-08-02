"""Track first-time profile setup completion on users.

Revision ID: 20260801_0008
Revises: 20260723_0007
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260801_0008"
down_revision = "20260723_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "onboarding_completed_at" not in columns:
        op.add_column(
            "users",
            sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        "UPDATE users SET onboarding_completed_at = CURRENT_TIMESTAMP "
        "WHERE onboarding_completed_at IS NULL"
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "onboarding_completed_at" in columns:
        op.drop_column("users", "onboarding_completed_at")
