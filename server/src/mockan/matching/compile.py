"""Pattern and rule compilers, one per match type. Admin save checks and the Gateway share them."""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

import re2

from mockan.domain.constants import ANY_METHOD, DEFAULT_PRIORITY, MAX_REGEX_LENGTH
from mockan.domain.enums import BodyMode, ConditionOperator, MatchType
from mockan.matching.errors import PatternError
from mockan.matching.model import (
    CompiledResponse,
    CompiledRule,
    Condition,
    PathMatcher,
)
from mockan.matching.paths import normalise, segments
from mockan.matching.template import parse_template

TYPE_RANK: Mapping[MatchType, int] = {
    MatchType.EXACT: 0,
    MatchType.TEMPLATE: 1,
    MatchType.PREFIX: 2,
    MatchType.REGEX: 3,
}

_NIL = UUID(int=0)
_EPOCH = datetime.min.replace(tzinfo=UTC)
_LOOKAROUND = re.compile(r"\(\?<?[=!]")
_BACKREFERENCE = re.compile(r"\\[1-9]|\\k<")
_REGEX_META = frozenset("\\.^$*+?()[]{}|")


class _RegexMatch(Protocol):
    def groupdict(self) -> dict[str, str | None]: ...


class _CompiledRegex(Protocol):
    def search(self, text: str) -> _RegexMatch | None: ...


class _ExactMatcher:
    __slots__ = ("_target",)

    def __init__(self, pattern: str) -> None:
        self._target = normalise(pattern.lower())

    def match(self, path: str) -> Mapping[str, str] | None:
        return {} if normalise(path.lower()) == self._target else None


class _PrefixMatcher:
    __slots__ = ("_prefix",)

    def __init__(self, pattern: str) -> None:
        self._prefix = pattern.lower()

    def match(self, path: str) -> Mapping[str, str] | None:
        return {} if path.lower().startswith(self._prefix) else None


class _RegexMatcher:
    __slots__ = ("_regex",)

    def __init__(self, regex: _CompiledRegex) -> None:
        self._regex = regex

    def match(self, path: str) -> Mapping[str, str] | None:
        found = self._regex.search(path)
        if found is None:
            return None
        return {name: value for name, value in found.groupdict().items() if value is not None}


def compile_pattern(match_type: MatchType, pattern: str) -> PathMatcher:
    """Compile `pattern` or raise `PatternError("pattern", message)`.

    The messages mirror `panel/src/lib/checks.ts#patternProblem`; the server is never looser.
    """
    if not pattern.strip():
        raise PatternError("pattern", "Enter a pattern.")
    if match_type is MatchType.REGEX:
        return _compile_regex(pattern)
    if not pattern.startswith("/"):
        raise PatternError("pattern", "Start the pattern with “/”.")
    if re.search(r"\s", pattern):
        raise PatternError("pattern", "Patterns can't contain spaces.")
    if match_type is MatchType.TEMPLATE:
        return parse_template(pattern)
    if "{" in pattern or "}" in pattern:
        raise PatternError(
            "pattern",
            f"{match_type.value} patterns can't contain {{ or }}. Use Template for parameters.",
        )
    return _ExactMatcher(pattern) if match_type is MatchType.EXACT else _PrefixMatcher(pattern)


def literal_prefix(match_type: MatchType, pattern: str) -> str:
    """Lower-cased text that every path matched by `pattern` starts with (a cheap pre-filter).

    Only a necessary condition: the matcher still decides. "" disables the pre-filter.
    """
    if match_type is MatchType.EXACT:
        return normalise(pattern.lower())
    if match_type is MatchType.PREFIX:
        return pattern.lower()
    if match_type is MatchType.TEMPLATE:
        literals: list[str] = []
        for part in segments(normalise(pattern)) or []:
            if "{" in part:
                break
            literals.append(part.lower())
        return "/" + "/".join(literals) if literals else ""
    return _regex_literal_prefix(pattern)


def _regex_literal_prefix(pattern: str) -> str:
    """Literal text after a leading `^`, up to the first metacharacter (conservative)."""
    if not pattern.startswith("^") or "|" in pattern:
        return ""
    literal: list[str] = []
    for char in pattern[1:]:
        if char in _REGEX_META:
            if char in "*+?{" and literal:
                literal.pop()  # the quantifier applies to the previous character
            break
        literal.append(char)
    return "".join(literal).lower()


