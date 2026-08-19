"""Story 2.21: ranked locator capture, fragility detection, container-chain
recording, and the model-builder-side ranking/durability aggregate. Pure
unit tests for the ranking logic; real Chromium for the parts that need a
live element (AC 1-3); real Postgres for the model-builder aggregate (AC 4).
"""

import json
import uuid

import pytest
from discovery_worker.crawler import (
    CapturedForm,
    _build_locator_candidates,
    _is_fragile_locator_value,
    run_discovery_crawl,
)
from discovery_worker.model_builder import (
    _derive_locators,
    _rank_locator_candidates,
    fragile_locator_proportion,
)
from discovery_worker.session import establish_session
from playwright.async_api import async_playwright


class FakeObjectStore:
    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        return "fake/0"


# --- pure unit tests: fragility detection --------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "css=.css-1x2y3z",
        "css=.sc-hKgILt",
        "#ctl00_ContentPlaceHolder1_Submit",
        "css=div:nth-child(3) > div:nth-child(7)",
        "#a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    ],
)
def test_fragile_patterns_detected(value: str) -> None:
    assert _is_fragile_locator_value(value) is True


@pytest.mark.parametrize(
    "value",
    ['[data-testid="save-button"]', 'role=button[name="Save"]', "#checkout-form", "#bare-div"],
)
def test_non_fragile_values_not_flagged(value: str) -> None:
    assert _is_fragile_locator_value(value) is False


# --- locator-accuracy fix: a filled-in value must never pass as a name ---


@pytest.mark.parametrize(
    "value",
    [
        'role=textbox[name="500000"]',
        'role=textbox[name="9.5"]',
        'role=textbox[name="60"]',
        'text="$1,234.56"',
        'role=textbox[name="12%"]',
    ],
)
def test_quoted_numeric_name_or_text_is_fragile(value: str) -> None:
    """A quoted `name=`/`text=` value that's purely a number (with optional
    currency/percent/thousands punctuation) is data a field happened to
    carry at capture time — a loan principal, a rate, a term — never a
    stable label, regardless of which capture path produced it."""
    assert _is_fragile_locator_value(value) is True


def test_quoted_alphabetic_name_is_not_flagged_by_the_numeric_check() -> None:
    assert _is_fragile_locator_value('role=textbox[name="Principal Amount"]') is False


# --- pure unit tests: candidate building/ranking -------------------------


