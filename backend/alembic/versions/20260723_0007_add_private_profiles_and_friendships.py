"""Add private user profiles, personal websites, and friendships.

Revision ID: 20260723_0007
Revises: 20260715_0006
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260723_0007"
down_revision = "20260715_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user"),
        sa.UniqueConstraint("username", name="uq_user_profiles_username"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])
    op.create_index("ix_user_profiles_username", "user_profiles", ["username"], unique=True)

    op.create_table(
        "user_websites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.UniqueConstraint("profile_id", "source_id", name="uq_user_websites_profile_source"),
    )
    op.create_index("ix_user_websites_profile_id", "user_websites", ["profile_id"])
    op.create_index("ix_user_websites_source_id", "user_websites", ["source_id"])

    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pair_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "requested",
                "connected",
                name="friendship_status",
                native_enum=False,
                length=40,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.UniqueConstraint("pair_key", name="uq_friendships_pair"),
    )
    op.create_index("ix_friendships_requester_id", "friendships", ["requester_id"])
    op.create_index("ix_friendships_recipient_id", "friendships", ["recipient_id"])
    op.create_index("ix_friendships_pair_key", "friendships", ["pair_key"], unique=True)
    op.create_index("ix_friendships_status", "friendships", ["status"])
    op.create_index(
        "idx_friendships_requester_status",
        "friendships",
        ["requester_id", "status"],
    )
    op.create_index(
        "idx_friendships_recipient_status",
        "friendships",
        ["recipient_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("friendships")
    op.drop_table("user_websites")
    op.drop_table("user_profiles")
