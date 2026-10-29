"""ScenarioGenerationActivity end-to-end (Story 4.1) — Postgres only, a fake
`AIProvider` injected via monkeypatch (no real LLM/API key needed; that would
only exercise `HostedAIProvider` itself).
"""

import asyncio
import uuid

import generation_worker.activities as activities_module
import pytest
from ai_provider.scenario_candidate import ScenarioCandidate, TestDataFieldCandidate
from domain import Application, DiscoveryRun, Journey, JourneyStep, Organization, Page, Scenario
from generation_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import ScenarioGenerationActivityInput


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


class _FakeAIProvider:
    def __init__(self, candidates: list[ScenarioCandidate]) -> None:
        self._candidates = candidates

    async def generate_scenarios(
        self,
        journey: Journey,
        pages: list[Page],
        limit: int | None = None,
        requested_counts: dict[str, int] | None = None,
    ) -> list[ScenarioCandidate]:
        return self._candidates if limit is None else self._candidates[:limit]


def _seed_journey() -> Journey:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Scenario Gen Test App",
            url="https://app.example.com",
            environment="test",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()

        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()

        page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/checkout",
            title="Checkout",
        )
        session.add(page)
        session.flush()

        journey = Journey(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add(
            JourneyStep(
                journey_id=journey.id, page_id=page.id, step_order=1, stage_label="Checkout"
            )
        )
        session.commit()
        session.refresh(journey)
        return journey


def test_scenario_generation_activity_creates_scenarios_with_blank_test_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Guest checkout",
            type="happy",
            steps=["Add item to cart", "Submit payment"],
            expected_result="Order confirmation is shown",
            test_data=[
                TestDataFieldCandidate(name="shipping_address", mandatory=True),
                TestDataFieldCandidate(name="promo_code", mandatory=False),
            ],
        ),
        ScenarioCandidate(
            name="Checkout with expired card",
            type="negative",
            steps=["Add item to cart", "Submit expired card"],
            expected_result="A card-declined error is shown",
            test_data=[TestDataFieldCandidate(name="card_number", mandatory=True)],
        ),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    scenario_external_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert len(scenario_external_ids) == 2

    with Session(engine) as session:
        scenarios = session.exec(
            select(Scenario).where(
                Scenario.external_id.in_([uuid.UUID(i) for i in scenario_external_ids])  # type: ignore[attr-defined]
            )
        ).all()
        assert len(scenarios) == 2
        assert all(s.journey_id == journey.id for s in scenarios)
        assert all(s.generation_run_id == journey.attempt for s in scenarios)
        assert all(s.current is True for s in scenarios)

        happy = next(s for s in scenarios if s.type == "happy")
        assert happy.name == "Guest checkout"
        assert happy.steps == ["Add item to cart", "Submit payment"]
        assert happy.expected_result == "Order confirmation is shown"
        assert happy.test_data == [
            {"name": "shipping_address", "mandatory": True, "value": None},
            {"name": "promo_code", "mandatory": False, "value": None},
        ]
        assert happy.test_data_complete() is False

        negative = next(s for s in scenarios if s.type == "negative")
        assert negative.name == "Checkout with expired card"


