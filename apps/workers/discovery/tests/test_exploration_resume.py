"""Story 2.16: Blocked Path Record & Re-Crawl Resume. Real Chromium +
Postgres + Vault + object storage, same skip-cleanly convention as
test_discovery_activity_integration.py / test_state_identity_integration.py.
Scoped to the `/wizard/*` fixture (a linear 3-step wizard) so this doesn't
re-run the whole dashboard crawl.
"""

import json
import os
import uuid

import pytest
from discovery_worker.activities import discovery_activity
from discovery_worker.db import engine, init_db
from discovery_worker.resume import resume_blocked_task
from domain import (
    Application,
    BlockedTask,
    DiscoveryRun,
    ExplorationStep,
    Organization,
    Page,
    TestDataEntry,
)
from fixtures.target_app import _wizard_orders, configure
from object_store.client import ObjectStore
from playwright.async_api import async_playwright
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN, SecretRef, VaultSecretsClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from workflows import DiscoveryActivityInput


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _vault_available() -> bool:
    try:
        import hvac

        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and os.environ.get("AWS_S3_BUCKET")),
    reason="requires PostgreSQL + Vault + AWS_S3_BUCKET configured",
)


def _seed_application_at(start_url: str) -> tuple[str, uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
        secret_ref = VaultSecretsClient().store(org.id, credential)

        application = Application(
            organization_id=org.id,
            name="Exploration Resume Test App",
            url=start_url,
            environment="test",
            auth_method="standard_login",
            secret_ref=secret_ref.path,
        )
        session.add(application)
        session.flush()
        discovery_run = DiscoveryRun(application_id=application.id, status="running")
        session.add(discovery_run)
        session.commit()
        session.refresh(application)
        session.refresh(discovery_run)
        return secret_ref.path, application.external_id, discovery_run.external_id


@pytest.mark.asyncio
async def test_wizard_path_blocks_and_resume_does_not_duplicate_the_earlier_order(
    target_app_url: str,
) -> None:
    init_db()
    configure(expire_after=None)
    secret_ref_path, application_external_id, discovery_run_external_id = _seed_application_at(
        f"{target_app_url}wizard/step-a"
    )

    result = await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )
    assert result.status == "complete"
    assert len(_wizard_orders) == 1, "step-a's own submit must have created exactly one order"

    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == application_external_id)
        ).one()

        blocked_task = session.exec(
            select(BlockedTask).where(BlockedTask.application_id == application.id)
        ).one()
        assert blocked_task.status == "blocked_data"
        assert blocked_task.required_type == "data"

        steps = list(
            session.exec(
                select(ExplorationStep)
                .where(ExplorationStep.blocked_task_id == blocked_task.id)
                .order_by(ExplorationStep.step_order)  # type: ignore[arg-type]
            ).all()
        )
        assert len(steps) >= 2, "must record more than just the blocking step"
        assert [s.step_order for s in steps] == list(range(1, len(steps) + 1))

        step_pages = {session.get(Page, s.page_id).url for s in steps}  # type: ignore[union-attr]
        assert any(url.endswith("/wizard/step-c") for url in step_pages), step_pages
        assert any(url.endswith("/wizard/step-a") for url in step_pages), step_pages

        last_step_page = session.get(Page, steps[-1].page_id)
        assert last_step_page is not None
        assert last_step_page.url.endswith("/wizard/step-c")

        discovery_run_pk = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.external_id == discovery_run_external_id)
        ).one().id
        blocked_task_id = blocked_task.id
        application_pk = application.id

        vault_client = VaultSecretsClient()
        credential = vault_client.resolve(SecretRef(path=secret_ref_path))
        object_store = ObjectStore()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            resume_result = await resume_blocked_task(
                session,
                browser,
                application=application,
                blocked_task=blocked_task,
                supplied_value="POL-999",
                credential=credential,
                object_store=object_store,
                discovery_run_id=discovery_run_pk,
            )
            await browser.close()

    assert len(_wizard_orders) == 1, (
        "resume must never replay step-a's order-creating submit — this is the "
        "specific harm Story 2.16's mechanism replacement exists to prevent"
    )
    # AC 3/6: resumed from the nearest confirmed entry point (step-b, the last
    # canonical page before the block), not the root (step-a).
    assert resume_result.resumed_from_root is False
    assert resume_result.entry_point_url.endswith("/wizard/step-b")

    with Session(engine) as session:
        refreshed = session.get(BlockedTask, blocked_task_id)
        assert refreshed is not None
        assert refreshed.status == "resolved"
        assert refreshed.resolved_at is not None

        pool_entry = session.exec(
            select(TestDataEntry).where(
                TestDataEntry.application_id == application_pk,
                TestDataEntry.normalized_key == refreshed.aggregation_key,
            )
        ).one()
        assert pool_entry.value == "POL-999"


