"""mock_rules.share_token: the secret of a rule's public share link (S-1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mock_rules",
        sa.Column("share_token", sa.String(length=64), nullable=True),
        schema="mockan",
    )
    op.create_unique_constraint(
        op.f("uq_mock_rules_share_token"), "mock_rules", ["share_token"], schema="mockan"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_mock_rules_share_token"), "mock_rules", type_="unique", schema="mockan"
    )
    op.drop_column("mock_rules", "share_token", schema="mockan")
