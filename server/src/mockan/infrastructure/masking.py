"""Secret masking for logs, the request log and audit changes (NFR-07)."""

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

MASK = "***"

_ALWAYS_MASKED = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie"})
_SENSITIVE_NAME = re.compile(r"(?i)(token|secret|password|api[-_]?key)")


def is_sensitive_name(name: str) -> bool:
    """Is a header or JSON key one whose value must never be stored or logged?"""
    return name.lower() in _ALWAYS_MASKED or _SENSITIVE_NAME.search(name) is not None


def mask_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name: MASK if is_sensitive_name(name) else value for name, value in headers.items()}


def mask_json(value: object) -> Any:
    """Return a copy of a JSON-like value with the value of every sensitive key replaced."""
    if isinstance(value, Mapping):
        return {
            str(key): MASK if is_sensitive_name(str(key)) else mask_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [mask_json(item) for item in value]
    return value


def mask_event_dict(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: mask every sensitive key anywhere in a log event."""
    masked = mask_json(event_dict)
    event_dict.update(masked)
    return event_dict
