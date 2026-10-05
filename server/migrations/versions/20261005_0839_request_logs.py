"""request_logs: the live request log table (PR-12, D-18)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05 08:39:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), server_default="", nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "Proxied",
                "Mocked",
                "Error",
                name="requestsource",
                native_enum=False,
                length=10,
                schema="mockan",
            ),
            nullable=False,
        ),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "request_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "response_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("request_body_sample", sa.Text(), nullable=True),
        sa.Column("response_body_sample", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source IN ('Proxied', 'Mocked', 'Error')", name=op.f("ck_request_logs_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_logs")),
        schema="mockan",
    )
    op.create_index(
        "ix_request_logs_developer_id_id", "request_logs", ["developer_id", "id"], schema="mockan"
    )
    op.create_index("ix_request_logs_timestamp", "request_logs", ["timestamp"], schema="mockan")


def downgrade() -> None:
    op.drop_index("ix_request_logs_timestamp", table_name="request_logs", schema="mockan")
    op.drop_index("ix_request_logs_developer_id_id", table_name="request_logs", schema="mockan")
    op.drop_table("request_logs", schema="mockan")
