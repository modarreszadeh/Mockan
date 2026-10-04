"""`resolve_service`: longest PathPrefix on a segment boundary, then environment (FR-03, FR-04)."""

from dataclasses import dataclass

from mockan.matching.errors import ServiceNotResolvedError
from mockan.matching.model import DeveloperEntry, EnvironmentEntry, ServiceEntry
from mockan.matching.snapshot import RuleSnapshot


@dataclass(frozen=True, slots=True)
class ResolvedService:
    service: ServiceEntry
    environment: EnvironmentEntry
    upstream_path: str  # starts with "/"; honours `strip_prefix`


def _on_boundary(path_lower: str, prefix_lower: str) -> bool:
    return path_lower == prefix_lower or path_lower.startswith(prefix_lower + "/")


def resolve_service(
    snapshot: RuleSnapshot, developer: DeveloperEntry, path: str
) -> ResolvedService:
    """Resolve the Service for `path` (the path after the DeveloperSlug).

    Raises `ServiceNotResolvedError` (code `service_not_resolved`) with a human-readable detail.
    """
    lowered = path.lower()
    service = next(
        (
            candidate
            for candidate in snapshot.services_sorted_by_prefix_len
            if _on_boundary(lowered, candidate.path_prefix.lower())
        ),
        None,
    )
    if service is None:
        raise ServiceNotResolvedError(
            f"No Service in the catalog has a path prefix matching '{path}'."
        )

    chosen_id = developer.service_environment_ids.get(service.id)
    environment = next((e for e in service.environments.values() if e.id == chosen_id), None)
    if environment is None:  # no setting (or a stale one): the Service default (FR-04)
        environment = service.environments.get(service.default_environment)
    if environment is None:
        raise ServiceNotResolvedError(
            f"Service '{service.name}' has no '{service.default_environment.value}' environment "
            "configured."
        )

    upstream_path = path[len(service.path_prefix) :] if service.strip_prefix else path
    return ResolvedService(service, environment, upstream_path or "/")
