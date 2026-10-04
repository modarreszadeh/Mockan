"""Manual micro-benchmark (not a CI gate): match_request p95 with 500 rules for one Developer (B1).

Run from server/:  uv run python bench/match_bench.py
"""

import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

from mockan.domain.enums import MatchType
from mockan.matching.compile import compile_rule
from mockan.matching.matcher import match_request
from mockan.matching.model import RequestFacts
from mockan.matching.snapshot import sort_rules

RULES = 500
ITERATIONS = 20_000
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def build() -> tuple:
    developer = uuid.uuid7()
    kinds = (MatchType.EXACT, MatchType.TEMPLATE, MatchType.PREFIX, MatchType.REGEX)
    patterns = {
        MatchType.EXACT: "/limsa/api/v1/res{i}/list",
        MatchType.TEMPLATE: "/limsa/api/v1/tpl{i}/{{id}}/detail",
        MatchType.PREFIX: "/limsa/api/v1/pre{i}/",
        MatchType.REGEX: r"^/limsa/api/v1/rx{i}/\d+$",
    }
    rules = [
        compile_rule(
            match_type=kinds[i % 4],
            pattern=patterns[kinds[i % 4]].format(i=i),
            method="GET" if i % 3 else "ANY",
            priority=100 + (i % 5),
            created_at=BASE + timedelta(seconds=i),
            developer_id=developer,
            name=f"rule-{i}",
        )
        for i in range(RULES)
    ]
    return sort_rules(rules)


def main() -> None:
    rules = build()
    cases = {
        "miss (proxy)": RequestFacts("GET", "/limsa/api/v1/orders/42", {}, {}),
        "hit exact (last)": RequestFacts("GET", "/limsa/api/v1/res496/list", {}, {}),
        "hit regex": RequestFacts("GET", "/limsa/api/v1/rx499/12345", {}, {}),
    }
    for label, facts in cases.items():
        samples = []
        for _ in range(ITERATIONS):
            started = time.perf_counter()
            match_request(rules, facts)
            samples.append((time.perf_counter() - started) * 1000)
        samples.sort()
        p95 = samples[int(len(samples) * 0.95)]
        p50 = statistics.median(samples)
        print(f"{label:18} p50={p50:.3f} ms  p95={p95:.3f} ms  (target p95 < 0.2 ms)")


if __name__ == "__main__":
    main()
