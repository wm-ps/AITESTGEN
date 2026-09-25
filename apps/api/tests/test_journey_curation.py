"""Discover Journeys read endpoints (Story 3.1) and Rename/Delete (Story 3.4).

Requires PostgreSQL + Vault + Temporal reachable, same skip-cleanly convention
as `test_onboarding.py`. Journeys/JourneySteps are seeded directly against the
DB rather than via a real Discovery Run — InferenceActivity's LLM-backed
inference is out of scope for testing this read/curation slice.
"""

import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import DiscoveryRun, Journey, JourneyStep, Page
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except (VaultError, OSError):
        return False


def _temporal_available() -> bool:
    import asyncio

    from api.temporal_client import get_temporal_client

    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and _temporal_available()),
    reason="requires PostgreSQL + Vault + Temporal reachable — start docker compose",
)


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _create_application(client: TestClient, name: str) -> dict:
    response = client.post(
        "/applications",
        json={
            "name": name,
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_candidate_journey(application: dict, name: str = "Login") -> str:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/login",
            title="Login",
        )
        session.add(page)
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name=name,
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id, page_id=page.id, step_order=1, stage_label="Login"
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=page.id,
                    step_order=2,
                    stage_label="MFA Verification",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        return str(journey.external_id)


def test_list_journeys_returns_name_and_step_count() -> None:
    init_db()
    client = _signed_in_client("Org Journey List")
    application = _create_application(client, "Journey List App")
    _add_candidate_journey(application, name="Checkout")

    response = client.get(f"/applications/{application['id']}/journeys")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Checkout"
    assert body[0]["step_count"] == 2
    assert "confidence" not in body[0]
    assert "risk" not in body[0]
    assert body[0]["generation_error"] is None


def test_list_journeys_surfaces_a_generation_error() -> None:
    """`[FIXED]` regression: ScenarioGenerationActivity catches its own
    failure and records it on the Journey (see Journey.generation_error's
    docstring) instead of leaving the Journey stuck at 0 Scenarios with no
    explanation — this is the read side the Review Scenarios screen polls
    to know a Journey's generation concluded (even if it failed) and to
    show the user why."""
    init_db()
    client = _signed_in_client("Org Journey Generation Error")
    application = _create_application(client, "Journey Generation Error App")
    journey_id = _add_candidate_journey(application, name="Checkout")
    with Session(engine) as session:
        journey = session.exec(
            select(Journey).where(Journey.external_id == uuid.UUID(journey_id))
        ).one()
        journey.generation_error = "RuntimeError: AI provider timed out"
        session.add(journey)
        session.commit()

    response = client.get(f"/applications/{application['id']}/journeys")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["generation_error"] == "RuntimeError: AI provider timed out"


def test_list_journeys_excludes_deleted() -> None:
    init_db()
    client = _signed_in_client("Org Journey Excludes Deleted")
    application = _create_application(client, "Excludes Deleted App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    response = client.get(f"/applications/{application['id']}/journeys")
    assert response.json() == []


def test_list_journeys_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Journey List A")
    client_b = _signed_in_client("Org Journey List B")
    application = _create_application(client_a, "Org A Journey App")
    _add_candidate_journey(application)

    response = client_b.get(f"/applications/{application['id']}/journeys")
    assert response.status_code == 404


def test_journey_steps_returns_ordered_route_method_stage_label() -> None:
    init_db()
    client = _signed_in_client("Org Journey Steps")
    application = _create_application(client, "Journey Steps App")
    journey_id = _add_candidate_journey(application)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert [s["stage_label"] for s in body] == ["Login", "MFA Verification"]
    assert body[0]["route"] == "https://staging.example.com/login"
    assert body[0]["method"] == "GET"


def test_journey_steps_returns_screenshot_url_on_final_step_only(monkeypatch) -> None:
    """Only the last step (highest step_order) gets a screenshot — and only
    when its Page actually captured one (`object_storage_key` set)."""
    import api.main as main_module

    class _FakeObjectStore:
        def presigned_get_url(
            self,
            key: str,
            expires_seconds: int = 900,
            *,
            response_content_type: str | None = None,
            filename: str | None = None,
        ) -> str:
            return f"https://fake-store/{key}"

    monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)

    init_db()
    client = _signed_in_client("Org Journey Screenshot")
    application = _create_application(client, "Journey Screenshot App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        login_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/login",
            title="Login",
        )
        checkout_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/checkout",
            title="Checkout",
            object_storage_key="discovery-runs/some-run/some-key",
        )
        session.add_all([login_page, checkout_page])
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout Flow",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id, page_id=login_page.id, step_order=1, stage_label="Login"
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=checkout_page.id,
                    step_order=2,
                    stage_label="Checkout",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        journey_id = str(journey.external_id)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["screenshot_url"] is None
    assert body[1]["screenshot_url"] == "https://fake-store/discovery-runs/some-run/some-key"


