"""add public uuids

Revision ID: 20260705_0003
Revises: 20260705_0002
Create Date: 2026-07-05
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260705_0003"
down_revision = "20260705_0002"
branch_labels = None
depends_on = None


def _add_uuid_column(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns(table_name)}

    if "uuid" not in existing:
        op.add_column(table_name, sa.Column("uuid", sa.String(length=36), nullable=True))

    rows = bind.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE uuid IS NULL OR uuid = ''")
    ).all()
    for row in rows:
        bind.execute(
            sa.text(f"UPDATE {table_name} SET uuid = :uuid WHERE id = :id"),
            {"uuid": str(uuid4()), "id": row.id},
        )

    if bind.dialect.name != "sqlite":
        op.alter_column(table_name, "uuid", existing_type=sa.String(length=36), nullable=False)

    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, ["uuid"], unique=True)


def _drop_uuid_column(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    if "uuid" in existing:
        op.drop_column(table_name, "uuid")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        checks = {check["name"] for check in sa.inspect(bind).get_check_constraints("document_categories")}
        if "category_assignment_source" in checks:
            op.drop_constraint("category_assignment_source", "document_categories", type_="check")
            op.create_check_constraint(
                "category_assignment_source",
                "document_categories",
                "assigned_by IN ('system', 'llm', 'user')",
            )

    _add_uuid_column("agent_conversations", "idx_agent_conversations_uuid")
    _add_uuid_column("documents", "idx_documents_uuid")


def downgrade() -> None:
    _drop_uuid_column("documents", "idx_documents_uuid")
    _drop_uuid_column("agent_conversations", "idx_agent_conversations_uuid")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        checks = {check["name"] for check in sa.inspect(bind).get_check_constraints("document_categories")}
        if "category_assignment_source" in checks:
            op.drop_constraint("category_assignment_source", "document_categories", type_="check")
            op.create_check_constraint(
                "category_assignment_source",
                "document_categories",
                "assigned_by IN ('system', 'user')",
            )
