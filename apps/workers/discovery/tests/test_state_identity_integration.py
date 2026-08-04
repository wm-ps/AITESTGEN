"""Story 2.10 Task 8 integration bullets — the real `discovery_activity`
end-to-end (Postgres + Vault + MinIO + a live local target), same
skip-cleanly convention as test_discovery_activity_integration.py. Scoped
to `/records/{id}` (a dead-end fixture linking only to itself) so this
doesn't re-run the whole dashboard crawl per test.
"""

import json
import uuid

import pytest
from discovery_worker.activities import discovery_activity
from discovery_worker.crawler import _SHADOW_TRACKING_INIT_SCRIPT, _capture_state_signals
from discovery_worker.db import engine, init_db
from discovery_worker.object_store import MINIO_ENDPOINT
from discovery_worker.session import establish_session
from domain import Application, DiagnosticRecord, DiscoveryRun, Organization, Page
from fixtures.target_app import configure
from playwright.async_api import async_playwright
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN, VaultSecretsClient
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


def _minio_available() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{MINIO_ENDPOINT}/minio/health/live", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and _minio_available()),
    reason="requires PostgreSQL + Vault + MinIO reachable — start docker compose",
)


def _seed_application_at(start_url: str) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Returns (secret_ref_path, application_external_id, discovery_run_external_id)."""
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()

        credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
        secret_ref = VaultSecretsClient().store(org.id, credential)

        application = Application(
            organization_id=org.id,
            name="State Identity Test App",
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
async def test_three_same_route_template_pages_collapse_to_two_canonical_pages(
    target_app_url: str,
) -> None:
    """AC 2/9: record 1 and record 3 (identical heading+actions) -> SAME;
    record 2 (Approve/Reject instead of Edit/Submit) -> VARIANT of record 1.
    Three visited URLs, two canonical `Page` rows, one `variant_of_page_id`
    pointing at the other."""
    init_db()
    configure(expire_after=None)
    secret_ref, application_external_id, discovery_run_external_id = _seed_application_at(
        f"{target_app_url}records/1"
    )

    result = await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref,
        )
    )
    assert result.status == "complete"

    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == application_external_id)
        ).one()
        pages = list(
            session.exec(select(Page).where(Page.application_id == application.id)).all()
        )

    record_pages = [p for p in pages if "/records/" in p.url]
    assert len(record_pages) == 2, [p.url for p in record_pages]

    variant_rows = [p for p in record_pages if p.variant_of_page_id is not None]
    canonical_rows = [p for p in record_pages if p.variant_of_page_id is None]
    assert len(variant_rows) == 1, record_pages
    assert len(canonical_rows) == 1, record_pages
    assert variant_rows[0].variant_of_page_id == canonical_rows[0].id
    # Record 1 (the first one visited) is the canonical row; record 2 is its variant.
    assert canonical_rows[0].url.endswith("/records/1")
    assert variant_rows[0].url.endswith("/records/2")


@pytest.mark.asyncio
async def test_every_classification_emits_a_diagnostic_with_all_signal_values(
    target_app_url: str,
) -> None:
    """AC 5: no classification is silent — every `classify()` call writes a
    diagnostic carrying all four component scores."""
    init_db()
    configure(expire_after=None)
    secret_ref, application_external_id, discovery_run_external_id = _seed_application_at(
        f"{target_app_url}records/1"
    )

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref,
        )
    )

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.external_id == discovery_run_external_id)
        ).one()
        diagnostics = list(
            session.exec(
                select(DiagnosticRecord).where(
                    DiagnosticRecord.discovery_run_id == discovery_run.id,
                    DiagnosticRecord.kind == "state_identity",
                )
            ).all()
        )

    record_diagnostics = [d for d in diagnostics if "/records/" in d.payload.get("url", "")]
    # One per record page (1, 2, 3) — the login page and dashboard aren't
    # under /records/ so aren't counted here.
    assert len(record_diagnostics) == 3, [d.payload for d in diagnostics]
    for diagnostic in record_diagnostics:
        payload = diagnostic.payload
        for key in (
            "verdict",
            "route_template",
            "ambiguous",
            "widened_mode",
            "heading_score",
            "action_score",
            "form_score",
            "structure_score",
            "composite_score",
        ):
            assert key in payload, (key, payload)


@pytest.mark.asyncio
async def test_route_template_hard_filter_produces_no_diagnostic_for_unrelated_pages(
    target_app_url: str,
) -> None:
    """AC 1: a page with no route-template match is classified NEW without
    ever running the weighted score against unrelated pages — still emits
    exactly one diagnostic of its own, with null component scores."""
    init_db()
    configure(expire_after=None)
    secret_ref, application_external_id, discovery_run_external_id = _seed_application_at(
        f"{target_app_url}records/1"
    )

    await discovery_activity(
        DiscoveryActivityInput(
            discovery_run_id=str(discovery_run_external_id),
            application_id=str(application_external_id),
            secret_ref=secret_ref,
        )
    )

    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(DiscoveryRun.external_id == discovery_run_external_id)
        ).one()
        diagnostics = list(
            session.exec(
                select(DiagnosticRecord).where(
                    DiagnosticRecord.discovery_run_id == discovery_run.id,
                    DiagnosticRecord.kind == "state_identity",
                )
            ).all()
        )

    record_1 = next(d for d in diagnostics if d.payload.get("url", "").endswith("/records/1"))
    assert record_1.payload["verdict"] == "NEW"
    assert record_1.payload["composite_score"] is None


@pytest.mark.asyncio
async def test_unreachable_containers_are_folded_into_the_structural_fingerprint(
    target_app_url: str,
) -> None:
    """Task 2: a page's closed-shadow-root and cross-origin-frame counts
    are observable structural facts — two pages differing only in
    reachability must not fingerprint identically. Real Chromium against
    Story 2.14's `/shadow-dom` (one closed root) and `/frames` (one cross-
    origin iframe) fixtures, direct call — no Activity/DB needed for this
    specific check."""
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        page = await context.new_page()
        # Story 2.14's attachShadow-tracking init script must be installed
        # before the page's own script runs — same requirement as the real
        # crawl loop.
        await page.add_init_script(_SHADOW_TRACKING_INIT_SCRIPT)
        await page.goto(f"{target_app_url}shadow-dom")
        _, shadow_tokens = await _capture_state_signals(page)

        await page.goto(f"{target_app_url}frames")
        _, frame_tokens = await _capture_state_signals(page)

        await context.close()
        await browser.close()

    assert any(t.startswith("unreachable:closed_shadow_root:") for t in shadow_tokens), (
        shadow_tokens
    )
    assert any(t.startswith("unreachable:cross_origin_frame:") for t in frame_tokens), (
        frame_tokens
    )
