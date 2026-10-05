"""Enumerations shared by every layer. Values match the architecture (§7, §8) and the Panel."""

from enum import StrEnum


class MatchType(StrEnum):
    EXACT = "Exact"
    TEMPLATE = "Template"
    PREFIX = "Prefix"
    REGEX = "Regex"


class BodyMode(StrEnum):
    STATIC = "Static"
    TEMPLATE = "Template"
    PROXY_AND_PATCH = "ProxyAndPatch"


class RequestSource(StrEnum):
    PROXIED = "Proxied"
    MOCKED = "Mocked"
    ERROR = "Error"


class EnvironmentName(StrEnum):
    DEV = "dev"
    STAGE = "stage"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    TOGGLE = "toggle"
    ACTIVATE = "activate"


class AuditEntityType(StrEnum):
    MOCK_RULE = "mock_rule"
    MOCK_RESPONSE = "mock_response"
    SERVICE = "service"
    SERVICE_ENVIRONMENT = "service_environment"
    DEVELOPER_SERVICE_SETTING = "developer_service_setting"
    DEVELOPER = "developer"


class ConditionOperator(StrEnum):
    EQUALS = "equals"
    EXISTS = "exists"
