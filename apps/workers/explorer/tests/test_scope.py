"""The scope check Explore and authoring share: a whole app is checked a few
screens at a time, each screen with only its own tests and screenshot."""

import uuid
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


def step(screen: str, element: str, **more: str) -> dict[str, str]:
    return {"screen": screen, "element": element, **more}


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
        "Search Harborview",  # seen nowhere: checked in the app when tried
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
    journal = type(
        "J",
        (),
        {"run_id": uuid.uuid4(), "event": lambda self, k, t, d=None: events.append((t, d or ""))},
    )()
    tests = await scope.cover(journal, facts, [invented], rewrite)  # type: ignore[arg-type]
    assert [t["title"] for t in tests] == ["Filter to Inactive"]
    assert tests[0]["not_possible"] == '“Account list” has no combobox "Status"'
    assert told == [["Filter to Inactive"]]  # the check counts its item as not on the page
    assert "Not tried:" in events[-1][1]


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


# A form whose sections each have an unnamed toggle — except Files, which has
# only text where the toggle would be.
SECTIONS = """- paragraph: Details
- button "Icon"
- textbox "Name"
- paragraph: Notes
- button "Icon"
- textbox "Description"
- paragraph: Files
- text: Icon
- button "Choose Files"
- group "Owner":
  - button "Icon"
  - combobox "Owner\""""


def _one(title: str, path: list[dict[str, str]], **more: object) -> dict[str, object]:
    return {"title": title, "start_screen": "Form", "path": path, **more}


def test_a_value_the_app_showed_while_exploring_counts_and_where_it_was_seen_is_kept() -> None:
    facts = [
        {"name": "Form", "elements": '- combobox "Account"'},
        {"name": "Account list", "elements": '- cell "Harborview Supply"'},
    ]
    records = ["Test data the app showed: Account name Northstar 7f3 (created by: New account)."]
    shown = _one(
        "Pick Northstar", [step("Form", 'combobox "Account"')], data={"finds": ["Northstar 7f3"]}
    )
    listed = _one(
        "Pick Harborview",
        [step("Form", 'combobox "Account"')],
        data={"finds": ["Harborview Supply"]},
    )
    nowhere = _one("Pick Acme", [step("Form", 'combobox "Account"')], data={"finds": ["Acme 123"]})
    ok, off = scope.ground([shown, listed, nowhere], facts, records)
    assert off == []  # a value seen nowhere is checked in the app, not set aside
    assert ok[0]["evidence"][0]["source"] == f"record: {records[0]}"
    assert ok[1]["evidence"] == [{"value": "Harborview Supply", "source": "page: Account list"}]
    assert ok[2]["evidence"] == [{"value": "Acme 123", "source": scope.UNSEEN}]


def test_a_repeated_control_must_be_in_the_section_it_names() -> None:
    facts = [{"name": "Form", "elements": SECTIONS}]
    notes = _one("Notes collapses", [step("Form", 'button "Icon"', near="Notes")])
    files = _one("Files collapses", [step("Form", 'button "Icon"', near="Files")])
    owner = _one("Owner collapses", [step("Form", 'button "Icon"', near="Owner")])
    unnamed = _one("Some section collapses", [step("Form", 'button "Icon"')])  # can't tell: kept
    unknown = _one("Other collapses", [step("Form", 'button "Icon"', near="Billing")])  # ditto
    once = _one("Choose a file", [step("Form", 'button "Choose Files"', near="Details")])  # unique
    ok, off = scope.ground([notes, files, owner, unnamed, unknown, once], facts)
    assert [t["title"] for t in ok] == [
        "Notes collapses",
        "Owner collapses",
        "Some section collapses",
        "Other collapses",
        "Choose a file",
    ]
    assert off[0]["not_possible"] == '“Files” on “Form” has no button "Icon"'
    assert off[0]["outcome"] == scope.REJECTED


def test_a_test_may_only_use_files_explorer_can_attach() -> None:
    facts = [{"name": "Form", "elements": '- button "Choose Files"\n- text: invoice-2024.pdf'}]
    path = [step("Form", 'button "Choose Files"')]
    own = _one("Attach a note", path, how_to_run="Attach contact-note-{{unique}}.pdf")
    sample = _one("Attach a PDF", path, how_to_run="Attach repair-estimate-11mb.pdf")
    shown = _one("Open the invoice", path, steps=["Open invoice-2024.pdf"])
    kinds = _one("Types listed", path, expected="Allowed: .pdf, .docx")
    ok, off = scope.ground([own, sample, shown, kinds], facts)
    assert [t["title"] for t in ok] == ["Attach a PDF", "Open the invoice", "Types listed"]
    assert "contact-note-{{unique}}.pdf" in off[0]["not_possible"]


