"""Mockan route templates: `{name}` is one non-empty segment, `{*name}` the rest (arch §7.1)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from mockan.matching.errors import PatternError
from mockan.matching.paths import normalise, segments

_PARAM = re.compile(r"\{(\*?)([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class _Literal:
    text: str  # lower-cased


@dataclass(frozen=True, slots=True)
class _Param:
    name: str


class TemplateMatcher:
    """A parsed template. Literals are case-insensitive; captures keep the request's case."""

    __slots__ = ("_fixed", "_rest")

    def __init__(self, fixed: tuple[_Literal | _Param, ...], rest: str | None) -> None:
        self._fixed = fixed
        self._rest = rest

    def match(self, path: str) -> Mapping[str, str] | None:
        parts = segments(normalise(path))
        if parts is None:
            return None
        count = len(self._fixed)
        if len(parts) < count or (self._rest is None and len(parts) != count):
            return None
        params: dict[str, str] = {}
        for part, expected in zip(parts, self._fixed, strict=False):
            if isinstance(expected, _Literal):
                if part.lower() != expected.text:
                    return None
            elif part:
                params[expected.name] = part
            else:
                return None
        if self._rest is not None:
            params[self._rest] = "/".join(parts[count:])
        return params


def parse_template(pattern: str) -> TemplateMatcher:
    """Parse a template pattern or raise `PatternError("pattern", ...)`."""
    parts = segments(normalise(pattern)) or []
    fixed: list[_Literal | _Param] = []
    rest: str | None = None
    seen: set[str] = set()
    for index, part in enumerate(parts):
        if "{" not in part and "}" not in part:
            fixed.append(_Literal(part.lower()))
            continue
        found = _PARAM.fullmatch(part)
        if found is None:
            raise PatternError(
                "pattern", f"“{part}” isn't valid. Use {{name}} or {{*name}} as a whole segment."
            )
        star, name = found.groups()
        if star and index != len(parts) - 1:
            raise PatternError("pattern", "{*name} can only be the last segment.")
        if name in seen:
            raise PatternError("pattern", f"Parameter {{{name}}} is used twice.")
        seen.add(name)
        if star:
            rest = name
        else:
            fixed.append(_Param(name))
    return TemplateMatcher(tuple(fixed), rest)
