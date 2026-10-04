import pytest

from mockan.domain.enums import MatchType
from mockan.matching.snapshot import RuleSnapshot, RuleSnapshotProvider
from tests.support.snapshot_builder import SnapshotBuilder


@pytest.mark.req("NFR-02")
def test_rules_are_grouped_per_developer_and_sorted_by_precedence(
    snapshot_builder: SnapshotBuilder,
) -> None:
    a = snapshot_builder.developer("alice")
    b = snapshot_builder.developer("bob")
    snapshot_builder.rule(a, MatchType.REGEX, "^/x", name="regex")
    snapshot_builder.rule(a, MatchType.EXACT, "/x", name="exact")
    snapshot_builder.rule(b, MatchType.PREFIX, "/", name="bob")
    snapshot = snapshot_builder.build()
    assert [r.name for r in snapshot.rules_for(a.id)] == ["exact", "regex"]
    assert [r.name for r in snapshot.rules_for(b.id)] == ["bob"]
    assert snapshot.rules_for(snapshot_builder.developer("nobody").id) == ()


@pytest.mark.req("FR-03")
def test_services_are_sorted_longest_prefix_first(snapshot_builder: SnapshotBuilder) -> None:
    snapshot_builder.service("a", "/a")
    snapshot_builder.service("abc", "/abc/d")
    snapshot_builder.service("ab", "/ab")
    names = [s.name for s in snapshot_builder.build().services_sorted_by_prefix_len]
    assert names == ["abc", "ab", "a"]


@pytest.mark.req("PR-01")
def test_developer_lookup_by_slug_is_case_insensitive(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("Ehtesham")
    snapshot = snapshot_builder.build()
    assert snapshot.developer_for_slug("ehtesham") is dev
    assert snapshot.developer_for_slug("EHTESHAM") is dev
    assert snapshot.developer_for_slug("other") is None


@pytest.mark.req("FR-08")
def test_with_developer_slice_replaces_only_that_developer(
    snapshot_builder: SnapshotBuilder,
) -> None:
    a = snapshot_builder.developer("alice")
    b = snapshot_builder.developer("bob")
    snapshot_builder.rule(a, MatchType.EXACT, "/a", name="old-a")
    snapshot_builder.rule(b, MatchType.EXACT, "/b", name="bob")
    service = snapshot_builder.service("limsa", "/limsa")
    before = snapshot_builder.build()

    other = SnapshotBuilder()
    new_rule = other.rule(a, MatchType.EXACT, "/a2", name="new-a")
    after = before.with_developer_slice(a.id, developer=a, rules=[new_rule])

    assert [r.name for r in after.rules_for(a.id)] == ["new-a"]
    assert after.rules_for(b.id) is before.rules_for(b.id)  # shared, not copied
    assert after.services_sorted_by_prefix_len == (service,)
    assert [r.name for r in before.rules_for(a.id)] == ["old-a"]  # the old snapshot is untouched
    assert after is not before


@pytest.mark.req("FR-08")
def test_with_developer_slice_handles_slug_change_and_removal(
    snapshot_builder: SnapshotBuilder,
) -> None:
    a = snapshot_builder.developer("alice")
    snapshot_builder.rule(a, MatchType.EXACT, "/a", name="a")
    before = snapshot_builder.build()

    renamed = a.__class__(
        id=a.id,
        slug="alicia",
        display_name=a.display_name,
        allowed_origins=a.allowed_origins,
        is_enabled=True,
        service_environment_ids={},
    )
    moved = before.with_developer_slice(a.id, developer=renamed, rules=before.rules_for(a.id))
    assert moved.developer_for_slug("alice") is None
    assert moved.developer_for_slug("alicia") is renamed
    assert len(moved.rules_for(a.id)) == 1

    removed = moved.with_developer_slice(a.id, developer=None, rules=[])
    assert removed.developer_for_slug("alicia") is None
    assert removed.rules_for(a.id) == ()

    no_rules = before.with_developer_slice(a.id, developer=a, rules=[])
    assert no_rules.developer_for_slug("alice") is a
    assert no_rules.rules_for(a.id) == ()


@pytest.mark.req("FR-08")
def test_provider_swaps_by_assignment_and_tracks_whether_a_snapshot_loaded(
    snapshot_builder: SnapshotBuilder,
) -> None:
    provider = RuleSnapshotProvider()
    assert provider.loaded is False
    assert provider.current.developers_by_slug == {}
    snapshot = snapshot_builder.build()
    provider.swap(snapshot)
    assert provider.loaded is True
    assert provider.current is snapshot
    assert RuleSnapshotProvider(snapshot).loaded is True
    assert RuleSnapshot.empty().services_sorted_by_prefix_len == ()