def test_scenario_generation_activity_applies_provided_test_data_to_happy_path_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` regression: a user's own literal value stated in their NL
    prompt (e.g. "fill Server type with GIT") was extracted correctly by
    AnalyzePromptActivity into `provided_test_data` but never actually
    reached Scenario.test_data — every field, happy-path included, silently
    fell back to a generic "Test value" placeholder, which then broke the
    generated test outright (it tried to select a "Test value" option from a
    dropdown that only ever offers GIT/SVN/etc). Applies only to the
    happy-path Scenario — a negative/edge Scenario's whole point is a
    deliberately different or missing value, so it keeps its own normal
    intent-based default fill instead."""
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Add a GIT MCP connection",
            type="happy",
            steps=["Open server type dropdown", "Select server type", "Submit"],
            expected_result="Connection is created",
            test_data=[
                TestDataFieldCandidate(name="Server type", mandatory=True),
                TestDataFieldCandidate(name="Endpoint URL", mandatory=True),
                TestDataFieldCandidate(name="Personal Access Token (PAT)", mandatory=False),
            ],
        ),
        ScenarioCandidate(
            name="Add a connection with an empty server type",
            type="negative",
            steps=["Open server type dropdown", "Leave it empty", "Submit"],
            expected_result="A required-field error is shown",
            test_data=[TestDataFieldCandidate(name="Server type", mandatory=True)],
        ),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    scenario_external_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(
                journey_id=str(journey.external_id),
                source="nl",
                provided_test_data={
                    "server_type": "GIT",
                    "endpoint_url": "https://github.com/wm-ps/jsp-servlet-ecommerce-website",
                    "personal_access_token": "fake-test-personal-access-token-value",
                },
            )
        )
    )

    with Session(engine) as session:
        scenarios = session.exec(
            select(Scenario).where(
                Scenario.external_id.in_([uuid.UUID(i) for i in scenario_external_ids])  # type: ignore[attr-defined]
            )
        ).all()

        happy = next(s for s in scenarios if s.type == "happy")
        by_name = {f["name"]: f["value"] for f in happy.test_data}
        assert by_name["Server type"] == "GIT"
        assert by_name["Endpoint URL"] == "https://github.com/wm-ps/jsp-servlet-ecommerce-website"
        assert by_name["Personal Access Token (PAT)"] == "fake-test-personal-access-token-value"

        negative = next(s for s in scenarios if s.type == "negative")
        assert negative.test_data == [{"name": "Server type", "mandatory": True, "value": None}]


def test_scenario_generation_activity_strips_existing_credential_test_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential-handling fix: even if the AI invents a test_data field for
    the account's own existing username/password, it must never be persisted
    — that value only ever comes from the user-provided credential source at
    Playwright-generation/runtime, never from generated test_data. A
    "new"/"confirm" password field (a change-password form's actual subject
    under test) is unrelated and must survive untouched."""
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Sign in with valid password",
            type="happy",
            steps=["Enter username", "Enter password", "Submit"],
            expected_result="Signed in",
            test_data=[
                TestDataFieldCandidate(name="username", mandatory=True),
                TestDataFieldCandidate(name="password", mandatory=True),
            ],
        ),
        ScenarioCandidate(
            name="Change password successfully",
            type="happy",
            steps=["Enter current password", "Enter new password", "Confirm new password"],
            expected_result="Password changed",
            test_data=[
                TestDataFieldCandidate(name="current password", mandatory=True),
                TestDataFieldCandidate(name="new password", mandatory=True),
                TestDataFieldCandidate(name="confirm new password", mandatory=True),
            ],
        ),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    with Session(engine) as session:
        scenarios_by_name = {
            s.name: s
            for s in session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).all()
        }

    assert scenarios_by_name["Sign in with valid password"].test_data == []
    change_password_fields = {
        f["name"] for f in scenarios_by_name["Change password successfully"].test_data
    }
    assert change_password_fields == {"new password", "confirm new password"}


def test_scenario_generation_activity_marks_login_email_but_not_signup_or_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A login Scenario's own Email is kept but marked `login` (hidden from
    the user and the AI); a signup Email and a negative-login Email are the
    values under test and stay plain, editable fields."""
    init_db()
    journey = _seed_journey()

    def _email_case(name: str) -> ScenarioCandidate:
        return ScenarioCandidate(
            name=name,
            type="happy",
            steps=[name, "Submit"],
            expected_result="Done",
            test_data=[TestDataFieldCandidate(name="Email", mandatory=True)],
        )

    candidates = [
        _email_case("Login with valid credentials"),
        _email_case("Sign up with a new account"),
        _email_case("Login with an unregistered email"),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    with Session(engine) as session:
        by_name = {
            s.name: s.test_data
            for s in session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).all()
        }

    assert [f.get("login") for f in by_name["Login with valid credentials"]] == [True]
    assert [f.get("login") for f in by_name["Sign up with a new account"]] == [None]
    assert [f.get("login") for f in by_name["Login with an unregistered email"]] == [None]


def test_scenario_generation_activity_is_idempotent_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Guest checkout",
            type="happy",
            steps=["Add item to cart"],
            expected_result="Order confirmation is shown",
            test_data=[TestDataFieldCandidate(name="username", mandatory=True)],
        )
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    first_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )
    second_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    assert first_ids == second_ids
    with Session(engine) as session:
        count = len(
            session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).all()
        )
        assert count == 1


class _RaisingAIProvider:
    """`[ADDED]` Simulates `ScenarioGenerationActivity`'s own AI-provider
    call failing — the case `GenerationWorkflow` has no per-scenario fault
    isolation for (unlike `SuiteGenerationWorkflow`), which used to leave a
    Journey stuck at 0 Scenarios forever with no record of why."""

    async def generate_scenarios(self, *args: object, **kwargs: object) -> list:
        raise RuntimeError("AI provider timed out")


def test_scenario_generation_activity_records_its_failure_on_the_journey_then_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[FIXED]` This used to swallow the exception and return `[]` on the
    very first attempt, which meant Temporal's own `RetryPolicy` never got
    a chance to actually retry a transient failure. It must still re-raise
    (so real retries keep happening) — `GenerationWorkflow` is the layer
    that stops retrying and completes cleanly, only once every attempt is
    genuinely exhausted (see that Workflow's own test)."""
    init_db()
    journey = _seed_journey()
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: _RaisingAIProvider())

    with pytest.raises(RuntimeError, match="AI provider timed out"):
        asyncio.run(
            activities_module.scenario_generation_activity(
                ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
            )
        )

    with Session(engine) as session:
        refreshed = session.exec(select(Journey).where(Journey.id == journey.id)).one()
        assert refreshed.generation_error is not None
        assert "AI provider timed out" in refreshed.generation_error
        assert (
            session.exec(select(Scenario).where(Scenario.journey_id == journey.id)).all() == []
        )


