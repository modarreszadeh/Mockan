"""Stable problem+json codes (arch §14 rule 8; Backend implementation plan G-5)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    # Gateway
    DEVELOPER_NOT_FOUND = "developer_not_found"
    SERVICE_NOT_RESOLVED = "service_not_resolved"
    UPSTREAM_UNREACHABLE = "upstream_unreachable"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    MOCK_RENDER_FAILED = "mock_render_failed"
    # Admin API
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    DEVELOPER_DISABLED = "developer_disabled"
    NOT_FOUND = "not_found"
    VALIDATION_FAILED = "validation_failed"
    SLUG_TAKEN = "slug_taken"
    SLUG_IMMUTABLE = "slug_immutable"
    NAME_TAKEN = "name_taken"
    PATH_PREFIX_TAKEN = "path_prefix_taken"
    ENVIRONMENT_EXISTS = "environment_exists"
    UPSTREAM_HOST_NOT_ALLOWED = "upstream_host_not_allowed"
    LAST_RESPONSE = "last_response"
    INTERNAL_ERROR = "internal_error"
