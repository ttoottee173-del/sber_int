"""initial schema: checks, documents, issues

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "program",
            sa.Enum("federal", "regional", name="programtype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("approved", "rejected", "check_in_progress", name="checkstatus"),
            nullable=False,
        ),
        sa.Column("status_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("extracted", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "check_id",
            sa.String(length=36),
            sa.ForeignKey("checks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("detected_type", sa.String(length=64), nullable=False),
        sa.Column("size_kb", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
    )

    op.create_table(
        "issues",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "check_id",
            sa.String(length=36),
            sa.ForeignKey("checks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "level",
            sa.Enum("error", "warning", name="issuelevel"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
    )

    op.create_index("ix_documents_check_id", "documents", ["check_id"])
    op.create_index("ix_issues_check_id", "issues", ["check_id"])


def downgrade() -> None:
    op.drop_index("ix_issues_check_id", table_name="issues")
    op.drop_index("ix_documents_check_id", table_name="documents")
    op.drop_table("issues")
    op.drop_table("documents")
    op.drop_table("checks")

    sa.Enum(name="issuelevel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="checkstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="programtype").drop(op.get_bind(), checkfirst=True)
