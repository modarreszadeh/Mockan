import pytest

from mockan.domain.enums import EnvironmentName
from mockan.matching.errors import ServiceNotResolvedError
from mockan.matching.service_resolver import resolve_service
from tests.support.snapshot_builder import SnapshotBuilder


@pytest.mark.req("PR-04")
def test_longest_prefix_wins(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    short = snapshot_builder.service("limsa", "/limsa")
    long = snapshot_builder.service("limsa-reports", "/limsa/reports")
    snapshot = snapshot_builder.build()
    assert resolve_service(snapshot, dev, "/limsa/reports/1").service is long
    assert resolve_service(snapshot, dev, "/limsa/other").service is short


@pytest.mark.req("PR-04")
def test_prefix_matches_on_a_segment_boundary_only(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    service = snapshot_builder.service("limsa", "/limsa")
    snapshot = snapshot_builder.build()
    assert resolve_service(snapshot, dev, "/limsa").service is service
    assert resolve_service(snapshot, dev, "/limsa/x").service is service
    assert resolve_service(snapshot, dev, "/LIMSA/x").service is service  # case-insensitive
    with pytest.raises(ServiceNotResolvedError):
        resolve_service(snapshot, dev, "/limsatest")


@pytest.mark.req("PR-16")
def test_unknown_path_explains_itself(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("limsa", "/limsa")
    with pytest.raises(ServiceNotResolvedError) as error:
        resolve_service(snapshot_builder.build(), dev, "/nothing/x")
    assert "'/nothing/x'" in error.value.detail


@pytest.mark.req("PR-04")
def test_strip_prefix_false_keeps_the_whole_path(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("limsa", "/limsa", strip_prefix=False)
    resolved = resolve_service(snapshot_builder.build(), dev, "/limsa/api/Items")
    assert resolved.upstream_path == "/limsa/api/Items"


@pytest.mark.req("PR-04")
def test_strip_prefix_true_removes_it_and_keeps_case(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("limsa", "/limsa", strip_prefix=True)
    snapshot = snapshot_builder.build()
    assert resolve_service(snapshot, dev, "/LIMSA/api/Items").upstream_path == "/api/Items"
    assert resolve_service(snapshot, dev, "/limsa").upstream_path == "/"


@pytest.mark.req("PR-04")
def test_environment_is_the_service_default_without_a_setting(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("limsa", "/limsa", default_environment=EnvironmentName.DEV)
    resolved = resolve_service(snapshot_builder.build(), dev, "/limsa/x")
    assert resolved.environment.environment is EnvironmentName.DEV
    assert resolved.environment.base_url == "https://limsa.dev.internal"


@pytest.mark.req("PR-04")
def test_environment_follows_the_developer_setting(snapshot_builder: SnapshotBuilder) -> None:
    service = snapshot_builder.service("limsa", "/limsa")  # default: stage
    dev_env = service.environments[EnvironmentName.DEV]
    dev = snapshot_builder.developer("ehtesham", environment_ids={service.id: dev_env.id})
    resolved = resolve_service(snapshot_builder.build(), dev, "/limsa/x")
    assert resolved.environment is dev_env


@pytest.mark.req("PR-04")
def test_a_stale_setting_falls_back_to_the_default(snapshot_builder: SnapshotBuilder) -> None:
    import uuid

    service = snapshot_builder.service("limsa", "/limsa")
    dev = snapshot_builder.developer("ehtesham", environment_ids={service.id: uuid.uuid7()})
    resolved = resolve_service(snapshot_builder.build(), dev, "/limsa/x")
    assert resolved.environment.environment is EnvironmentName.STAGE


@pytest.mark.req("PR-16")
def test_a_missing_environment_row_is_service_not_resolved(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service(
        "limsa",
        "/limsa",
        default_environment=EnvironmentName.STAGE,
        environments={EnvironmentName.DEV: "https://limsa.dev.internal"},
    )
    with pytest.raises(ServiceNotResolvedError) as error:
        resolve_service(snapshot_builder.build(), dev, "/limsa/x")
    assert error.value.detail == "Service 'limsa' has no 'stage' environment configured."


@pytest.mark.req("PR-04")
def test_the_slash_prefix_is_a_catch_all_that_any_longer_prefix_beats(
    snapshot_builder: SnapshotBuilder,
) -> None:
    dev = snapshot_builder.developer("ehtesham")
    catch_all = snapshot_builder.service("api", "/")
    limsa = snapshot_builder.service("limsa", "/limsa")
    snapshot = snapshot_builder.build()
    assert resolve_service(snapshot, dev, "/anything/at/all").service is catch_all
    assert resolve_service(snapshot, dev, "/").service is catch_all
    assert resolve_service(snapshot, dev, "/limsatest").service is catch_all  # not on a boundary
    assert resolve_service(snapshot, dev, "/limsa/x").service is limsa


@pytest.mark.req("PR-04")
def test_stripping_the_slash_prefix_changes_nothing(snapshot_builder: SnapshotBuilder) -> None:
    dev = snapshot_builder.developer("ehtesham")
    snapshot_builder.service("api", "/", strip_prefix=True)
    snapshot = snapshot_builder.build()
    assert resolve_service(snapshot, dev, "/api/Items").upstream_path == "/api/Items"
    assert resolve_service(snapshot, dev, "/").upstream_path == "/"
