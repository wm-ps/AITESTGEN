"""A button the user said "Yes, press it" to while Explorer explored (a risk
question) may be pressed by scenarios too, on a test environment
(tests_stage.approved_labels, pursue.pre_approved). Anything never approved
still stops before the button, as before."""

from explorer_worker.pursue import pre_approved
from explorer_worker.tests_stage import approved_labels


def test_only_buttons_the_user_said_yes_to_are_approved() -> None:
    answers = [
        ("May I press “Send transfer” on Transfer funds?", "Yes, press it"),
        ("May I press “Buy” on Investments?", "Yes, press it"),
        ("May I press “Issue policy” on Insurance?", "No, stop here"),
        ("May I press “Apply” on Loans?", None),  # never answered
        ("Which test policy should I use?", "POL-1"),  # not about pressing
    ]
    assert approved_labels(answers) == {"Send transfer", "Buy"}


def test_a_scenario_presses_only_an_approved_button() -> None:
    approved = {"Send transfer", "Buy"}
    assert pre_approved("Send transfer", approved)
    assert pre_approved("Buy Icon Buy", approved)  # same button, icon text read out
    assert not pre_approved("Issue policy", approved)
    assert not pre_approved("Send transfer", set())  # nothing approved: as before


def test_the_planner_may_plan_approved_money_flows_and_nothing_else_changes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from explorer_worker import brain

    prompts: list[str] = []

    async def ask_json(system: str, user: str, **kw: object) -> dict:  # type: ignore[type-arg]
        prompts.append(user)
        return {"tests": []}

    monkeypatch.setattr(brain, "ask_json", ask_json)
    asyncio.run(brain.plan_tests({}, [], [], [], [], None, may_save=True, approved=["Send transfer"]))
    asyncio.run(brain.plan_tests({}, [], [], [], [], None, may_save=True))
    assert "approved pressing these buttons" in prompts[0] and "Send transfer" in prompts[0]
    assert "approved pressing" not in prompts[1]  # nothing approved: today's prompt
