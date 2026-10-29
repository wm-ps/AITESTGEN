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
                activities=[*steps, queued, run_mission, planned, build],
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
    # Nothing said: the request plus the other scenarios worth testing on it.
    assert plan.more_wanted({"scenarios": [], "count": None}) == 8
    # "Write a test case": just the request itself.
    assert plan.more_wanted({"scenarios": [], "count": 1}) == 0
    # "Write 3 test cases": the request plus 2 more.
    assert plan.more_wanted({"scenarios": [], "count": 3}) == 2
    # Scenarios written out: exactly those, nothing more.
    assert plan.more_wanted({"scenarios": ["a", "b"], "count": None}) == 0
