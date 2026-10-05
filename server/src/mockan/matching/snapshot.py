"""Immutable `RuleSnapshot` and the provider the Gateway reads once per request (arch §9)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from mockan.matching.model import CompiledRule, DeveloperEntry, ServiceEntry


def sort_rules(rules: Sequence[CompiledRule]) -> tuple[CompiledRule, ...]:
    """Order rules by precedence (arch §7.2); this is also the order the Panel lists them in."""
    return tuple(sorted(rules, key=lambda rule: rule.sort_key))


def sort_services(services: Sequence[ServiceEntry]) -> tuple[ServiceEntry, ...]:
    """Longest `path_prefix` first, so the first segment-boundary match is the longest."""
    return tuple(sorted(services, key=lambda service: -len(service.path_prefix)))


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    developers_by_slug: Mapping[str, DeveloperEntry]
    rules_by_developer: Mapping[UUID, tuple[CompiledRule, ...]]  # enabled only, sorted
    services_sorted_by_prefix_len: tuple[ServiceEntry, ...]
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def build(
        cls,
        *,
        developers: Sequence[DeveloperEntry],
        rules: Sequence[CompiledRule],
        services: Sequence[ServiceEntry],
        built_at: datetime | None = None,
    ) -> RuleSnapshot:
        """Group and sort. Disabled rules are dropped here, so matching never sees them."""
        grouped: dict[UUID, list[CompiledRule]] = {}
        for rule in rules:
            grouped.setdefault(rule.developer_id, []).append(rule)
        return cls(
            developers_by_slug=MappingProxyType({d.slug.lower(): d for d in developers}),
            rules_by_developer=MappingProxyType(
                {dev_id: sort_rules(items) for dev_id, items in grouped.items()}
            ),
            services_sorted_by_prefix_len=sort_services(services),
            built_at=built_at or datetime.now(UTC),
        )

    @classmethod
    def empty(cls) -> RuleSnapshot:
        return cls.build(developers=(), rules=(), services=())

    def developer_for_slug(self, slug: str) -> DeveloperEntry | None:
        return self.developers_by_slug.get(slug.lower())

    def rules_for(self, developer_id: UUID) -> tuple[CompiledRule, ...]:
        return self.rules_by_developer.get(developer_id, ())

    def with_developer_slice(
        self,
        developer_id: UUID,
        *,
        developer: DeveloperEntry | None,
        rules: Sequence[CompiledRule],
    ) -> RuleSnapshot:
        """A new snapshot with one Developer's entry and rules replaced (cheap partial rebuild).

        `developer=None` removes the Developer (deleted, or no slug yet). The rest is shared.
        """
        developers = {
            slug: entry
            for slug, entry in self.developers_by_slug.items()
            if entry.id != developer_id
        }
        if developer is not None:
            developers[developer.slug.lower()] = developer
        grouped = dict(self.rules_by_developer)
        grouped.pop(developer_id, None)
        if developer is not None and rules:
            grouped[developer_id] = sort_rules(rules)
        return RuleSnapshot(
            developers_by_slug=MappingProxyType(developers),
            rules_by_developer=MappingProxyType(grouped),
            services_sorted_by_prefix_len=self.services_sorted_by_prefix_len,
            built_at=datetime.now(UTC),
        )


class RuleSnapshotProvider:
    """Holds the current snapshot. A swap is a single attribute assignment (atomic in CPython).

    Request handlers read `current` once and use that object for the whole request.
    """

    def __init__(self, snapshot: RuleSnapshot | None = None) -> None:
        self.current: RuleSnapshot = snapshot if snapshot is not None else RuleSnapshot.empty()
        self.loaded: bool = snapshot is not None

    def swap(self, snapshot: RuleSnapshot) -> None:
        self.current = snapshot
        self.loaded = True