def _compile_regex(pattern: str) -> PathMatcher:
    # TODO(OQ-B3): matched against the original-case path; authors use (?i) for case-insensitive.
    # D-17: RE2 is linear-time, so no per-match timeout is needed.
    if len(pattern) > MAX_REGEX_LENGTH:
        raise PatternError(
            "pattern", f"Regex patterns can be at most {MAX_REGEX_LENGTH} characters."
        )
    if _LOOKAROUND.search(pattern):
        raise PatternError("pattern", "RE2 doesn't support lookahead or lookbehind.")
    if _BACKREFERENCE.search(pattern):
        raise PatternError("pattern", "RE2 doesn't support backreferences.")
    try:
        return _RegexMatcher(re2.compile(pattern))
    except re2.error as error:
        detail = error.args[0] if error.args else b"unknown error"  # RE2 reports bytes
        text = (
            detail.decode("utf-8", errors="replace") if isinstance(detail, bytes) else str(detail)
        )
        raise PatternError("pattern", f"Invalid regex: {text}") from error


def _compile_conditions(
    field: str, conditions: Sequence[Condition], *, lowercase_keys: bool
) -> tuple[Condition, ...]:
    compiled: list[Condition] = []
    for index, condition in enumerate(conditions):
        key = condition.key.strip()
        if not key:
            raise PatternError(f"{field}.{index}.key", "Enter a name.")
        if condition.operator is ConditionOperator.EQUALS and condition.value is None:
            raise PatternError(f"{field}.{index}.value", "Enter a value.")
        compiled.append(
            Condition(
                key.lower() if lowercase_keys else key,
                condition.operator,
                condition.value if condition.operator is ConditionOperator.EQUALS else None,
            )
        )
    return tuple(compiled)


def compile_response(
    *,
    response_id: UUID,
    name: str,
    status_code: int,
    headers: Mapping[str, str],
    content_type: str,
    body: str,
    body_mode: BodyMode = BodyMode.STATIC,
    delay_ms: int = 0,
) -> CompiledResponse:
    return CompiledResponse(
        id=response_id,
        name=name,
        status_code=status_code,
        headers=MappingProxyType(dict(headers)),
        content_type=content_type,
        body=body,
        body_bytes=body.encode("utf-8"),
        body_mode=body_mode,
        delay_ms=delay_ms,
    )


def compile_rule(
    *,
    match_type: MatchType,
    pattern: str,
    method: str = ANY_METHOD,
    query_conditions: Sequence[Condition] = (),
    header_conditions: Sequence[Condition] = (),
    priority: int = DEFAULT_PRIORITY,
    rule_id: UUID = _NIL,
    developer_id: UUID = _NIL,
    service_id: UUID | None = None,
    name: str = "",
    created_at: datetime = _EPOCH,
    responses: Sequence[CompiledResponse] = (),
    active_response_id: UUID | None = None,
) -> CompiledRule:
    """Compile a MockRule; raises `PatternError(field, message)` for the first invalid field.

    The Admin calls this with just the match fields to validate a rule on save, so what it accepts
    is exactly what the Gateway will run (§2 risk: validation and behaviour must not drift).
    """
    matcher = compile_pattern(match_type, pattern)
    query = _compile_conditions("queryConditions", query_conditions, lowercase_keys=False)
    headers = _compile_conditions("headerConditions", header_conditions, lowercase_keys=True)
    active = next((r for r in responses if r.id == active_response_id), None)
    return CompiledRule(
        id=rule_id,
        developer_id=developer_id,
        service_id=service_id,
        name=name,
        method=method.upper(),
        match_type=match_type,
        pattern=pattern,
        matcher=matcher,
        literal_prefix=literal_prefix(match_type, pattern),
        query_conditions=query,
        header_conditions=headers,
        priority=priority,
        created_at=created_at,
        sort_key=(priority, TYPE_RANK[match_type], -len(pattern), created_at),
        responses=tuple(responses),
        active_response=active,
    )
