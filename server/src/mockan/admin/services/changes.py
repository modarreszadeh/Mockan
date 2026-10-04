"""Build the `changes` payload of audit rows (masked later by `audit.record`)."""

from collections.abc import Mapping
from typing import Any


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """`{field: {"from": old, "to": new}}` for the fields whose value differs."""
    return {
        field: {"from": old.get(field), "to": value}
        for field, value in new.items()
        if old.get(field) != value
    }
