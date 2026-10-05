"""Response body templates: sandbox, request data, fake data, bounds (PR-19, arch §7.3)."""

import json
import uuid

import pytest

from mockan.domain.constants import MAX_BODY_BYTES
from mockan.domain.enums import BodyMode
from mockan.matching.compile import compile_response
from mockan.matching.errors import PatternError
from mockan.matching.templating import (
    FAKE_GENERATORS,
    MAX_RANGE,
    FakeData,
    TemplateRenderError,
    compile_template,
    render,
)

pytestmark = pytest.mark.req("PR-19")


def run(
    source: str,
    *,
    method: str = "GET",
    path: str = "/limsa/orders/42",
    query: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> str:
    return render(
        compile_template(source),
        method=method,
        path=path,
        query=query or {},
        headers=headers or {},
        params=params or {},
    )


def test_request_data_and_route_params_are_available() -> None:
    body = run(
        '{"id":{{ route.id }},"m":"{{ request.method }}","p":"{{ request.path }}",'
        '"page":"{{ request.query.page }}","all":{{ request.query_all.tag | tojson }},'
        '"tenant":"{{ request.headers["x-tenant"] }}"}',
        params={"id": "42"},
        query={"page": ["2", "3"], "tag": ["a", "b"], "empty": []},
        headers={"x-tenant": "acme"},
    )

    assert json.loads(body) == {
        "id": 42,
        "m": "GET",
        "p": "/limsa/orders/42",
        "page": "2",  # the first value
        "all": ["a", "b"],
        "tenant": "acme",
    }


def test_a_parameterless_query_name_with_no_values_is_not_in_query() -> None:
    assert run("{{ request.query.get('empty', 'none') }}", query={"empty": []}) == "none"


def test_loops_conditions_and_filters_work() -> None:
    body = run(
        "[{% for i in range(3) %}{{ i * 2 }}{% if not loop.last %},{% endif %}{% endfor %}]"
        "{{ 'x' | upper }}"
    )

    assert body == "[0,2,4]X"


def test_a_trailing_newline_is_kept() -> None:
    assert run("line\n") == "line\n"


def test_fake_data_generators_work_and_vary() -> None:
    body = run(
        '{"name":"{{ fake.name() }}","id":"{{ fake.uuid4() }}","n":{{ fake.random_int(5, 9) }},'
        '"mail":"{{ fake.email() }}"}'
    )

    data = json.loads(body)
    assert data["name"] and "@" in data["mail"]
    assert uuid.UUID(data["id"])
    assert 5 <= data["n"] <= 9
    assert run("{{ fake.uuid4() }}") != run("{{ fake.uuid4() }}")


@pytest.mark.parametrize("name", sorted(FAKE_GENERATORS))
def test_every_whitelisted_generator_exists_in_faker(name: str) -> None:
    assert callable(getattr(FakeData(), name))


def test_python_probes_of_private_names_behave_normally() -> None:
    assert not hasattr(FakeData(), "__deepcopy__")


def test_only_whitelisted_generators_are_reachable() -> None:
    with pytest.raises(TemplateRenderError, match=r"fake\.seed_instance doesn't exist"):
        run("{{ fake.seed_instance(1) }}")
    with pytest.raises(TemplateRenderError):
        run("{{ fake._faker }}")


def test_a_missing_variable_is_an_error_not_an_empty_string() -> None:
    with pytest.raises(TemplateRenderError, match="UndefinedError"):
        run("{{ route.id }}")  # not a Template rule: no parameters
    with pytest.raises(TemplateRenderError):
        run("{{ nothing }}")


@pytest.mark.parametrize(
    "source",
    [
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ request.__class__ }}",
        "{{ lipsum(1000) }}",  # removed global
        "{{ cycler.__init__.__globals__ }}",
    ],
)
def test_the_sandbox_blocks_escapes(source: str) -> None:
    with pytest.raises(TemplateRenderError):
        run(source)


def test_range_is_capped() -> None:
    assert run(f"{{{{ range({MAX_RANGE}) | length }}}}") == str(MAX_RANGE)
    with pytest.raises(TemplateRenderError, match="OverflowError"):
        run(f"{{{{ range({MAX_RANGE + 1}) | length }}}}")


def test_output_is_capped_at_one_megabyte() -> None:
    chunk = "x" * 1000
    assert len(run("{% for i in range(500) %}" + chunk + "{% endfor %}")) == 500_000
    with pytest.raises(TemplateRenderError, match="larger than 1 MB"):
        run(
            "{% for i in range(1000) %}{% for j in range(2) %}" + chunk + "{% endfor %}{% endfor %}"
        )
    assert MAX_BODY_BYTES == 1_048_576


def test_runtime_errors_become_render_errors_with_the_reason() -> None:
    with pytest.raises(TemplateRenderError, match="ZeroDivisionError"):
        run("{{ 1 / 0 }}")
    with pytest.raises(TemplateRenderError, match="TypeError"):
        run("{{ route.id + 1 }}", params={"id": "x"})


def test_a_syntax_error_names_the_line() -> None:
    with pytest.raises(PatternError) as error:
        compile_template("ok\n{% for x in %}\n")

    assert error.value.field == "body"
    assert error.value.message.startswith("Line 2:")


def test_a_template_response_is_compiled_when_the_response_is_built() -> None:
    response = compile_response(
        response_id=uuid.uuid4(),
        name="t",
        status_code=200,
        headers={},
        content_type="application/json",
        body="{{ fake.uuid4() }}",
        body_mode=BodyMode.TEMPLATE,
    )
    plain = compile_response(
        response_id=uuid.uuid4(),
        name="p",
        status_code=200,
        headers={},
        content_type="application/json",
        body="{{ not a template }}",
    )

    assert response.template is not None
    assert plain.template is None  # a Static body is never interpreted
    with pytest.raises(PatternError):
        compile_response(
            response_id=uuid.uuid4(),
            name="bad",
            status_code=200,
            headers={},
            content_type="text/plain",
            body="{% if %}",
            body_mode=BodyMode.TEMPLATE,
        )