def test_the_same_check_written_twice_is_left_out_by_code() -> None:
    def planned(title: str, element: str, coverage: str = "E-01 Button") -> dict[str, object]:
        return {**_one(title, [step("Form", element)]), "coverage": coverage}

    tests = [
        planned("Save works", 'button "Save"'),
        planned("Pressing Save saves", 'button "Save"'),  # same check, other words
        planned("Save twice", 'button "Save"', "F-19 Double submit"),  # another item
        planned("Cancel works", 'button "Cancel"'),  # another element
        {"title": "Name is required", "coverage": "F-05 Field rules"},  # field rules: never
        {"title": "Name is required", "coverage": "F-05 Field rules"},
    ]
    assert scope.duplicates(tests) == {1: "Left out before trying: the same check as “Save works”"}


async def test_over_the_limit_and_left_out_scenarios_are_kept_with_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = [{"name": "Form", "elements": '- button "Save"'}]
    tests = [_one(f"t{i}", [step("Form", 'button "Save"')], coverage=f"X-{i}") for i in range(4)]

    async def check(*_a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        return [], {"t1": "repeats t0"}

    async def write(*_a: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(scope, "check_scope", check)
    journal = type("J", (), {"run_id": uuid.uuid4(), "event": lambda *a: None})()
    out = await scope.cover(journal, facts, tests, write, ceiling=3)  # type: ignore[arg-type]
    why = {t["title"]: scope.set_aside_reason(t) for t in out}
    assert why == {
        "t0": None,
        "t2": None,
        "t1": "Left out before trying: repeats t0",
        "t3": "Not tried: over the limit of 3 scenarios per run",
    }


def test_what_a_scenario_was_planned_from_is_kept_with_it() -> None:
    t = {
        "title": "x",
        "path": [step("Form", 'button "Save"')],
        "data": {"finds": ["A"]},
        "evidence": [{"value": "A", "source": "page"}],
        "category": "edge",
        "steps": ["s"],
    }
    assert scope.trace(t) == {k: t[k] for k in ("path", "data", "evidence", "category")}
    assert scope.trace(scope.left(t, "why"))["outcome"] == scope.REJECTED


def test_the_sample_files_listed_are_the_ones_handed_out() -> None:
    from explorer_worker import samples

    assert {samples.sample_file(k).name for k in samples.KINDS} <= set(samples.FILES)


def _screen(name: str, aria: str) -> Any:
    from explorer_core import ExplorerScreen

    return ExplorerScreen(
        run_id=uuid.uuid4(), signature=name, name=name, url="u", url_pattern="u", aria=aria
    )


MENU = '- link "Dashboard":\n  - /url: x\n- link "Territories"\n- button "Icon"\n- link "Terms"\n'


def test_the_apps_shared_menu_is_found_from_the_pages_themselves() -> None:
    screens = [
        _screen("Dashboard", MENU + '- heading "Sales"\n- button "Icon"'),
        _screen("Territory list", MENU + '- button "New Territory"'),
        _screen("New territory", MENU + '- textbox "Name"\n- button "Save"'),
    ]
    # Once on every page: shared. "Icon" repeats on a page: can't be told apart.
    assert scope.app_wide_controls(screens) == {
        'link "dashboard"',
        'link "territories"',
        'link "terms"',
    }
    assert scope.app_wide_controls(screens[:2]) == set()  # too few pages to tell
    assert scope.screen_facts(screens)[2]["app_wide"] == sorted(scope.app_wide_controls(screens))


def test_ideas_that_are_not_scenarios_are_set_aside_with_why() -> None:
    facts = [{"name": "Form", "app_wide": ['link "territories"', 'link "terms"']}]

    def idea(title: str, coverage: str, *elements: str) -> dict[str, Any]:
        path = [step("Form", e) for e in elements]
        return {"title": title, "start_screen": "Form", "coverage": coverage, "path": path}

    tests = [
        idea("Territories link opens Territories", "E-02 Link", 'link "Territories"'),
        idea("Terms opens Terms", "E-02 Link", 'link "Terms":'),
        idea("Open the form from the menu", "F-13 Create", 'link "Territories"', 'button "Save"'),
        idea("Name is required", "F-05 Required fields", 'textbox "Name"'),
        {"title": "Name is required on Form", "coverage": "F-05 Field rules"},  # the field rule
    ]
    why = scope.not_needed(tests, facts)
    assert sorted(why) == [0, 1, 3]  # using the menu to get somewhere is fine
    assert "shared menu" in why[0] and "once per field" in why[3]