def test_journey_steps_falls_back_to_an_earlier_settled_screenshot(monkeypatch) -> None:
    """`[FIXED journey-screenshot]` regression: the last step's screenshot
    used to be shown unconditionally, blank or not. When its Page never
    settled (`page_settled=False` — Story 2.9's readiness gate, checked
    right before the crawler's screenshot), the endpoint must walk
    backward through the journey's earlier steps for one that did settle,
    instead of showing what's very likely a blank capture."""
    import api.main as main_module

    class _FakeObjectStore:
        def presigned_get_url(
            self,
            key: str,
            expires_seconds: int = 900,
            *,
            response_content_type: str | None = None,
            filename: str | None = None,
        ) -> str:
            return f"https://fake-store/{key}"

    monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)

    init_db()
    client = _signed_in_client("Org Journey Screenshot Fallback")
    application = _create_application(client, "Journey Screenshot Fallback App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        login_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/login",
            title="Login",
            object_storage_key="discovery-runs/some-run/login-key",
            page_settled=True,
        )
        blank_checkout_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/checkout",
            title="Checkout",
            object_storage_key="discovery-runs/some-run/blank-checkout-key",
            page_settled=False,
        )
        session.add_all([login_page, blank_checkout_page])
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout Flow",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id, page_id=login_page.id, step_order=1, stage_label="Login"
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=blank_checkout_page.id,
                    step_order=2,
                    stage_label="Checkout",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        journey_id = str(journey.external_id)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    # Still attached to the LAST step's response object (unchanged API
    # contract/frontend read path) — just sourced from the earlier,
    # actually-settled page's screenshot instead of the blank one.
    assert body[1]["screenshot_url"] == "https://fake-store/discovery-runs/some-run/login-key"


def test_journey_steps_uses_the_only_screenshot_even_if_unsettled(monkeypatch) -> None:
    """No settled page exists anywhere in the journey — still show the
    closest available screenshot rather than nothing at all."""
    import api.main as main_module

    class _FakeObjectStore:
        def presigned_get_url(
            self,
            key: str,
            expires_seconds: int = 900,
            *,
            response_content_type: str | None = None,
            filename: str | None = None,
        ) -> str:
            return f"https://fake-store/{key}"

    monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)

    init_db()
    client = _signed_in_client("Org Journey Screenshot Only Blank")
    application = _create_application(client, "Journey Screenshot Only Blank App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        blank_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/checkout",
            title="Checkout",
            object_storage_key="discovery-runs/some-run/only-blank-key",
            page_settled=False,
        )
        session.add(blank_page)
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout Flow",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add(
            JourneyStep(
                journey_id=journey.id, page_id=blank_page.id, step_order=1, stage_label="Checkout"
            )
        )
        session.commit()
        session.refresh(journey)
        journey_id = str(journey.external_id)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["screenshot_url"] == "https://fake-store/discovery-runs/some-run/only-blank-key"


def test_journey_steps_prefers_the_end_states_own_screenshot(monkeypatch) -> None:
    """`[FIXED screenshot-content-score]` The journey's own end state (its
    last step's Page) is shown whenever its capture is good enough
    (`content_score >= 0.3`), even when an earlier step's page scored
    higher — searching every step for the single highest score let a
    generic-but-real earlier page (most often `Home` in production: a real
    nav DOM and heading, but no dashboard widgets) win over the journey's
    actual destination far too often, showing an unrepresentative
    screenshot."""
    import api.main as main_module

    class _FakeObjectStore:
        def presigned_get_url(
            self,
            key: str,
            expires_seconds: int = 900,
            *,
            response_content_type: str | None = None,
            filename: str | None = None,
        ) -> str:
            return f"https://fake-store/{key}"

    monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)

    init_db()
    client = _signed_in_client("Org Journey Content Score")
    application = _create_application(client, "Journey Content Score App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        # A real, legitimate page (e.g. a Home dashboard) that scores well
        # despite being visually generic.
        home_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/home",
            title="Home",
            object_storage_key="discovery-runs/some-run/home-key",
            page_settled=True,
            content_score=0.85,
        )
        # The journey's actual destination — a lower score than Home, but
        # still well above the "usable" floor, so it must still win.
        end_state_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/confirmation",
            title="Confirmation",
            object_storage_key="discovery-runs/some-run/end-state-key",
            page_settled=True,
            content_score=0.4,
        )
        session.add_all([home_page, end_state_page])
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout Flow",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id,
                    page_id=home_page.id,
                    step_order=1,
                    stage_label="Home",
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=end_state_page.id,
                    step_order=2,
                    stage_label="Confirmation",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        journey_id = str(journey.external_id)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[-1]["screenshot_url"] == "https://fake-store/discovery-runs/some-run/end-state-key"


