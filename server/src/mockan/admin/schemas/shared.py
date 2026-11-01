"""The public, read-only view of a shared MockRule (`GET /shared/rules/{token}`, S-3, S-4).

A dedicated model: it never carries `developerId`, `ssoSubject` or the share token itself.
"""

import uuid
from datetime import datetime

from mockan.admin.schemas.base import CamelModel
from mockan.admin.schemas.rule import ConditionOut, MockResponseOut
from mockan.domain.enums import MatchType


class SharedOwnerOut(CamelModel):
    display_name: str
    slug: str | None


class SharedServiceOut(CamelModel):
    name: str
    path_prefix: str


class SharedRuleOut(CamelModel):
    name: str
    method: str
    match_type: MatchType
    pattern: str
    query_conditions: list[ConditionOut]
    header_conditions: list[ConditionOut]
    priority: int
    is_enabled: bool
    active_response_id: uuid.UUID | None
    responses: list[MockResponseOut]
    service: SharedServiceOut | None
    owner: SharedOwnerOut
    public_base_url: str  # same source as `GET /me`
    updated_at: datetime