def test_testid_ranks_first_among_multiple_candidates() -> None:
    info = {
        "testid": "save-button",
        "role": "button",
        "name": "Save",
        "text": "Save",
        "label": None,
        "idAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": "button:nth-child(1)",
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    assert candidates[0]["strategy"] == "testid"
    assert candidates[0]["value"] == '[data-testid="save-button"]'


def test_css_in_js_hash_ranks_below_aria_role_and_name() -> None:
    info = {
        "testid": None,
        "role": "button",
        "name": "Confirm order",
        "text": "Confirm order",
        "label": None,
        "idAttr": None,
        "firstClass": "css-1x2y3z",
        "scoped": None,
        "absolute": "button:nth-child(2)",
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    strategies_in_order = [c["strategy"] for c in candidates]
    hash_candidate = next(c for c in candidates if "css-1x2y3z" in c["value"])
    aria_candidate = next(c for c in candidates if c["strategy"] == "aria")
    assert hash_candidate["fragile"] is True
    assert strategies_in_order.index("aria") < candidates.index(hash_candidate)
    assert aria_candidate["value"] == 'role=button[name="Confirm order"]'


def test_no_testid_role_or_text_falls_through_to_scoped_css_and_scores_low() -> None:
    info = {
        "testid": None,
        "role": None,
        "name": "",
        "text": "",
        "label": None,
        "idAttr": "bare-div",
        "firstClass": None,
        "scoped": None,
        "absolute": "div:nth-child(3)",
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    assert candidates[0]["strategy"] == "css_scoped"
    assert candidates[0]["value"] == "#bare-div"


def test_frame_path_is_prefixed_onto_every_candidate_value() -> None:
    info = {
        "testid": "save-button",
        "role": None,
        "name": "",
        "text": "",
        "label": None,
        "idAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": "button:nth-child(1)",
    }
    candidates = _build_locator_candidates(info, frame_path='iframe[src="http://x/frame"]')
    assert all(c["value"].startswith('iframe[src="http://x/frame"] >> ') for c in candidates)


@pytest.mark.asyncio
async def test_capture_locator_candidates_skips_text_backfill_for_input_tag() -> None:
    """A `text="<fallback>"` candidate for an input/select/textarea would be
    the field's internal name/id masquerading as visible text — it can
    never match real page content, unlike for a button/link (below)."""
    from discovery_worker.crawler import _capture_locator_candidates

    class FakeLocator:
        async def evaluate(self, script: str) -> dict:
            return {
                "testid": None,
                "role": "textbox",
                "name": "",
                "label": None,
                "text": "",
                "tag": "input",
                "idAttr": None,
                "firstClass": None,
                "scoped": None,
                "absolute": "input:nth-child(1)",
            }

    candidates = await _capture_locator_candidates(FakeLocator(), fallback_text="txtUserName")
    assert not any(c["strategy"] == "text" for c in candidates)


@pytest.mark.asyncio
async def test_capture_locator_candidates_still_backfills_text_for_button_tag() -> None:
    from discovery_worker.crawler import _capture_locator_candidates

    class FakeLocator:
        async def evaluate(self, script: str) -> dict:
            return {
                "testid": None,
                "role": "button",
                "name": "",
                "label": None,
                "text": "",
                "tag": "button",
                "idAttr": None,
                "firstClass": None,
                "scoped": None,
                "absolute": "button:nth-child(1)",
            }

    candidates = await _capture_locator_candidates(FakeLocator(), fallback_text="Save")
    assert any(c["strategy"] == "text" and c["value"] == 'text="Save"' for c in candidates)


def test_rank_locator_candidates_dedupes_and_sorts_fragile_last() -> None:
    ranked = _rank_locator_candidates(
        [
            [{"strategy": "css_scoped", "value": "css=.hash1", "fragile": True}],
            [
                {"strategy": "aria", "value": 'role=button[name="Save"]', "fragile": False},
                {"strategy": "css_scoped", "value": "css=.hash1", "fragile": True},
            ],
        ]
    )
    assert [c["value"] for c in ranked] == ['role=button[name="Save"]', "css=.hash1"]


# --- real Chromium: candidate capture against live elements --------------


async def _capture_candidates_on_locators_page(target_app_url: str) -> dict[str, list[dict]]:
    from discovery_worker.crawler import _capture_locator_candidates

    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        page = await context.new_page()
        await page.goto(f"{target_app_url}locators")
        result = {
            "Save": await _capture_locator_candidates(
                page.get_by_role("button", name="Save", exact=True)
            ),
            "Confirm order": await _capture_locator_candidates(
                page.get_by_role("button", name="Confirm order", exact=True)
            ),
            "bare": await _capture_locator_candidates(page.locator("#bare-div")),
            "principal": await _capture_locator_candidates(page.locator('input[name="principal"]')),
            "promoCode": await _capture_locator_candidates(page.locator('input[name="promoCode"]')),
        }
        await context.close()
        await browser.close()
    return result


@pytest.mark.asyncio
async def test_real_element_with_testid_captures_testid_first(target_app_url: str) -> None:
    candidates = await _capture_candidates_on_locators_page(target_app_url)
    assert candidates["Save"][0]["strategy"] == "testid"
    assert candidates["Save"][0]["value"] == '[data-testid="save-button"]'


@pytest.mark.asyncio
async def test_real_hash_classed_element_ranks_aria_above_the_hash(target_app_url: str) -> None:
    candidates = await _capture_candidates_on_locators_page(target_app_url)
    confirm = candidates["Confirm order"]
    aria_index = next(i for i, c in enumerate(confirm) if c["strategy"] == "aria")
    hash_index = next(i for i, c in enumerate(confirm) if "css-1x2y3z" in c["value"])
    assert aria_index < hash_index
    assert confirm[hash_index]["fragile"] is True


@pytest.mark.asyncio
async def test_real_bare_element_falls_through_to_scoped_css(target_app_url: str) -> None:
    candidates = await _capture_candidates_on_locators_page(target_app_url)
    assert candidates["bare"], candidates
    assert candidates["bare"][0]["strategy"] == "css_scoped"
    assert not any(c["strategy"] in ("testid", "aria", "text", "label") for c in candidates["bare"])


@pytest.mark.asyncio
async def test_real_prefilled_unlabeled_input_never_captures_its_value_as_a_name(
    target_app_url: str,
) -> None:
    """Locator-accuracy fix — `/locators`' `principal` input is pre-filled
    with "500000" and has no label/aria-label/id; before the fix this
    produced a non-fragile `role=textbox[name="500000"]` "aria" candidate
    (the field's current value masquerading as its accessible name). Now:
    no "aria" candidate at all (nothing legitimate to build one from), and
    its own `name` attribute surfaces as a durable, non-fragile candidate
    instead of falling straight through to the fragile absolute path."""
    candidates = await _capture_candidates_on_locators_page(target_app_url)
    principal = candidates["principal"]
    assert not any(c["strategy"] == "aria" for c in principal), principal
    name_attr_candidate = next(c for c in principal if c["value"] == '[name="principal"]')
    assert name_attr_candidate["fragile"] is False
    assert not any("500000" in c["value"] for c in principal), principal


@pytest.mark.asyncio
async def test_real_placeholder_only_input_captures_a_fragile_aria_candidate(
    target_app_url: str,
) -> None:
    """`/locators`' `promoCode` input has a placeholder and no value/label —
    a real ARIA accessible name once no label exists, but explicitly
    fragile (placeholder text can echo dynamic/example content)."""
    candidates = await _capture_candidates_on_locators_page(target_app_url)
    promo = candidates["promoCode"]
    aria_candidate = next(
        (c for c in promo if c["strategy"] == "aria" and "SAVE10" in c["value"]), None
    )
    assert aria_candidate is not None, promo
    assert aria_candidate["fragile"] is True


@pytest.mark.asyncio
async def test_element_inside_iframe_records_a_resolvable_container_chain(
    target_app_url: str,
) -> None:
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    captured: list = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        await run_discovery_crawl(
            context,
            f"{target_app_url}frames",
            FakeObjectStore(),
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
            on_capture=captured.append,
        )
        await context.close()
        await browser.close()

    forms = [item for item in captured if isinstance(item, CapturedForm)]
    frame_form = next(f for f in forms if f.action_url == "/items" and f.fields)
    candidate_values = [
        c["value"] for field in frame_form.fields for c in (field.locator_candidates or [])
    ]
    assert candidate_values, frame_form
    assert all(v.startswith("iframe[src=") and " >> " in v for v in candidate_values)


# --- model_builder: durability aggregate ----------------------------------


def test_fragile_locator_proportion_returns_none_with_no_locators() -> None:
    from unittest.mock import MagicMock

    session = MagicMock()
    session.exec.return_value.all.return_value = []
    assert fragile_locator_proportion(session, uuid.uuid4()) is None


def _db_available() -> bool:
    from discovery_worker.db import engine
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


@pytest.mark.skipif(not _db_available(), reason="requires PostgreSQL reachable")
def test_derive_locators_and_fragile_proportion_against_real_postgres() -> None:
    from discovery_worker.db import engine, init_db
    from domain import Application, Component, ComponentLocator, DiscoveryRun, Organization, Page
    from sqlmodel import Session, select

    init_db()
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Locator Durability Test App",
            url="https://example.test",
            environment="test",
            secret_ref="unused",
        )
        session.add(application)
        session.flush()
        run = DiscoveryRun(application_id=application.id)
        session.add(run)
        session.flush()
        page = Page(application_id=application.id, discovery_run_id=run.id, url="/")
        session.add(page)
        session.flush()

        durable_component = Component(
            application_id=application.id,
            page_id=page.id,
            form_id=None,
            name="Save",
            type="button",
            action="click",
        )
        fragile_component = Component(
            application_id=application.id,
            page_id=page.id,
            form_id=None,
            name="Confirm order",
            type="button",
            action="click",
        )
        legacy_component = Component(
            application_id=application.id,
            page_id=page.id,
            form_id=None,
            name="Legacy Button",
            type="button",
            action="click",
        )
        session.add(durable_component)
        session.add(fragile_component)
        session.add(legacy_component)
        session.flush()

        _derive_locators(
            session,
            durable_component,
            [(None, [{"strategy": "testid", "value": '[data-testid="save"]', "fragile": False}])],
        )
        _derive_locators(
            session,
            fragile_component,
            [(None, [{"strategy": "css_scoped", "value": "css=.hash1", "fragile": True}])],
        )
        # AC 5: a row captured before this story landed has no
        # `locator_candidates` at all — only the legacy `captured_selector`
        # string — and must still produce a working `ComponentLocator`.
        _derive_locators(session, legacy_component, [('[data-testid="legacy"]', None)])

        proportion = fragile_locator_proportion(session, application.id)
        assert proportion == pytest.approx(1 / 3)

        legacy_locators = list(
            session.exec(
                select(ComponentLocator).where(
                    ComponentLocator.component_id == legacy_component.id
                )
            ).all()
        )
        assert len(legacy_locators) == 1
        assert legacy_locators[0].value == '[data-testid="legacy"]'
        assert legacy_locators[0].strategy == "testid"
        assert legacy_locators[0].fragile is False
