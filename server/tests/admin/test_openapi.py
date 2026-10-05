"""The OpenAPI document is the contract with the Panel: contract changes must show up in a diff."""

import json
import os
from pathlib import Path

import pytest

from mockan.admin.app import create_app
from mockan.infrastructure.settings import MockanSettings

SNAPSHOT = Path(__file__).with_name("openapi.snapshot.json")


def build_schema() -> dict[str, object]:
    settings = MockanSettings(_env_file=None, auth_mode="dev")  # type: ignore[call-arg]
    return create_app(settings).openapi()


def test_openapi_matches_the_snapshot() -> None:
    actual = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_OPENAPI_SNAPSHOT"):
        SNAPSHOT.write_text(actual)
    assert actual == SNAPSHOT.read_text(), (
        "The Admin API contract changed. If that is intended, update the Panel "
        "(`panel/src/api/types.ts`) and `Backend/admin-api.md`, then regenerate with "
        "`UPDATE_OPENAPI_SNAPSHOT=1 uv run pytest tests/admin/test_openapi.py`."
    )


@pytest.mark.req("PR-16")
def test_every_422_is_the_problem_shape_not_fastapis_default() -> None:
    schema = build_schema()
    paths = schema["paths"]
    assert isinstance(paths, dict)
    seen = 0
    for path, operations in paths.items():
        for method, operation in operations.items():
            responses = operation["responses"]
            if "422" not in responses:
                continue
            seen += 1
            ref = responses["422"]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/Problem"), (method, path)
    assert seen > 0
    assert "HTTPValidationError" not in json.dumps(schema)