def test_scenario_generation_activity_clears_a_stale_error_on_a_successful_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Journey that failed once and is retried (a fresh Activity call —
    Story 4.3/regeneration isn't built yet, but the field must not lie once
    it is) must not keep showing the old error once generation succeeds."""
    init_db()
    journey = _seed_journey()
    journey_external_id = str(journey.external_id)
    with Session(engine) as session:
        journey.generation_error = "RuntimeError: previous failure"
        session.add(journey)
        session.commit()

    candidates = [
        ScenarioCandidate(
            name="Guest checkout",
            type="happy",
            steps=["Add item to cart"],
            expected_result="Order confirmation is shown",
            test_data=[TestDataFieldCandidate(name="username", mandatory=True)],
        )
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    scenario_external_ids = asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=journey_external_id)
        )
    )

    assert len(scenario_external_ids) == 1
    with Session(engine) as session:
        refreshed = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(journey_external_id))
        ).one()
        assert refreshed.generation_error is None


def test_scenario_generation_activity_persists_safety_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run All Tests feature: each persisted Scenario is classified from its
    own steps at generation time, most-severe-step-wins, using the same
    `safety_classifier.classify()` discovery's live-crawl safety_engine
    calls — see `activities_module._classify_scenario_steps`."""
    init_db()
    journey = _seed_journey()

    candidates = [
        ScenarioCandidate(
            name="Safe browsing",
            type="happy",
            steps=["View item details", "Open the cart"],
            expected_result="Cart is shown",
            test_data=[],
        ),
        ScenarioCandidate(
            name="Deletes an order",
            type="negative",
            steps=["View item details", "Delete the order"],
            expected_result="Order is removed",
            test_data=[],
        ),
        ScenarioCandidate(
            name="Ambiguous save",
            type="happy",
            steps=["View item details", "Save changes"],
            expected_result="Changes are saved",
            test_data=[],
        ),
        ScenarioCandidate(
            name="No steps at all",
            type="edge",
            steps=[],
            expected_result="N/A",
            test_data=[],
        ),
    ]
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates)
    )

    asyncio.run(
        activities_module.scenario_generation_activity(
            ScenarioGenerationActivityInput(journey_id=str(journey.external_id))
        )
    )

    with Session(engine) as session:
        scenarios_by_name = {
            s.name: s
            for s in session.exec(
                select(Scenario).where(Scenario.journey_id == journey.id)
            ).all()
        }

    assert scenarios_by_name["Safe browsing"].safety_classification == "SAFE"
    assert scenarios_by_name["Deletes an order"].safety_classification == "DESTRUCTIVE"
    assert scenarios_by_name["Ambiguous save"].safety_classification == "UNKNOWN"
    assert scenarios_by_name["No steps at all"].safety_classification == "UNKNOWN"
    assert scenarios_by_name["No steps at all"].safety_classification_reason == (
        "scenario has no steps to classify"
    )
