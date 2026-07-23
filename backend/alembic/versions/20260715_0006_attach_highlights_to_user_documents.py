"""Attach document highlights to user document mappings.

Revision ID: 20260715_0006
Revises: 20260713_0005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260715_0006"
down_revision = "20260713_0005"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "document_highlights" not in sa.inspect(bind).get_table_names():
        return

    columns = _columns(bind, "document_highlights")
    if "user_document_mapping_id" in columns and "user_id" not in columns:
        return

    if "user_document_mapping_id" not in columns:
        op.add_column(
            "document_highlights",
            sa.Column("user_document_mapping_id", sa.Integer(), nullable=True),
        )

    # Older API versions could create a highlight without first creating the
    # corresponding user-document row. Preserve those highlights by repairing
    # that invariant before the foreign key is made mandatory.
    op.execute(sa.text("""
        INSERT INTO user_document_mappings (
            user_id, document_id, created_at, updated_at, first_seen_at,
            last_seen_at, open_count
        )
        SELECT h.user_id, h.document_id, MIN(h.created_at), MIN(h.created_at),
               MIN(h.created_at), MIN(h.created_at), 0
        FROM document_highlights AS h
        LEFT JOIN user_document_mappings AS m
          ON m.user_id = h.user_id AND m.document_id = h.document_id
        WHERE m.id IS NULL
        GROUP BY h.user_id, h.document_id
    """))
    op.execute(sa.text("""
        UPDATE document_highlights
        SET user_document_mapping_id = (
            SELECT m.id
            FROM user_document_mappings AS m
            WHERE m.user_id = document_highlights.user_id
              AND m.document_id = document_highlights.document_id
        )
        WHERE user_document_mapping_id IS NULL
    """))

    indexes = _indexes(bind, "document_highlights")
    for name in (
        "idx_document_highlights_user_document",
        "idx_document_highlights_document_created",
        "ix_document_highlights_user_id",
        "ix_document_highlights_document_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="document_highlights")

    with op.batch_alter_table("document_highlights") as batch_op:
        batch_op.create_foreign_key(
            "fk_document_highlights_user_document_mapping",
            "user_document_mappings",
            ["user_document_mapping_id"],
            ["id"],
        )
        batch_op.alter_column("user_document_mapping_id", nullable=False)
        batch_op.drop_column("user_id")
        batch_op.drop_column("document_id")

    # Batch table recreation removes the legacy indexes along with their
    # columns. Use one index for the dominant restore/list access pattern.
    op.create_index(
        "idx_document_highlights_mapping_created",
        "document_highlights",
        ["user_document_mapping_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "document_highlights" not in sa.inspect(bind).get_table_names():
        return
    columns = _columns(bind, "document_highlights")
    if "user_id" in columns and "document_id" in columns:
        return

    indexes = _indexes(bind, "document_highlights")
    if "idx_document_highlights_mapping_created" in indexes:
        op.drop_index(
            "idx_document_highlights_mapping_created",
            table_name="document_highlights",
        )

    with op.batch_alter_table("document_highlights") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("document_id", sa.Integer(), nullable=True))

    op.execute(sa.text("""
        UPDATE document_highlights
        SET user_id = (
                SELECT m.user_id FROM user_document_mappings AS m
                WHERE m.id = document_highlights.user_document_mapping_id
            ),
            document_id = (
                SELECT m.document_id FROM user_document_mappings AS m
                WHERE m.id = document_highlights.user_document_mapping_id
            )
    """))

    with op.batch_alter_table("document_highlights") as batch_op:
        batch_op.create_foreign_key(
            "fk_document_highlights_user", "users", ["user_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_document_highlights_document", "documents", ["document_id"], ["id"]
        )
        batch_op.alter_column("user_id", nullable=False)
        batch_op.alter_column("document_id", nullable=False)
        batch_op.drop_column("user_document_mapping_id")

    op.create_index(
        "idx_document_highlights_user_document",
        "document_highlights",
        ["user_id", "document_id"],
    )
    op.create_index(
        "idx_document_highlights_document_created",
        "document_highlights",
        ["document_id", "created_at"],
    )
