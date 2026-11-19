"""Authoring: a user's request carried out by Explorer on its own path —
the request becomes the Goal, only what was asked is planned, no hunt, and
the run ends by generating the test cases for what it added."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from explorer_worker import activities as ex
from explorer_worker.authoring import activities as au
from explorer_worker.authoring import plan, promote, request
from explorer_worker.authoring.workflow import AuthoringRunWorkflow
from explorer_worker.promote import identity_key as explorer_identity_key
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from workflows import GENERATION_TASK_QUEUE


def test_the_request_is_the_summary_and_the_walk_is_the_request_word_for_word() -> None:
    prompt = "Open the app and tap Report an insurance claim. Enter policy PL-10001."
    reading = {
        "title": "Report a claim",
        "flow": "Report a claim up to policy search",
        "scenarios": [],
        "questions": [{"screen": "Your request", "question": "Which date?", "options": []}],
    }
    brief = request.first_summary("FNOL", prompt, reading)
    assert brief["app_name"] == "FNOL"
    assert [q["question"] for q in brief["questions_for_you"]] == ["Which date?"]
    # No Goal: nothing else is explored, so nothing needs fencing off.
    assert "focus" not in brief
    mission = plan.request_mission(prompt, brief["request"])
    assert prompt in mission["instructions"]
    assert mission["kind"] == "custom"  # walked once, not again to find other screens
    assert mission["why"] == plan.REQUEST_MISSION


def test_reading_keeps_only_the_scenarios_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ask_json(system: str, user: str, **_: Any) -> dict[str, Any]:
        assert "Search policy POL-1" in user
        return {
            "title": "Policy search",
            "flow": "Search a policy",
            "scenarios": ["Search POL-1 finds it", "", "Unknown number shows an error"],
            "count": "2",
            "only": None,
            "questions": [{"question": f"Q{i}", "options": ["a"]} for i in range(5)] + ["junk"],
        }

    monkeypatch.setattr(request, "ask_json", ask_json)
    out = asyncio.run(request.read_request("Search policy POL-1"))
    assert out["scenarios"] == ["Search POL-1 finds it", "Unknown number shows an error"]
    assert out["count"] == 2 and out["only"] is None
    assert [q["question"] for q in out["questions"]] == ["Q0", "Q1", "Q2"]
    assert all(q["screen"] == "Your request" for q in out["questions"])


def test_authored_journeys_never_share_a_key_with_explorers() -> None:
    key = promote.identity_key(uuid.uuid4())
    assert key.startswith("explorer-author:")
    assert not key.startswith(explorer_identity_key("x").split(":")[0] + ":")


@workflow.defn(name="SuiteGenerationWorkflow")
class FakeSuiteGeneration:
    @workflow.run
    async def run(self, journey_id: str) -> list[str]:
        await workflow.execute_activity(
            "record_generated", journey_id, start_to_close_timeout=timedelta(minutes=1)
        )
        return []


@pytest.mark.parametrize(("asks", "blank"), [(True, False), (False, False), (False, True)])
async def test_full_run_follows_the_request_then_generates_test_cases(
    asks: bool, blank: bool
) -> None:
    calls: list[str] = []
    missions = ["m1"]
    tests = ["t1", "t2"]
    generated: list[str] = []

    def fake(name: str, result: Any = None):  # type: ignore[no-untyped-def]
        @activity.defn(name=name)
        async def step(run_id: str) -> Any:
            calls.append(name)
            return result

        return step

    @activity.defn(name=au.QUEUED_MISSIONS_ACTIVITY)
    async def queued(run_id: str) -> list[str]:
        return list(missions)

    @activity.defn(name=ex.RUN_MISSION_ACTIVITY)
    async def run_mission(run_id: str, mission_id: str) -> str:
        missions.remove(mission_id)
        calls.append(f"mission:{mission_id}")
        return "done"

    retries = [True] if blank else []

    @activity.defn(name=au.RETRY_BLANK_ACTIVITY)
    async def blank_retry(run_id: str) -> bool:
        if retries:  # the app was blank: walk the request again
            missions.append("m1")
        return bool(retries and retries.pop())

    @activity.defn(name=au.PLANNED_TESTS_ACTIVITY)
    async def planned(run_id: str) -> list[str]:
        return list(tests)

    @activity.defn(name=ex.BUILD_TEST_ACTIVITY)
    async def build(run_id: str, test_id: str) -> str:
        tests.remove(test_id)
        calls.append(f"build:{test_id}")
        return "proven"

    @activity.defn(name="record_generated")
    async def record_generated(journey_id: str) -> None:
        generated.append(journey_id)

    refills = [1, 0]  # one replacement, then the number is met

    @activity.defn(name=au.REFILL_ACTIVITY)
    async def refill(run_id: str) -> int:
        added = refills.pop(0)
        if added:
            tests.append("t3")
        calls.append(f"refill:{added}")
        return added

    steps = [
        fake(au.READ_REQUEST_ACTIVITY),
        fake(au.START_ACTIVITY, "awaiting_confirmation" if asks else "confirmed"),
        fake(ex.UNDERSTAND_ACTIVITY, "awaiting_confirmation"),
        fake(au.PLAN_MISSIONS_ACTIVITY, 1),
        fake(au.FINISH_EXPLORING_ACTIVITY),
        blank_retry,
        fake(au.PLAN_TESTS_ACTIVITY, 2),
        fake(ex.FINISH_TESTING_ACTIVITY),
        fake(au.DONE_ACTIVITY),
        fake(au.PROMOTE_ACTIVITY, ["journey-1"]),
        fake(ex.REEL_ACTIVITY, True),
        fake(ex.HUNT_ACTIVITY, 0),
        fake(ex.BREADTH_ACTIVITY),
        fake(ex.PLAN_MISSIONS_ACTIVITY, 9),
        fake(ex.PLAN_TESTS_ACTIVITY, 9),
        fake(ex.PROMOTE_ACTIVITY, {}),
    ]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue="test-authoring",
                workflows=[AuthoringRunWorkflow],
                activities=[*steps, queued, run_mission, planned, build, refill],
            ),
            Worker(
                env.client,
                task_queue=GENERATION_TASK_QUEUE,
                workflows=[FakeSuiteGeneration],
                activities=[record_generated],
                # the fake lives in this test module, which the sandbox can't import
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
        ):
            handle = await env.client.start_workflow(
                AuthoringRunWorkflow.run,
                "run-1",
                id=f"wf-{uuid.uuid4()}",
                task_queue="test-authoring",
            )
            if asks:  # waits for your answers and confirm before walking
                while au.START_ACTIVITY not in calls:
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.2)
                assert au.PLAN_MISSIONS_ACTIVITY not in calls
                await handle.signal("brief_confirmed")
            assert await handle.result() == "tested"

    assert calls[:3] == [au.READ_REQUEST_ACTIVITY, au.START_ACTIVITY, au.PLAN_MISSIONS_ACTIVITY]
    # a blank app gets the request walked once more
    assert calls.count("mission:m1") == (2 if blank else 1)
    assert "mission:m1" in calls and {"build:t1", "build:t2"} <= set(calls)
    # Explorer exploring by itself, and Explorer's own planners/hand-off, never run.
    for own in (
        ex.UNDERSTAND_ACTIVITY,  # no first look around the app
        ex.HUNT_ACTIVITY,
        ex.BREADTH_ACTIVITY,
        ex.PLAN_MISSIONS_ACTIVITY,
        ex.PLAN_TESTS_ACTIVITY,
        ex.PROMOTE_ACTIVITY,
    ):
        assert own not in calls
    assert generated == ["journey-1"]
    # a scenario that couldn't be carried out is replaced and tried before adding
    assert calls.index("build:t3") < calls.index(au.PROMOTE_ACTIVITY)
    assert calls.count("refill:1") == 1 and calls.count("refill:0") == 1
    # no test run is started: the test cases are run when the user chooses
    # test cases are written before the run is marked done
    assert calls.index(au.PROMOTE_ACTIVITY) < calls.index(ex.FINISH_TESTING_ACTIVITY)


def test_the_main_scenario_is_the_request_word_for_word() -> None:
    prompt = 'Go to My Team, check Brad Smith is in the team list and his email is "b@x.com".'
    [only] = plan.request_scenarios(prompt, {"title": "Check Brad Smith", "scenarios": []}, "Home")
    assert only["kind"] == "journey" and only["start_screen"] == "Home"
    assert "Start from" not in only["how_to_run"]
    assert only["title"] == "Check Brad Smith"
    assert prompt in only["how_to_run"] and prompt in only["expected"]

    listed = ["Search POL-1 finds it", "Unknown number shows an error"]
    rows = plan.request_scenarios(prompt, {"title": "x", "scenarios": listed}, "Home")
    assert [r["title"] for r in rows] == listed  # exactly those, in order, nothing else
    assert all(text in r["how_to_run"] for text, r in zip(listed, rows, strict=True))


def test_the_proof_is_steered_to_the_named_value_alone() -> None:
    hint = plan.proof_hint('Check "Brad Smith" has email “brad.smith@mail.com”.')
    assert "'Brad Smith'" in hint and "'brad.smith@mail.com'" in hint
    assert "never joined with a label" in hint
    assert "e.g." not in plan.proof_hint("Open My Team")


def test_a_flow_starts_where_the_walk_ended_and_says_so() -> None:
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    now = datetime.now(UTC)
    home = [{"do": "goto", "url": "https://a/#/Dashboard"}]
    screens = [
        SimpleNamespace(name="Sales dashboard", route=home, created_at=now),
        SimpleNamespace(
            name="My Team",
            route=[*home, {"do": "click", "label": "My Team"}],
            created_at=now + timedelta(seconds=30),
        ),
        SimpleNamespace(name="Popup", route=None, created_at=now + timedelta(seconds=60)),
    ]
    assert plan.walk_end(screens) == "My Team"  # type: ignore[arg-type]
    assert plan.walk_end(screens[:1]) is None  # type: ignore[arg-type]
    [row] = plan.request_scenarios("Go to My Team", {"scenarios": []}, "My Team", "Sales dashboard")
    assert row["start_screen"] == "My Team"
    assert row["how_to_run"].startswith("Start from My Team")


def test_how_many_scenarios_follows_what_the_user_asked() -> None:
    # Nothing said: the request plus every scenario the requirement calls for.
    assert plan.more_wanted({"scenarios": [], "count": None}) == plan.CEILING
    # "Write 10 test cases, including these 2": the 2 plus 8 more.
    assert plan.more_wanted({"scenarios": ["a", "b"], "count": 10}) == 8
    # "Write a test case": just the request itself.
    assert plan.more_wanted({"scenarios": [], "count": 1}) == 0
    # "Write 3 test cases": the request plus 2 more.
    assert plan.more_wanted({"scenarios": [], "count": 3}) == 2
    # Scenarios written out: exactly those, nothing more.
    assert plan.more_wanted({"scenarios": ["a", "b"], "count": None}) == 0


@pytest.mark.parametrize(
    ("said", "count"),
    [
        ("5", 5),
        (5, 5),
        ("five", 5),
        ("Twenty-one", 21),
        ("a dozen", 12),
        ("a", 1),
        ("many", None),
        (0, None),
        ("99", None),
        (None, None),
    ],
)
def test_the_number_asked_for_is_read_in_digits_or_words(said: object, count: int | None) -> None:
    assert request._count(said) == count


def test_a_request_for_tests_becomes_its_understood_steps_not_the_sentence() -> None:
    prompt = "write test cases for the lead creation in leeds page"
    reading = {
        "title": "Create a lead",
        "steps": ["Open Leads", "Press New Lead", "Fill in the lead's details", "Press Save Lead"],
        "checks": ["The new lead appears in the Leads list"],
        "scenarios": [],
    }
    [main] = plan.request_scenarios(prompt, reading, "Home")
    assert main["steps"] == reading["steps"]
    assert main["how_to_run"].index("1. Open Leads") < main["how_to_run"].index("4. Press Save")
    assert "The new lead appears in the Leads list" in main["expected"]
    assert prompt not in main["steps"]
    mission = plan.request_mission(prompt, reading)
    assert "2. Press New Lead" in mission["instructions"]
    assert prompt in mission["instructions"]  # the user's words stay as context


def test_more_listed_than_asked_keeps_the_first_ones() -> None:
    rows = plan.request_scenarios("x", {"scenarios": ["a", "b", "c"], "count": 2}, "Home")
    assert [r["title"] for r in rows] == ["a", "b"]


async def test_the_number_asked_is_planned_from_what_the_page_has() -> None:
    facts = [{"name": "Account list", "elements": '- button "Export"\n- textbox "Search"'}]
    real = {
        "kind": "data_load",
        "start_screen": "Account list",
        "path": [{"screen": "Account list", "element": 'button "Export"'}],
    }
    replies = [
        # 2 real, 1 using what the page lacks (rewritten, still lacking), 1 a repeat
        [
            {**real, "title": "a"},
            {**real, "title": "b"},
            {
                **real,
                "title": "x",
                "path": [{"screen": "Account list", "element": 'button "Delete"'}],
            },
            {**real, "title": "a"},
        ],
        [
            {
                **real,
                "title": "x",
                "path": [{"screen": "Account list", "element": 'button "Delete"'}],
            }
        ],  # the one rewrite
        [{**real, "title": f"c{i}"} for i in range(5)],  # the second round tops it up
    ]
    asked: list[str] = []

    async def write(instruction: str, only: list[str]) -> list[dict[str, Any]]:
        asked.append(instruction)
        assert only == ["Account list"]
        return replies.pop(0)

    journal = type("J", (), {"run_id": uuid.uuid4(), "event": lambda self, *a: None})()
    found, cant = await plan.requested_scenarios(
        journal,
        write,
        facts,
        5,
        {"only": "list tests"},
        exact=True,  # type: ignore[arg-type]
    )
    assert [t["title"] for t in found] == ["a", "b", "c0", "c1", "c2"]
    assert [t["title"] for t in cant] == ["x"]  # kept aside with why, never tried
    assert "exactly 5" in asked[0] and "list tests" in asked[0]
    assert "exactly 3" in asked[2] and '"x"' in asked[2]  # no repeats


def test_a_flow_alone_gets_the_full_scope_and_anything_specified_is_followed() -> None:
    assert plan.wants_full_scope({"scenarios": [], "count": None, "only": None})
    assert not plan.wants_full_scope({"scenarios": ["Save with no email"], "count": None})
    assert not plan.wants_full_scope({"scenarios": [], "count": 5})
    assert not plan.wants_full_scope({"scenarios": [], "count": None, "only": "positive only"})


async def test_full_scope_writes_every_field_rule_plus_the_checklist(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def checklist(*_a, only, **_k):  # type: ignore[no-untyped-def]
        return [{"kind": "data_load", "title": f"Search match on {only[0]}", "expected": "x"}]

    async def no_review(*_a, **_k):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(plan.brain, "plan_tests", checklist)
    monkeypatch.setattr(plan.brain, "review_plan", no_review)
    form = {
        "name": "New Contact",
        "kind": "form",
        "fields": [
            {"label": "First Name", "required": True},
            {"label": "Last Name", "required": True},
            {"label": "Email", "type": "email"},
        ],
    }
    tests, _ = await plan._scope_scenarios({}, [form], [], [], None, may_save=True, approved=[])
    titles = [t["title"] for t in tests]
    assert "Empty New Contact can't be saved" in titles
    assert "First Name is required on New Contact" in titles
    assert any(t.startswith("Email refuses") for t in titles)
    assert "Search match on New Contact" in titles


async def test_a_missing_scope_item_is_written_then_the_report_says_what_was_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scope(*_a: Any, **_k: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        email = {"kind": "validation", "title": "Email refuses a wrong format", "expected": "x"}
        return [email], []

    checks = [
        [
            {"screen": "New Contact", "id": "F-06", "status": "covered", "tests": ["Email…"]},
            {"screen": "New Contact", "id": "F-17", "status": "missing", "why": "has Cancel"},
            {"screen": "New Contact", "id": "F-11", "status": "not_applicable", "why": "none"},
        ],
        [
            {"screen": "New Contact", "id": "F-06", "status": "covered", "tests": ["Email…"]},
            {"screen": "New Contact", "id": "F-17", "status": "covered", "tests": ["Cancel"]},
            {"screen": "New Contact", "id": "F-11", "status": "not_applicable", "why": "none"},
        ],
    ]

    async def check(*_a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        # The second check also spots a duplicate written in the gap round.
        return checks.pop(0), ({} if checks else {"Cancel twice": "duplicate of Cancel"})

    async def no_map(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"aim": "", "items": [], "not_applicable": []}

    async def gaps(*a: Any, **k: Any) -> list[dict[str, Any]]:
        assert "F-17" in a[5] and k["only"] == ["New Contact"]  # the gap, on its screen
        return [
            {"kind": "navigation", "title": "Cancel saves nothing", "expected": "x"},
            {"kind": "navigation", "title": "Cancel twice", "expected": "x"},
        ]

    events: list[tuple[str, str]] = []
    journal = type(
        "J",
        (),
        {"run_id": uuid.uuid4(), "event": lambda self, k, t, d=None: events.append((t, d or ""))},
    )()
    monkeypatch.setattr(plan, "_scope_scenarios", scope)
    monkeypatch.setattr(plan.brain, "coverage_map", no_map)
    monkeypatch.setattr(plan.scope, "check_scope", check)
    monkeypatch.setattr(plan.brain, "plan_tests", gaps)
    tests = await plan.cover_scope(
        journal,  # type: ignore[arg-type]
        "",
        {},
        [],
        [],
        [],
        None,
        may_save=True,
        approved=[],
    )
    assert [t["title"] for t in tests] == [
        "Email refuses a wrong format",
        "Cancel saves nothing",
        "Cancel twice",  # left out, kept with why: never silently gone
    ]
    assert tests[2]["left_out"] == "Left out before trying: duplicate of Cancel"
    assert events[1][0].startswith("Scope not met yet: 1 item(s) missing")
    assert events[2] == (
        "Left out 1 scenario(s) before trying them",
        "Cancel twice: duplicate of Cancel",
    )
    headline, detail = events[-1]
    assert headline == "Scope check: 2 of 2 items covered (1 not on these pages)"
    assert "F-11 Dependent field — left out: none" in detail


def test_the_home_screen_is_in_scope_only_when_the_request_names_it() -> None:
    brief = {"request": {"flow": "Create a territory from the Territories page"}}
    prompt = "write test cases for the new territory flow in Territories Page."
    assert not plan.names_screen("Sales dashboard", prompt, brief)
    assert plan.names_screen("Territories", prompt, brief)
    assert plan.names_screen("Sales dashboard", "check the sales dashboard figures", {})


async def test_a_scenario_naming_something_the_app_lacks_is_asked_then_stops_unanswered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ask_json(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"unclear": [{"index": 2, "question": "There is no Discount field. Which?"}]}

    answers = ["Price"]

    async def wait_for_answer(*_a: Any) -> str | None:
        return answers.pop(0) if answers else None

    stopped: list[object] = []
    monkeypatch.setattr(plan, "ask_json", ask_json)
    monkeypatch.setattr(plan, "wait_for_answer", wait_for_answer)
    monkeypatch.setattr(plan, "stop_unclear", stopped.append)
    journal = type("J", (), {"run_id": "r"})()
    request = {"scenarios": ["Save an order", "Discount refuses -1"]}
    clarified = await plan.clarify_scenarios(journal, request, [])  # type: ignore[arg-type]
    assert clarified is not None
    assert clarified["scenarios"] == ["Save an order", "Discount refuses -1 (You answered: Price)"]
    # No answer: no guessed tests, the run stops saying why.
    assert await plan.clarify_scenarios(journal, request, []) is None  # type: ignore[arg-type]
    assert stopped == ["r"]


def test_a_flows_scope_is_its_own_screens_not_the_route_to_it() -> None:
    from datetime import datetime

    from explorer_core import ExplorerScreen

    def screen(name: str, minute: int) -> ExplorerScreen:
        return ExplorerScreen(
            run_id=uuid.uuid4(), name=name, created_at=datetime(2026, 11, 17, 13, minute)
        )

    dashboard, accounts, form, saved = (
        screen("Sales dashboard", 1),
        screen("Account list", 2),
        screen("New account form", 3),
        screen("Account details", 4),
    )
    screens = [dashboard, accounts, form, saved]
    prompt = "create test cases for the new account flow in accounts page"
    assert plan.flow_screens(screens, "New account form", "Sales dashboard", prompt, {}) == [
        form,
        saved,
    ]
    # "Test the accounts page": the walk ends on the list, so the list is the scope.
    assert plan.flow_screens(screens, "Account list", "Sales dashboard", prompt, {})[0] is accounts
    # No walk end: everything but the home screen the request doesn't name.
    assert dashboard not in plan.flow_screens(screens, None, "Sales dashboard", prompt, {})


async def test_not_a_bug_on_an_authoring_run_adds_only_that_scenario() -> None:
    """Possible bugs wait for an answer; "Not a bug" hands off that one
    scenario (its test case is written next), nothing else is re-sent."""
    sent: list[tuple[str, str]] = []

    @activity.defn(name=au.PROMOTE_ACTIVITY)
    async def fake_promote(run_id: str, test_id: str = "") -> list[str]:
        sent.append((run_id, test_id))
        return []  # no journey: no test-case writing to start in this test

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-authoring-send",
            workflows=[AuthoringRunWorkflow],
            activities=[fake_promote],
        ):
            result = await env.client.execute_workflow(
                AuthoringRunWorkflow.run,
                args=["run-1", "send", "test-7"],
                id=f"wf-{uuid.uuid4()}",
                task_queue="test-authoring-send",
            )
    assert result == "sent" and sent == [("run-1", "test-7")]


FORM_FACTS = [
    {"name": "Dashboard", "elements": '- heading "Sales"'},
    {
        "name": "New Territory",
        "kind": "form",
        "elements": '- combobox "Status"\n- button "Save Territory"\n- link "Terms"',
        "app_wide": ['link "terms"'],
    },
]


async def test_what_to_test_is_decided_first_from_the_evidence_then_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def decide(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "aim": "Create a territory",
            "items": [
                {
                    "screen": "New Territory",
                    "id": "F-03",
                    "what": "Status options",
                    "evidence": 'combobox "Status"',
                },
                {
                    "screen": "New Territory",
                    "id": "F-13",
                    "what": "Save works",
                    "evidence": 'button "Save Territory"',
                },
                {
                    "screen": "New Territory",
                    "id": "E-02",
                    "what": "Terms opens",
                    "evidence": 'link "Terms"',
                },  # the shared footer
                {
                    "screen": "New Territory",
                    "id": "F-11",
                    "what": "Region updates Country",
                    "evidence": 'combobox "Region"',
                },  # not on the page
                {
                    "screen": "New Territory",
                    "id": "F-05",
                    "what": "Name is required",
                    "evidence": 'combobox "Status"',
                },  # written per field
            ],
            "not_applicable": [{"screen": "New Territory", "id": "F-17", "why": "no Cancel"}],
        }

    written: list[tuple[list[str], str]] = []

    async def write(*a: Any, only: list[str], **_k: Any) -> list[dict[str, Any]]:
        written.append((only, a[5]))
        return []

    async def no_review(*_a: Any, **_k: Any) -> list[Any]:
        return []

    events: list[tuple[str, str]] = []
    journal = type(
        "J",
        (),
        {"run_id": uuid.uuid4(), "event": lambda self, k, t, d=None: events.append((t, d or ""))},
    )()
    monkeypatch.setattr(plan.brain, "coverage_map", decide)
    monkeypatch.setattr(plan.brain, "plan_tests", write)
    monkeypatch.setattr(plan.brain, "review_plan", no_review)
    items = await plan.coverage_map(journal, "the request", {}, FORM_FACTS, [], [], may_save=True)  # type: ignore[arg-type]
    assert [i["id"] for i in items] == ["F-03", "F-13"]  # only what the page proves
    assert events[0][0] == "Coverage map: 2 check(s) to test on 1 screen(s)"
    assert "F-17 doesn't apply — no Cancel" in events[0][1]
    assert "F-11 doesn't apply — “combobox \"Region\"” isn't on that screen" in events[0][1]
    await plan._scope_scenarios(
        {}, FORM_FACTS, [], [], "notes", may_save=True, approved=[], coverage=items
    )
    [(only, notes)] = written  # the Dashboard has nothing to test: no call for it
    assert only == ["New Territory"] and "Write exactly one test for each item" in notes
    assert '"F-13"' in notes and '"F-11"' not in notes
