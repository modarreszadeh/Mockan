"""`match_request`: the precedence algorithm of arch §7.2. Pure; shared with test-route."""

from collections.abc import Iterable

from mockan.domain.constants import ANY_METHOD
from mockan.domain.enums import ConditionOperator
from mockan.matching.model import CompiledRule, Condition, MatchResult, RequestFacts


def _query_ok(conditions: tuple[Condition, ...], facts: RequestFacts) -> bool:
    for condition in conditions:
        values = facts.query.get(condition.key)
        if not values:
            return False
        if condition.operator is ConditionOperator.EQUALS and condition.value not in values:
            return False
    return True


def _headers_ok(conditions: tuple[Condition, ...], facts: RequestFacts) -> bool:
    # Names are lower-cased at compile time and in RequestFacts; values are case-sensitive.
    for condition in conditions:
        value = facts.headers.get(condition.key)
        if value is None:
            return False
        if condition.operator is ConditionOperator.EQUALS and value != condition.value:
            return False
    return True


def match_request(rules: Iterable[CompiledRule], facts: RequestFacts) -> MatchResult | None:
    """Return the winning enabled rule for `facts`, or `None` to proxy.

    `rules` holds one Developer's enabled rules. Order does not matter (the snapshot pre-sorts them
    so losers are skipped without running their matcher). Equal sort keys keep the first rule.
    """
    method = facts.method.upper()
    lowered = facts.path.lower()
    best: CompiledRule | None = None
    best_params: dict[str, str] = {}
    for rule in rules:
        # TODO(OQ-B5): HEAD does not match a GET rule.
        if rule.method != ANY_METHOD and rule.method != method:
            continue
        if best is not None and rule.sort_key >= best.sort_key:
            continue
        if rule.literal_prefix and not lowered.startswith(rule.literal_prefix):
            continue
        params = rule.matcher.match(facts.path)
        if params is None:
            continue
        if not _query_ok(rule.query_conditions, facts):
            continue
        if not _headers_ok(rule.header_conditions, facts):
            continue
        best, best_params = rule, dict(params)
    if best is None:
        return None
    reason = (
        f"{best.match_type.value} rule “{best.name}” ({best.pattern}) won with priority "
        f"{best.priority}"
    )
    return MatchResult(rule=best, params=best_params, reason=reason)
