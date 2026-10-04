"""Per-request state shared by the pipeline steps (`scope["state"]["mockan"]`)."""

import time
from dataclasses import dataclass, field
from uuid import UUID

from starlette.types import Scope

from mockan.domain.enums import RequestSource
from mockan.matching.model import DeveloperEntry
from mockan.matching.snapshot import RuleSnapshot, RuleSnapshotProvider

# Health routes bypass the pipeline. Anything else under `/_mockan/...` is a reserved slug (404).
INTERNAL_PATHS = frozenset({"/_mockan/health/live", "/_mockan/health/ready"})
_STATE_KEY = "mockan"
_SNAPSHOT_KEY = "mockan_snapshot"


@dataclass(slots=True)
class MockanContext:
    snapshot: RuleSnapshot
    developer: DeveloperEntry
    path_after_slug: str  # what rules and Service prefixes match against, e.g. "/limsa/api/v1/x"
    started_at: float = field(default_factory=time.perf_counter)
    source: RequestSource | None = None
    rule_id: UUID | None = None


def is_internal(scope: Scope) -> bool:
    """Health routes are dispatched before Developer resolution (arch §6.2)."""
    return str(scope["path"]) in INTERNAL_PATHS


def snapshot_for(scope: Scope, provider: RuleSnapshotProvider) -> RuleSnapshot:
    """Read `provider.current` once per request and reuse that object for the whole request."""
    state: dict[str, object] = scope.setdefault("state", {})
    snapshot = state.get(_SNAPSHOT_KEY)
    if not isinstance(snapshot, RuleSnapshot):
        snapshot = state[_SNAPSHOT_KEY] = provider.current
    return snapshot


def set_context(scope: Scope, context: MockanContext) -> None:
    scope.setdefault("state", {})[_STATE_KEY] = context


def get_context(scope: Scope) -> MockanContext | None:
    found = scope.get("state", {}).get(_STATE_KEY)
    return found if isinstance(found, MockanContext) else None


def split_slug(path: str) -> tuple[str, str]:
    """`/ehtesham/limsa/x` -> (`ehtesham`, `/limsa/x`). The slug is `""` when there is none."""
    trimmed = path[1:] if path.startswith("/") else path
    slug, _, rest = trimmed.partition("/")
    return slug, "/" + rest
