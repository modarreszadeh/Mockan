"""Same ordered cases as panel/src/lib/precedence.parity.test.ts (shared JSON fixture)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mockan.domain.enums import MatchType
from mockan.matching.compile import compile_rule
from mockan.matching.matcher import match_request
from mockan.matching.snapshot import sort_rules
from tests.support.snapshot_builder import facts

_FIXTURE = json.loads((Path(__file__).parent / "precedence_parity.json").read_text())
_CASES: list[dict[str, Any]] = _FIXTURE["cases"]


@pytest.mark.req("PR-05")
@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_precedence_order_and_winner_match_the_panel(case: dict[str, Any]) -> None:
    rules = [
        compile_rule(
            match_type=MatchType(r["matchType"]),
            pattern=r["pattern"],
            priority=r["priority"],
            name=r["id"],
            created_at=datetime.fromisoformat(r["createdAt"]),
        )
        for r in case["rules"]
    ]
    assert [rule.name for rule in sort_rules(rules)] == case["order"]
    result = match_request(rules, facts(case["path"]))
    assert result is not None
    assert result.rule.name == case["order"][0]
