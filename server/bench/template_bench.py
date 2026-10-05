"""Manual benchmark (not a CI gate): rendering templated bodies on the event loop (PR-19, B8c).

Rendering runs on the Gateway's event loop (arch §14 rule 10), so its cost is the added latency of
a templated mock. Measures p50/p95/p99 of `render()` for three realistic templates after the
template is compiled (as the Gateway holds it).

Run from server/:  uv run python bench/template_bench.py [--runs 5000]
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mockan.matching.templating import compile_template, render

CASES = {
    "route + query (small JSON)": (
        '{"id":{{ route.id }},"page":"{{ request.query.page }}","path":"{{ request.path }}"}',
        1,
    ),
    "fake person (8 generators)": (
        '{"name":"{{ fake.name() }}","email":"{{ fake.email() }}","city":"{{ fake.city() }}",'
        '"phone":"{{ fake.phone_number() }}","company":"{{ fake.company() }}",'
        '"id":"{{ fake.uuid4() }}","age":{{ fake.random_int(18, 90) }},"job":"{{ fake.job() }}"}',
        1,
    ),
    "list of 50 rows (2 generators each)": (
        "[{% for i in range(50) %}"
        '{"i":{{ i }},"name":"{{ fake.name() }}","id":"{{ fake.uuid4() }}"}'
        "{% if not loop.last %},{% endif %}{% endfor %}]",
        50,
    ),
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5000)
    runs = parser.parse_args().runs
    print(f"{'template':<40} {'p50':>9} {'p95':>9} {'p99':>9}   ({runs} renders each)")
    for label, (source, _rows) in CASES.items():
        template = compile_template(source)
        arguments = {
            "method": "GET",
            "path": "/limsa/orders/42",
            "query": {"page": ["2"]},
            "headers": {"x-tenant": "acme"},
            "params": {"id": "42"},
        }
        render(template, **arguments)  # warm up (the first fake.* call creates the Faker)
        timings: list[float] = []
        for _ in range(runs):
            started = time.perf_counter()
            render(template, **arguments)
            timings.append((time.perf_counter() - started) * 1000)
        print(
            f"{label:<40} {statistics.median(timings):>7.3f}ms "
            f"{percentile(timings, 0.95):>7.3f}ms {percentile(timings, 0.99):>7.3f}ms"
        )


if __name__ == "__main__":
    main()
