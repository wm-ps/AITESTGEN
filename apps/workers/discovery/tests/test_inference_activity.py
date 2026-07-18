"""InferenceActivity end-to-end (Story 2.6, Task 6) — Postgres + Temporal, a
fake `AIProvider` injected via monkeypatch (no real LLM/API key needed; that
would only exercise `HostedAIProvider` itself, covered separately and
skip-cleanly in `packages/ai_provider/tests/test_hosted.py`).
"""

import uuid

import discovery_worker.activities as activities_module
import pytest
from ai_provider.journey_candidate import JourneyCandidate
from discovery_worker.db import engine, init_db
from discovery_worker.temporal_client import get_temporal_client
from domain import ApiEndpoint, Application, Capability, DiscoveryRun, Journey, Organization, Page
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import GENERATION_TASK_QUEUE, InferenceActivityInput


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


async def _temporal_available() -> bool:
    try:
        await get_temporal_client()
        return True
    except Exception:
        return False


def _temporal_available_sync() -> bool:
    import asyncio

    return asyncio.run(_temporal_available())


pytestmark = pytest.mark.skipif(
    not (_db_available() and _temporal_available_sync()),
    reason="requires PostgreSQL + Temporal reachable — start docker compose",
)


class _FakeAIProvider:
    def __init__(self, candidates: list[JourneyCandidate]) -> None:
        self._candidates = candidates

    def infer_journeys(self, pages: list[Page]) -> list[JourneyCandidate]:
        return self._candidates


def _seed_completed_run() -> tuple[uuid.UUID, uuid.UUID, list[Page], ApiEndpoint]:
    """Returns (application_id, discovery_run_external_id, pages, checkout_api).

    `pages` is [cart_page, about_page, unrelated_page]. `unrelated_page` is
    deliberately not referenced by any candidate in the tests below — it
    proves an unrelated canonical Page for the same run stays unattributed
    (Task 6).
    """
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        application = Application(
            organization_id=org.id,
            name="Inference Test App",
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

        cart_page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/cart",
            title="Cart",
        )
        about_page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/about",
            title="About",
        )
        unrelated_page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/unrelated",
            title="Unrelated",
        )
        session.add(cart_page)
        session.add(about_page)
        session.add(unrelated_page)
        session.flush()

        checkout_api = ApiEndpoint(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            page_id=cart_page.id,
            method="POST",
            path="/api/checkout",
        )
        session.add(checkout_api)
        session.commit()
        session.refresh(discovery_run)
        session.refresh(cart_page)
        session.refresh(about_page)
        session.refresh(unrelated_page)
        session.refresh(checkout_api)

        return (
            application.id,
            discovery_run.external_id,
            [cart_page, about_page, unrelated_page],
            checkout_api,
        )


@pytest.mark.asyncio
async def test_inference_activity_creates_journeys_attributes_pages_and_starts_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    application_id, discovery_run_external_id, pages, checkout_api = _seed_completed_run()
    cart_page, about_page, unrelated_page = pages

    candidates = [
        JourneyCandidate(
            name="Checkout from cart",
            capability_name="Purchasing",
            page_ids=[str(cart_page.id)],
        ),
        JourneyCandidate(
            name="View about page",
            capability_name="Marketing",
            page_ids=[str(about_page.id)],
        ),
    ]
    monkeypatch.setattr(activities_module, "HostedAIProvider", lambda: _FakeAIProvider(candidates))

    journey_external_ids = await activities_module.inference_activity(
        InferenceActivityInput(discovery_run_id=str(discovery_run_external_id))
    )

    assert len(journey_external_ids) == 2

    journey_uuids = [uuid.UUID(j) for j in journey_external_ids]
    with Session(engine) as session:
        journeys = session.exec(
            select(Journey).where(Journey.external_id.in_(journey_uuids))  # type: ignore[attr-defined]
        ).all()
        assert len(journeys) == 2
        assert all(j.status == "candidate" for j in journeys)
        names = {j.name for j in journeys}
        assert names == {"Checkout from cart", "View about page"}
        assert all(j.discovery_run_id == cart_page.discovery_run_id for j in journeys)

        capabilities = session.exec(
            select(Capability).where(Capability.application_id == application_id)
        ).all()
        assert {c.name for c in capabilities} == {"Purchasing", "Marketing"}

        refreshed_cart = session.get(Page, cart_page.id)
        refreshed_about = session.get(Page, about_page.id)
        refreshed_unrelated = session.get(Page, unrelated_page.id)
        refreshed_checkout_api = session.get(ApiEndpoint, checkout_api.id)
        assert refreshed_cart is not None
        assert refreshed_about is not None
        assert refreshed_unrelated is not None
        checkout_journey = next(j for j in journeys if j.name == "Checkout from cart")
        about_journey = next(j for j in journeys if j.name == "View about page")

        assert refreshed_cart.journey_id == checkout_journey.id
        assert refreshed_about.journey_id == about_journey.id
        # Task 6: unrelated Page for the same run stays unattributed.
        assert refreshed_unrelated.journey_id is None
        # ApiEndpoint on the cart page is attributed through the same Journey.
        assert refreshed_checkout_api is not None
        assert refreshed_checkout_api.journey_id == checkout_journey.id

    client = await get_temporal_client()
    for journey_external_id in journey_external_ids:
        handle = client.get_workflow_handle(f"generation-{journey_external_id}-1")
        description = await handle.describe()
        assert description.task_queue == GENERATION_TASK_QUEUE


@pytest.mark.asyncio
async def test_inference_activity_retry_is_idempotent_on_identity_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    _, discovery_run_external_id, pages, _checkout_api = _seed_completed_run()
    cart_page, _about_page, _unrelated_page = pages

    # Second call uses a *different* AI-generated name for the same page
    # shape — AD-13 says identity_key must depend only on the canonical
    # Application Model, so this must still resolve to the same Journey,
    # not a duplicate.
    first_candidates = [
        JourneyCandidate(
            name="Checkout from cart", capability_name="Purchasing", page_ids=[str(cart_page.id)]
        ),
    ]
    second_candidates = [
        JourneyCandidate(
            name="Complete a purchase",
            capability_name="Purchasing",
            page_ids=[str(cart_page.id)],
        ),
    ]

    input_ = InferenceActivityInput(discovery_run_id=str(discovery_run_external_id))
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(first_candidates)
    )
    first_run = await activities_module.inference_activity(input_)
    monkeypatch.setattr(
        activities_module, "HostedAIProvider", lambda: _FakeAIProvider(second_candidates)
    )
    second_run = await activities_module.inference_activity(input_)

    # Same identity_key both times -> the retry finds and reuses the existing
    # Journey row rather than creating a duplicate (AD-9/AD-13).
    assert first_run == second_run

    with Session(engine) as session:
        run = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.external_id == discovery_run_external_id)
        ).one()
        journeys = session.exec(select(Journey).where(Journey.discovery_run_id == run.id)).all()
        assert len(journeys) == 1
        # The original attribution is preserved — the second call's different
        # name never overwrites it (AD-13).
        assert journeys[0].name == "Checkout from cart"
