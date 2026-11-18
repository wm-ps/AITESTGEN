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
        screens: list[dict[str, Any]],
        tests: list[dict[str, Any]],
        shots: list[bytes],
        _cant: list[str] | None = None,
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


ACCOUNTS = """- heading "Accounts" [level=1]
- button "New Account"
- textbox "Search accounts..."
- button "Export"
- table:
  - rowgroup:
    - row "Account Name Status":
      - columnheader "Account Name"
      - columnheader "Status"
  - rowgroup:
""" + "\n".join(
    f'    - row "Account {i} Active":\n      - cell "Account {i}"\n      - button "Edit account"'
    for i in range(30)
)


def test_a_page_is_planned_from_its_own_elements_with_its_first_rows() -> None:
    from datetime import datetime

    from explorer_core import ExplorerScreen

    screen = ExplorerScreen(
        run_id=__import__("uuid").uuid4(),
        signature="s",
        name="Account list",
        url="u",
        url_pattern="u",
        aria=ACCOUNTS,
        created_at=datetime(2026, 11, 18),
    )
    [facts] = scope.screen_facts([screen])
    elements = facts["elements"]
    assert 'columnheader "Account Name"' in elements and 'button "Edit account"' in elements
    assert 'row "Account 9 Active"' in elements and "Account 10" not in elements  # first 10 rows
    assert 'row "Account Name Status"' in elements  # the header row is no data row to cut


def step(screen: str, element: str) -> dict[str, str]:
    return {"screen": screen, "element": element}


FORM = '- heading "New Account"\n- textbox "Account Name"\n- button "Save Account"'


def test_a_flow_is_planned_only_when_every_step_is_there() -> None:
    facts = [
        {
            "name": "Account list",
            "elements": scope.trim_rows(ACCOUNTS),
            "leads_to": [{"action": "New Account", "to": "New account form"}],
        },
        {"name": "New account form", "elements": FORM},
        {"name": "Account details", "elements": '- heading "Account"'},
    ]

    def test(title: str, path: list[dict[str, str]], **more: object) -> dict[str, object]:
        return {"title": title, "start_screen": "Account list", "path": path, **more}

    search = test(
        "Search finds Account 3",
        [step("Account list", 'textbox "Search accounts..."')],
        data={"finds": ["Account 3"]},
    )
    create = test(
        "Create an account",
        [
            step("Account list", 'button "New Account"'),
            step("New account form", 'textbox "Account Name"'),
            step("New account form", 'button "Save Account"'),
        ],
    )
    wrong_button = test(
        "Edit opens the form",
        [
            step("Account list", 'button "Edit account"'),
            step("New account form", 'textbox "Account Name"'),
        ],
    )
    wrong_page = test("Save from the list", [step("Account list", 'button "Save Account"')])
    no_route = test(
        "Open details",
        [step("Account list", 'cell "Account 0"'), step("Account details", 'heading "Account"')],
    )
    unseen = test("Confirm delete", [step("Delete dialog", 'button "Yes"')])
    invented_value = test(
        "Search Harborview",
        [step("Account list", 'textbox "Search accounts..."')],
        data={"finds": ["Harborview"]},
    )
    silent = test("Sort by name", [])
    rule = {
        "title": "Name is required",
        "start_screen": "Account list",
        "coverage": "F-05 Field rules",
    }
    ok, off = scope.ground(
        [search, create, wrong_button, wrong_page, no_route, unseen, invented_value, silent, rule],
        facts,
    )
    assert [t["title"] for t in ok] == [
        "Search finds Account 3",
        "Create an account",
        "Name is required",
    ]
    why = {t["title"]: t["not_possible"] for t in off}
    assert why["Edit opens the form"] == (
        'button "Edit account" on “Account list” was never seen to lead to “New account form” '
        "(seen: New Account)"
    )
    assert why["Save from the list"] == '“Account list” has no button "Save Account"'
    assert why["Open details"] == "no way was seen from “Account list” to “Account details”"
    assert why["Confirm delete"] == "goes to a screen Explorer never saw: “Delete dialog”"
    assert why["Search Harborview"] == "the value “Harborview” isn't on its pages"
    assert why["Sort by name"].startswith("doesn't say which page")


def test_a_screen_says_where_its_actions_lead() -> None:
    from datetime import datetime

    from explorer_core import ExplorerScreen

    screen = ExplorerScreen(
        run_id=__import__("uuid").uuid4(),
        signature="s",
        name="Account list",
        url="u",
        url_pattern="u",
        created_at=datetime(2026, 11, 18),
    )
    [facts] = scope.screen_facts(
        [screen],
        ["Account list --New Account--> New account form", "Account list --Sort--> Account list"],
    )
    assert facts["leads_to"] == [{"action": "New Account", "to": "New account form"}]


async def test_a_scenario_the_page_cant_support_is_rewritten_once_then_kept_aside(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = [{"name": "Account list", "elements": ACCOUNTS}]
    invented = {
        "title": "Filter to Inactive",
        "start_screen": "Account list",
        "path": [step("Account list", "combobox")],
    }
    told: list[list[str]] = []

    async def check(*a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        told.append([t["title"] for t in a[3] or []])
        return [{"screen": "Account list", "id": "L-09", "status": "not_applicable"}], {}

    async def rewrite(instruction: str, only: list[str]) -> list[dict[str, Any]]:
        assert "Filter to Inactive" in instruction and only == ["Account list"]
        return [{**invented, "path": [step("Account list", 'combobox "Status"')]}]  # still not

    monkeypatch.setattr(scope, "check_scope", check)
    events: list[tuple[str, str]] = []
    journal = type("J", (), {"event": lambda self, k, t, d=None: events.append((t, d or ""))})()
    tests = await scope.cover(journal, facts, [invented], rewrite)  # type: ignore[arg-type]
    assert [t["title"] for t in tests] == ["Filter to Inactive"]
    assert tests[0]["not_possible"] == '“Account list” has no combobox "Status"'
    assert told == [["Filter to Inactive"]]  # the check counts its item as not on the page
    assert "Can't be tested on these pages:" in events[-1][1]


def test_a_screen_keeps_its_fullest_element_structure() -> None:
    import uuid

    from domain import Application, Organization
    from explorer_core import ExplorerRun, ExplorerScreen
    from explorer_worker.db import engine
    from explorer_worker.journal import Journal
    from sqlmodel import Session

    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id, name="x", url="https://x", environment="staging", secret_ref=""
        )
        session.add(app)
        session.flush()
        run = ExplorerRun(application_id=app.id, status="tested")
        session.add(run)
        session.commit()
        run_id = run.id
    seen = {"name": "Account list", "view_kind": "list", "url": "u", "url_pattern": "/accounts"}
    journal = Journal(run_id)
    screen_id, _ = journal.upsert_screen("s", {**seen, "aria": '- heading "Accounts"'})
    journal.upsert_screen("s", {**seen, "aria": ACCOUNTS})  # the rows have loaded
    journal.upsert_screen("s", {**seen, "aria": None})  # a visit that read nothing
    with Session(engine) as session:
        assert session.get(ExplorerScreen, screen_id).aria == ACCOUNTS  # type: ignore[union-attr]
