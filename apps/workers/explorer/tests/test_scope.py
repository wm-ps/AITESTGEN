"""The scope check Explore and authoring share: a whole app is checked a few
screens at a time, each screen with only its own tests and screenshot."""

from typing import Any

import pytest
from explorer_worker import scope


async def test_a_whole_app_is_checked_a_few_screens_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], list[str], int]] = []

    async def part(
        screens: list[dict[str, Any]], tests: list[dict[str, Any]], shots: list[bytes]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        calls.append(([s["name"] for s in screens], [t["title"] for t in tests], len(shots)))
        name = screens[0]["name"]
        return [{"screen": name, "id": "P-01", "status": "covered"}], {f"dup {name}": "duplicate"}

    monkeypatch.setattr(scope, "_check_part", part)
    screens = [{"name": f"S{i}"} for i in range(6)]
    tests = [{"title": "on S5", "start_screen": "S5"}, {"title": "nowhere", "start_screen": "X"}]
    report, leave_out = await scope.check_scope(screens, tests, {f"S{i}": b"x" for i in range(6)})
    assert sorted(calls) == [
        (["S0", "S1", "S2", "S3"], [], 4),
        (["S4", "S5"], ["on S5"], 2),
    ]
    assert [r["screen"] for r in report] == ["S0", "S4"]
    assert leave_out == {"dup S0": "duplicate", "dup S4": "duplicate"}
    assert len(scope.SCOPE_ITEMS) == 49
