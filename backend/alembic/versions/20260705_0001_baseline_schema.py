"""baseline schema

Revision ID: 20260705_0001
Revises:
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op

from iris.dao.db import Base

# Import models so Base.metadata is populated.
from iris import models  # noqa: F401


revision = "20260705_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # This baseline bootstraps Alembic for both existing and fresh local DBs.
    # Do not drop application tables on downgrade.
    pass
