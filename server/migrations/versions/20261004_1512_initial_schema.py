"""initial schema (arch §8): developers, services, rules, responses, audit log

Revision ID: 0001
Revises:
Create Date: 2026-10-04 15:12:20.798881

Reviewed by hand after autogenerate: the circular FK mock_rules.active_response_id ->
mock_responses.id is created after both tables exist (autogenerate inlined it, which fails).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "action",
            sa.Enum(
                "create",
                "update",
                "delete",
                "toggle",
                "activate",
                name="auditaction",
                native_enum=False,
                length=10,
                schema="mockan",
            ),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.Enum(
                "mock_rule",
                "mock_response",
                "service",
                "service_environment",
                "developer_service_setting",
                "developer",
                name="auditentitytype",
                native_enum=False,
                length=30,
                schema="mockan",
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete', 'toggle', 'activate')",
            name=op.f("ck_audit_logs_action"),
        ),
        sa.CheckConstraint(
            "entity_type IN ('mock_rule', 'mock_response', 'service', 'service_environment', 'developer_service_setting', 'developer')",
            name=op.f("ck_audit_logs_entity_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        schema="mockan",
    )
    op.create_index(
        "ix_audit_logs_developer_id_timestamp",
        "audit_logs",
        ["developer_id", "timestamp"],
        unique=False,
        schema="mockan",
    )
    op.create_table(
        "developers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("sso_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "allowed_origins",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_developers")),
        sa.UniqueConstraint("slug", name=op.f("uq_developers_slug")),
        sa.UniqueConstraint("sso_subject", name=op.f("uq_developers_sso_subject")),
        schema="mockan",
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("path_prefix", sa.String(length=200), nullable=False),
        sa.Column("strip_prefix", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rewrite_origin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "default_environment",
            sa.Enum(
                "dev",
                "stage",
                name="environmentname",
                native_enum=False,
                length=10,
                schema="mockan",
            ),
            server_default="stage",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "default_environment IN ('dev', 'stage')", name=op.f("ck_services_default_environment")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint("name", name=op.f("uq_services_name")),
        sa.UniqueConstraint("path_prefix", name=op.f("uq_services_path_prefix")),
        schema="mockan",
    )
    op.create_table(
        "mock_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("method", sa.String(length=10), server_default="ANY", nullable=False),
        sa.Column(
            "match_type",
            sa.Enum(
                "Exact",
                "Template",
                "Prefix",
                "Regex",
                name="matchtype",
                native_enum=False,
                length=10,
                schema="mockan",
            ),
            nullable=False,
        ),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column(
            "query_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "header_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("active_response_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_type IN ('Exact', 'Template', 'Prefix', 'Regex')",
            name=op.f("ck_mock_rules_match_type"),
        ),
        sa.CheckConstraint(
            "method IN ('ANY', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')",
            name=op.f("ck_mock_rules_method"),
        ),
        sa.CheckConstraint("priority >= 0", name=op.f("ck_mock_rules_priority")),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["mockan.developers.id"],
            name=op.f("fk_mock_rules_developer_id_developers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["mockan.services.id"],
            name=op.f("fk_mock_rules_service_id_services"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_rules")),
        schema="mockan",
    )
    op.create_index(
        "ix_mock_rules_developer_id_is_enabled",
        "mock_rules",
        ["developer_id", "is_enabled"],
        unique=False,
        schema="mockan",
    )
    op.create_table(
        "service_environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column(
            "environment",
            sa.Enum(
                "dev",
                "stage",
                name="environmentname",
                native_enum=False,
                length=10,
                schema="mockan",
            ),
            nullable=False,
        ),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column(
            "extra_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "environment IN ('dev', 'stage')", name=op.f("ck_service_environments_environment")
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 3600",
            name=op.f("ck_service_environments_timeout_seconds"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["mockan.services.id"],
            name=op.f("fk_service_environments_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_environments")),
        sa.UniqueConstraint(
            "service_id", "environment", name="uq_service_environments_service_id_environment"
        ),
        schema="mockan",
    )
    op.create_table(
        "developer_service_settings",
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("service_environment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["mockan.developers.id"],
            name=op.f("fk_developer_service_settings_developer_id_developers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_environment_id"],
            ["mockan.service_environments.id"],
            name=op.f("fk_developer_service_settings_service_environment_id_service_environments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["mockan.services.id"],
            name=op.f("fk_developer_service_settings_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "developer_id", "service_id", name=op.f("pk_developer_service_settings")
        ),
        schema="mockan",
    )
    op.create_table(
        "mock_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "content_type", sa.String(length=255), server_default="application/json", nullable=False
        ),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "body_mode",
            sa.Enum(
                "Static",
                "Template",
                "ProxyAndPatch",
                name="bodymode",
                native_enum=False,
                length=20,
                schema="mockan",
            ),
            server_default="Static",
            nullable=False,
        ),
        sa.Column("delay_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "body_mode IN ('Static', 'Template', 'ProxyAndPatch')",
            name=op.f("ck_mock_responses_body_mode"),
        ),
        sa.CheckConstraint("delay_ms BETWEEN 0 AND 30000", name=op.f("ck_mock_responses_delay_ms")),
        sa.CheckConstraint(
            "status_code BETWEEN 100 AND 599", name=op.f("ck_mock_responses_status_code")
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["mockan.mock_rules.id"],
            name=op.f("fk_mock_responses_rule_id_mock_rules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_responses")),
        schema="mockan",
    )
    op.create_foreign_key(
        "fk_mock_rules_active_response_id_mock_responses",
        "mock_rules",
        "mock_responses",
        ["active_response_id"],
        ["id"],
        source_schema="mockan",
        referent_schema="mockan",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mock_rules_active_response_id_mock_responses",
        "mock_rules",
        schema="mockan",
        type_="foreignkey",
    )
    op.drop_table("mock_responses", schema="mockan")
    op.drop_table("developer_service_settings", schema="mockan")
    op.drop_table("service_environments", schema="mockan")
    op.drop_index("ix_mock_rules_developer_id_is_enabled", table_name="mock_rules", schema="mockan")
    op.drop_table("mock_rules", schema="mockan")
    op.drop_table("services", schema="mockan")
    op.drop_table("developers", schema="mockan")
    op.drop_index("ix_audit_logs_developer_id_timestamp", table_name="audit_logs", schema="mockan")
    op.drop_table("audit_logs", schema="mockan")
