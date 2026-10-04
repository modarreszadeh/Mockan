"""Audit trail (PR-15): who changed what, written in the same transaction as the change."""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.infrastructure.db.models import AuditLog, Developer
from mockan.infrastructure.masking import mask_json


def record(
    session: AsyncSession,
    actor: Developer,
    action: AuditAction,
    entity_type: AuditEntityType,
    entity_id: uuid.UUID | str,
    changes: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Add an `audit_logs` row to `session`; it commits or rolls back with the change itself."""
    entry = AuditLog(
        developer_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        changes=mask_json(changes or {}),  # NFR-07: never store secrets in the audit trail
    )
    session.add(entry)
    return entry