@pytest.mark.asyncio
async def test_a_second_block_on_the_same_key_extends_the_same_blocked_task(
    target_app_url: str,
) -> None:
    """AC 5: re-running discovery against the same Application (a second,
    independent path that hits the same business-specific field) extends
    the existing `BlockedTask`'s `ExplorationStep` trail rather than
    colliding with it or creating a second `BlockedTask` row. Also exercises
    `resume_blocked_task` against a path whose only preceding hop is the
    login page — a real, always-present entry point for `standard_login`
    (established_session's own pre-crawl login-page capture), distinct from
    the multi-page wizard path the other test covers."""
    init_db()
    configure(expire_after=None)
    secret_ref_path, application_external_id, discovery_run_external_id = _seed_application_at(
        f"{target_app_url}wizard/step-c"
    )

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )

    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == application_external_id)
        ).one()
        first_block = session.exec(
            select(BlockedTask).where(BlockedTask.application_id == application.id)
        ).one()
        first_steps = list(
            session.exec(
                select(ExplorationStep).where(
                    ExplorationStep.blocked_task_id == first_block.id
                )
            ).all()
        )
        # Started directly at step-c, but `establish_session`'s own
        # pre-crawl login capture always seeds the first page's `from_url`
        # with the login page (Story 2.2's "Sign in" journey feature) — so
        # there's a real preceding hop (login page -> step-c) even here.
        assert len(first_steps) == 2, first_steps
        first_max_order = max(s.step_order for s in first_steps)

    # A second, independent DiscoveryRun for the same Application hitting the
    # exact same field again.
    with Session(engine) as session:
        second_run = DiscoveryRun(application_id=application.id, status="running")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_external_id = second_run.external_id

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(second_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref_path,
        )
    )

    with Session(engine) as session:
        blocks = list(
            session.exec(
                select(BlockedTask).where(BlockedTask.application_id == application.id)
            ).all()
        )
        assert len(blocks) == 1, "the same aggregation_key must not create a second BlockedTask"
        all_steps = list(
            session.exec(
                select(ExplorationStep).where(ExplorationStep.blocked_task_id == blocks[0].id)
            ).all()
        )
        assert len(all_steps) == 4, "the second block's steps must extend, not collide"
        assert {s.step_order for s in all_steps} == {1, 2, 3, 4}
        new_orders = {s.step_order for s in all_steps if s.step_order > first_max_order}
        assert new_orders == {first_max_order + 1, first_max_order + 2}

        # AC 3/6: the only entry point available is the login page (not
        # step-c itself, and not the Application root either) — resume must
        # pick it, not degrade further than it needs to.
        blocked_task = blocks[0]
        discovery_run_pk = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.external_id == second_run_external_id)
        ).one().id

        vault_client = VaultSecretsClient()
        credential = vault_client.resolve(SecretRef(path=secret_ref_path))
        object_store = ObjectStore()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            resume_result = await resume_blocked_task(
                session,
                browser,
                application=application,
                blocked_task=blocked_task,
                supplied_value="POL-777",
                credential=credential,
                object_store=object_store,
                discovery_run_id=discovery_run_pk,
            )
            await browser.close()

    assert resume_result.resumed_from_root is False
    assert resume_result.entry_point_url.endswith("/login")
