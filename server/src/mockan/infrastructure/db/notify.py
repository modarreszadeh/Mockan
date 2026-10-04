"""Change notification: tell Gateways which Developer's rules changed (D-07, D-16).

An `after_flush` listener records the affected Developer ids (or `catalog`) of every ORM write
into `session.info`; `before_commit` sends one `pg_notify('mockan_config_changed', payload)` per
distinct payload. PostgreSQL delivers a notification only if the transaction commits, so a
rollback sends nothing. Bulk `update()` statements bypass the ORM and must call `mark()`.
"""

import uuid
from typing import Literal

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from mockan.infrastructure.db.models import (
    Developer,
    DeveloperServiceSetting,
    MockResponse,
    MockRule,
    Service,
    ServiceEnvironment,
)

CHANNEL = "mockan_config_changed"
CATALOG = "catalog"

_PAYLOADS = "mockan_notify_payloads"
_RULE_IDS = "mockan_notify_rule_ids"  # rules whose owner is looked up at commit (MockResponse)


class NotifySession(Session):
    """The sync session class behind Mockan's `AsyncSession`s; the listeners below hang off it."""


def mark(session: AsyncSession | Session, target: uuid.UUID | Literal["catalog"]) -> None:
    """Register a payload explicitly (bulk UPDATE/DELETE statements skip the ORM events)."""
    sync = session.sync_session if isinstance(session, AsyncSession) else session
    sync.info.setdefault(_PAYLOADS, set()).add(str(target))


@event.listens_for(NotifySession, "after_flush")
def _collect(session: Session, _flush_context: object) -> None:
    # Not `before_flush`: primary keys (UUIDv7 defaults) are only assigned during the flush, and
    # in `after_flush` the new/dirty/deleted lists still show the pre-flush state. Collecting on
    # every flush (not only at commit) keeps an explicit `session.flush()` from hiding a change.
    payloads: set[str] = session.info.setdefault(_PAYLOADS, set())
    rule_ids: set[uuid.UUID] = session.info.setdefault(_RULE_IDS, set())
    for obj in (*session.new, *session.dirty, *session.deleted):
        match obj:
            case Developer():
                payloads.add(str(obj.id))
            case MockRule() | DeveloperServiceSetting():
                payloads.add(str(obj.developer_id))
            case MockResponse():
                rule_ids.add(obj.rule_id)
            case Service() | ServiceEnvironment():
                payloads.add(CATALOG)


@event.listens_for(NotifySession, "before_commit")
def _emit(session: Session) -> None:
    # `before_commit` runs before the commit's own flush, so flush now: that is what populates the
    # payloads (and assigns primary keys) for changes the caller never flushed explicitly.
    session.flush()
    payloads: set[str] = session.info.pop(_PAYLOADS, set())
    rule_ids: set[uuid.UUID] = session.info.pop(_RULE_IDS, set())
    if rule_ids:  # the owner of a changed MockResponse is its rule's Developer
        owners = session.execute(
            select(MockRule.developer_id).where(MockRule.id.in_(rule_ids)).distinct()
        )
        payloads.update(str(owner) for owner in owners.scalars())
    for payload in sorted(payloads):
        session.execute(
            text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload}
        )


@event.listens_for(NotifySession, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PAYLOADS, None)
    session.info.pop(_RULE_IDS, None)
