"""Every Phase 1 (P0) requirement has an acceptance test (PRD §11)."""

import re
from pathlib import Path

# PR-18 (Panel + onboarding) is covered by the Panel's own tests.
PHASE_1 = [f"PR-{n:02d}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 16)]


def test_every_phase_1_requirement_has_an_acceptance_test() -> None:
    marked: dict[str, list[str]] = {}
    for path in Path(__file__).parent.glob("test_*.py"):
        text = path.read_text()
        for match in re.finditer(r'@pytest\.mark\.req\("(PR-\d+)"\)\s+async def (test_\w+)', text):
            marked.setdefault(match.group(1), []).append(match.group(2))
    missing = [pr for pr in PHASE_1 if pr not in marked]
    assert not missing, f"no acceptance test for {missing}"
    for pr, names in marked.items():
        assert all(name.startswith(f"test_{pr.lower().replace('-', '_')}_") for name in names), pr
