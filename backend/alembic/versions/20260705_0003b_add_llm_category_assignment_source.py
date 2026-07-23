"""Add LLM category assignment source."""

from __future__ import annotations

from alembic import op


revision = "20260705_0003b"
down_revision = "20260705_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE document_categories DROP CONSTRAINT IF EXISTS category_assignment_source")
    op.execute(
        "ALTER TABLE document_categories ADD CONSTRAINT category_assignment_source "
        "CHECK (assigned_by IN ('system', 'llm', 'user'))"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE document_categories DROP CONSTRAINT IF EXISTS category_assignment_source")
    op.execute(
        "ALTER TABLE document_categories ADD CONSTRAINT category_assignment_source "
        "CHECK (assigned_by IN ('system', 'user'))"
    )