def test_journey_steps_falls_back_when_the_end_states_own_screenshot_is_too_low(
    monkeypatch,
) -> None:
    """`[ADDED screenshot-content-score]` When the end state's own capture
    scored too low to be worth showing (e.g. captured before its data
    finished loading — content_score < 0.3), fall back to the best-scoring
    earlier step's page rather than showing a near-blank screenshot."""
    import api.main as main_module

    class _FakeObjectStore:
        def presigned_get_url(
            self,
            key: str,
            expires_seconds: int = 900,
            *,
            response_content_type: str | None = None,
            filename: str | None = None,
        ) -> str:
            return f"https://fake-store/{key}"

    monkeypatch.setattr(main_module, "ObjectStore", _FakeObjectStore)

    init_db()
    client = _signed_in_client("Org Journey Content Score Fallback")
    application = _create_application(client, "Journey Content Score Fallback App")

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        best_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/checkout",
            title="Checkout",
            object_storage_key="discovery-runs/some-run/best-key",
            page_settled=True,
            content_score=0.85,
        )
        # Settled but a near-empty capture (e.g. a loading skeleton that
        # happened to settle) — low content_score despite page_settled=True,
        # and it's the journey's own end state.
        blank_end_state_page = Page(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            url="https://staging.example.com/loading",
            title="Loading",
            object_storage_key="discovery-runs/some-run/loading-key",
            page_settled=True,
            content_score=0.05,
        )
        session.add_all([best_page, blank_end_state_page])
        session.flush()

        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Checkout Flow",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()

        session.add_all(
            [
                JourneyStep(
                    journey_id=journey.id,
                    page_id=best_page.id,
                    step_order=1,
                    stage_label="Checkout",
                ),
                JourneyStep(
                    journey_id=journey.id,
                    page_id=blank_end_state_page.id,
                    step_order=2,
                    stage_label="Loading",
                ),
            ]
        )
        session.commit()
        session.refresh(journey)
        journey_id = str(journey.external_id)

    response = client.get(f"/journeys/{journey_id}/steps")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # Still attached to the LAST step's response object (unchanged API
    # contract) — the Journey association is preserved even though the
    # winning screenshot came from an earlier step.
    assert body[-1]["screenshot_url"] == "https://fake-store/discovery-runs/some-run/best-key"


def test_rename_journey_updates_name() -> None:
    init_db()
    client = _signed_in_client("Org Journey Rename")
    application = _create_application(client, "Journey Rename App")
    journey_id = _add_candidate_journey(application, name="Old Name")

    response = client.patch(f"/journeys/{journey_id}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"

    listed = client.get(f"/applications/{application['id']}/journeys").json()
    assert listed[0]["name"] == "New Name"


def test_rename_already_deleted_journey_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Journey Rename Deleted")
    application = _create_application(client, "Journey Rename Deleted App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    response = client.patch(f"/journeys/{journey_id}", json={"name": "New Name"})
    assert response.status_code == 409


def test_delete_already_deleted_journey_is_rejected() -> None:
    init_db()
    client = _signed_in_client("Org Journey Delete Twice")
    application = _create_application(client, "Journey Delete Twice App")
    journey_id = _add_candidate_journey(application)

    assert client.delete(f"/journeys/{journey_id}").status_code == 204
    assert client.delete(f"/journeys/{journey_id}").status_code == 409


def test_journey_curation_is_organization_scoped() -> None:
    init_db()
    client_a = _signed_in_client("Org Journey Curation A")
    client_b = _signed_in_client("Org Journey Curation B")
    application = _create_application(client_a, "Org A Curation App")
    journey_id = _add_candidate_journey(application)

    assert client_b.patch(f"/journeys/{journey_id}", json={"name": "Hijacked"}).status_code == 404
    assert client_b.delete(f"/journeys/{journey_id}").status_code == 404
