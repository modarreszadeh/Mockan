"""SQLAlchemy models for schema `mockan` (arch §8).

Enum columns are `varchar` plus a `CHECK` (easier to extend in Alembic than native PG enums).
Relationships use `lazy="raise"`: callers must `selectinload` what they need, so nothing issues
hidden I/O (and the Gateway loader can't accidentally do N+1 queries).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from mockan.domain.constants import HTTP_METHODS, MAX_DELAY_MS, MAX_STATUS, MIN_STATUS
from mockan.domain.enums import (
    AuditAction,
    AuditEntityType,
    BodyMode,
    EnvironmentName,
    MatchType,
    RequestSource,
)

SCHEMA = "mockan"

# Stable constraint names keep Alembic autogenerate diffs deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class of every ORM model."""

    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
    # Fetch server-generated values (created_at, updated_at) with RETURNING so nothing is lazily
    # reloaded later (that would be hidden I/O on an async session).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012


def _enum[E: StrEnum](cls: type[E], length: int) -> Enum:
    """`varchar(length)` column that stores the enum *value* (e.g. "Exact"); no native PG enum."""
    return Enum(
        cls,
        native_enum=False,
        length=length,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


def _in_check(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _enum_check(column: str, cls: type[StrEnum], name: str | None = None) -> CheckConstraint:
    return CheckConstraint(_in_check(column, [m.value for m in cls]), name=name or column)


_now = func.now()
_empty_list = text("'[]'::jsonb")
_empty_object = text("'{}'::jsonb")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )


class Developer(TimestampMixin, Base):
    __tablename__ = "developers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    slug: Mapped[str | None] = mapped_column(String(32), unique=True)  # null until claimed
    display_name: Mapped[str] = mapped_column(String(200))
    sso_subject: Mapped[str] = mapped_column(String(255), unique=True)
    allowed_origins: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=_empty_list
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    service_settings: Mapped[list[DeveloperServiceSetting]] = relationship(
        lazy="raise", passive_deletes=True
    )


class Service(TimestampMixin, Base):
    __tablename__ = "services"
    __table_args__ = (_enum_check("default_environment", EnvironmentName),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    path_prefix: Mapped[str] = mapped_column(String(200), unique=True)
    strip_prefix: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    rewrite_origin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    default_environment: Mapped[EnvironmentName] = mapped_column(
        _enum(EnvironmentName, 10),
        default=EnvironmentName.STAGE,
        server_default=EnvironmentName.STAGE.value,
    )

    environments: Mapped[list[ServiceEnvironment]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ServiceEnvironment.environment",
    )


class ServiceEnvironment(TimestampMixin, Base):
    __tablename__ = "service_environments"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "environment", name="uq_service_environments_service_id_environment"
        ),
        _enum_check("environment", EnvironmentName),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 3600", name="timeout_seconds"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.services.id", ondelete="CASCADE")
    )
    environment: Mapped[EnvironmentName] = mapped_column(_enum(EnvironmentName, 10))
    base_url: Mapped[str] = mapped_column(String(2048))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"))
    extra_headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=_empty_object
    )


class DeveloperServiceSetting(TimestampMixin, Base):
    """A Developer's chosen environment for a Service. No row = the Service default (FR-04)."""

    __tablename__ = "developer_service_settings"

    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.developers.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.services.id", ondelete="CASCADE"), primary_key=True
    )
    service_environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.service_environments.id", ondelete="CASCADE")
    )


class MockRule(TimestampMixin, Base):
    __tablename__ = "mock_rules"
    __table_args__ = (
        Index("ix_mock_rules_developer_id_is_enabled", "developer_id", "is_enabled"),
        _enum_check("match_type", MatchType),
        CheckConstraint(
            _in_check("method", ["ANY", *HTTP_METHODS]),
            name="method",
        ),
        CheckConstraint("priority >= 0", name="priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    developer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.developers.id", ondelete="RESTRICT")
    )
    # Informational only: it does not filter matching (G-7, OQ-B1).
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.services.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10), default="ANY", server_default="ANY")
    match_type: Mapped[MatchType] = mapped_column(_enum(MatchType, 10))
    pattern: Mapped[str] = mapped_column(Text)
    query_conditions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=_empty_list
    )
    header_conditions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=_empty_list
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Circular with mock_responses.rule_id: created with use_alter, SET NULL when the response goes.
    active_response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            f"{SCHEMA}.mock_responses.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_mock_rules_active_response_id_mock_responses",
        )
    )

    responses: Mapped[list[MockResponse]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MockResponse.id",  # UUIDv7: creation order
        foreign_keys="MockResponse.rule_id",
    )


class MockResponse(TimestampMixin, Base):
    __tablename__ = "mock_responses"
    __table_args__ = (
        _enum_check("body_mode", BodyMode),
        CheckConstraint(f"status_code BETWEEN {MIN_STATUS} AND {MAX_STATUS}", name="status_code"),
        CheckConstraint(f"delay_ms BETWEEN 0 AND {MAX_DELAY_MS}", name="delay_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.mock_rules.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    status_code: Mapped[int] = mapped_column(Integer)
    headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=_empty_object
    )
    content_type: Mapped[str] = mapped_column(
        String(255), default="application/json", server_default="application/json"
    )
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    body_mode: Mapped[BodyMode] = mapped_column(
        _enum(BodyMode, 20), default=BodyMode.STATIC, server_default=BodyMode.STATIC.value
    )
    delay_ms: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class AuditLog(Base):
    """Who changed what (PR-15). Append-only, so no `updated_at`; deliberately no FKs, so history
    survives deleted Developers and entities."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_developer_id_timestamp", "developer_id", "timestamp"),
        _enum_check("action", AuditAction),
        _enum_check("entity_type", AuditEntityType),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    developer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # the actor
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    action: Mapped[AuditAction] = mapped_column(_enum(AuditAction, 10))
    entity_type: Mapped[AuditEntityType] = mapped_column(_enum(AuditEntityType, 30))
    entity_id: Mapped[str] = mapped_column(String(100))
    changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=_empty_object
    )


class RequestLog(Base):
    """One request through the Gateway (PR-12, D-18). Headers and body samples arrive masked
    (NFR-07). No FKs, like `audit_logs`; retention keeps 7 days and 5,000 rows per Developer."""

    __tablename__ = "request_logs"
    __table_args__ = (
        Index("ix_request_logs_developer_id_id", "developer_id", "id"),
        Index("ix_request_logs_timestamp", "timestamp"),
        _enum_check("source", RequestSource),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    developer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)  # after the Developer slug, as rules see it
    query: Mapped[str] = mapped_column(Text, default="", server_default="")
    service_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source: Mapped[RequestSource] = mapped_column(_enum(RequestSource, 10))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    request_headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=_empty_object
    )
    response_headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=_empty_object
    )
    request_body_sample: Mapped[str | None] = mapped_column(Text)
    response_body_sample: Mapped[str | None] = mapped_column(Text)
