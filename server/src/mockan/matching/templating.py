"""Templated response bodies (PR-19, arch §7.3): a Jinja2 sandbox with request data and fake data.

A `Template` body is compiled when the snapshot is built (and when the Admin saves it, with this
same function), never per request. Rendering runs on the event loop, so it is bounded: the output
may not exceed 1 MB, `range()` stops at 1,000, and only a curated set of Faker generators exists.

Context available to a template:

* `request.method`, `request.path` (after the slug), `request.query` (first value per name),
  `request.query_all` (a list per name), `request.headers` (lower-case names);
* `route.<name>` for the `{name}` / `{*name}` parameters of a Template rule or the named groups of
  a Regex rule;
* `fake.<generator>()`, e.g. `{{ fake.name() }}`, `{{ fake.uuid4() }}`,
  `{{ fake.random_int(1, 9) }}`.

A missing variable is an error, not an empty string: it surfaces as `mock_render_failed` with
the reason, so a typo never serves a silently wrong mock.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from jinja2 import Template, TemplateSyntaxError
from jinja2.runtime import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from mockan.domain.constants import MAX_BODY_BYTES
from mockan.matching.errors import PatternError

MAX_RANGE = 1_000

# Faker generators a template may call: pure, cheap, and no way to reach the rest of the object.
FAKE_GENERATORS = frozenset(
    {
        "name", "first_name", "last_name", "user_name", "email", "safe_email", "phone_number",
        "address", "street_address", "city", "state", "postcode", "country", "company", "job",
        "word", "words", "sentence", "sentences", "paragraph", "text", "uuid4", "random_int",
        "random_element", "pyint", "pyfloat", "pybool", "boolean", "date", "date_time",
        "iso8601", "date_of_birth", "url", "domain_name", "ipv4", "ipv6", "color_name",
        "hex_color", "currency_code", "credit_card_number", "iban", "locale",
    }
)  # fmt: skip


class TemplateRenderError(Exception):
    """Rendering failed; the message is safe to show to the Developer (`mock_render_failed`)."""


class FakeData:
    """`fake` in a template: a whitelist over one lazily created Faker instance."""

    def __init__(self) -> None:
        self._faker: Any = None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)  # Python's own probes (`hasattr`, copy...) stay normal
        if name not in FAKE_GENERATORS:  # not an AttributeError: Jinja would turn it into Undefined
            raise TemplateRenderError(f"fake.{name} doesn't exist: it is not a known generator")
        if self._faker is None:
            from faker import Faker  # imported on first use: it is slow to import

            self._faker = Faker()
        return getattr(self._faker, name)


def _safe_range(*args: int) -> range:
    produced = range(*args)
    if len(produced) > MAX_RANGE:
        raise OverflowError(f"range() can produce at most {MAX_RANGE} numbers")
    return produced


def _environment() -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        autoescape=False,  # JSON, XML, plain text: escaping would corrupt them
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # The defaults include `lipsum`, which can build huge strings, and an unbounded `range`.
    env.globals = {"range": _safe_range, "fake": FakeData(), "namespace": env.globals["namespace"]}
    return env


_ENV = _environment()


def compile_template(source: str) -> Template:
    """Compile a body template or raise `PatternError("body", message)` with the line number."""
    try:
        return _ENV.from_string(source)
    except TemplateSyntaxError as error:
        raise PatternError("body", f"Line {error.lineno}: {error.message}") from error


def render(
    template: Template,
    *,
    method: str,
    path: str,
    query: Mapping[str, Sequence[str]],
    headers: Mapping[str, str],
    params: Mapping[str, str],
) -> str:
    """Render `template` for one request. Raises `TemplateRenderError`."""
    context = {
        "request": {
            "method": method,
            "path": path,
            "query": {name: values[0] for name, values in query.items() if values},
            "query_all": {name: list(values) for name, values in query.items()},
            "headers": dict(headers),
        },
        "route": dict(params),
    }
    parts: list[str] = []
    size = 0
    try:
        for chunk in template.generate(context):
            size += len(chunk.encode("utf-8", errors="replace"))
            if size > MAX_BODY_BYTES:
                raise TemplateRenderError("The rendered body is larger than 1 MB.")
            parts.append(chunk)
    except TemplateRenderError:
        raise
    except Exception as error:  # a template can raise anything; none of it may leak or crash
        raise TemplateRenderError(f"{type(error).__name__}: {error}") from error
    return "".join(parts)
