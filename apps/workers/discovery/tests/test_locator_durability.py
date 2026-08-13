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
    _LOCATOR_TIER_ORDER,
    _build_locator_candidates,
    _capture_locator_candidates,
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


class _FakeLiveLocator:
    """Stand-in for `page.locator(value)` — resolves to a fixed `.count()`."""

    def __init__(self, count: int) -> None:
        self._count = count

    async def count(self) -> int:
        return self._count


class _FakeLivePage:
    """Minimal stand-in for `Locator.page`. `counts_by_value` maps a candidate
    value to its live match count; anything not listed resolves to 1 (i.e.
    confirmed unique) by default so tests not about the live check itself are
    unaffected by it."""

    def __init__(self, counts_by_value: dict[str, int] | None = None) -> None:
        self._counts_by_value = counts_by_value or {}
        self.checked_selectors: list[str] = []

    def locator(self, value: str) -> _FakeLiveLocator:
        self.checked_selectors.append(value)
        return _FakeLiveLocator(self._counts_by_value.get(value, 1))


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
    # `id` is now its own dedicated tier (was folded into `css_scoped`) —
    # ranked well above raw text/label, matching the durability priority a
    # bare `#id` selector actually deserves.
    assert candidates[0]["strategy"] == "id"
    assert candidates[0]["value"] == "#bare-div"


def test_other_data_attribute_ranks_between_testid_and_id() -> None:
    info = {
        "testid": None,
        "role": None,
        "name": "",
        "text": "",
        "label": None,
        "tag": "div",
        "idAttr": "confirm-panel",
        "nameAttr": None,
        "typeAttr": None,
        "otherDataAttr": {"name": "data-qa", "value": "confirm-order"},
        "firstClass": None,
        "scoped": None,
        "absolute": "div:nth-child(1)",
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    assert candidates[0]["strategy"] == "data_attr"
    assert candidates[0]["value"] == '[data-qa="confirm-order"]'
    assert candidates[1]["strategy"] == "id"
    assert candidates[1]["value"] == "#confirm-panel"


def test_name_attribute_produces_name_strategy_candidate() -> None:
    info = {
        "testid": None,
        "role": "textbox",
        "name": "",
        "text": "",
        "label": None,
        "tag": "input",
        "idAttr": None,
        "nameAttr": "username",
        "typeAttr": "text",
        "otherDataAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": None,
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    name_candidate = next(c for c in candidates if c["strategy"] == "name")
    assert name_candidate["value"] == '[name="username"]'


def test_input_type_and_name_combo_produces_type_name_strategy() -> None:
    info = {
        "testid": None,
        "role": "textbox",
        "name": "",
        "text": "",
        "label": None,
        "tag": "input",
        "idAttr": None,
        "nameAttr": "username",
        "typeAttr": "text",
        "otherDataAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": None,
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    combo = next(c for c in candidates if c["strategy"] == "type_name")
    assert combo["value"] == 'input[type="text"][name="username"]'


def test_type_name_strategy_skipped_for_non_input_tags() -> None:
    """A `<button type="submit" name="go">` should never produce a
    `button[type="submit"][name="go"]` locator — the combo tier is scoped to
    `<input>` elements only, matching what `ai_provider.hosted`'s prompt
    actually asks the model to prefer for form fields."""
    info = {
        "testid": None,
        "role": "button",
        "name": "",
        "text": "",
        "label": None,
        "tag": "button",
        "idAttr": None,
        "nameAttr": "go",
        "typeAttr": "submit",
        "otherDataAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": None,
    }
    candidates = _build_locator_candidates(info, frame_path=None)
    assert not any(c["strategy"] == "type_name" for c in candidates)


def test_tier_order_matches_documented_priority_list() -> None:
    order = _LOCATOR_TIER_ORDER
    assert (
        order["testid"]
        < order["data_attr"]
        < order["id"]
        < order["name"]
        < order["type_name"]
        < order["aria"]
        < order["css_scoped"]
        < order["css_absolute"]
        < order["text"]
    )
    assert order["aria"] == order["label"]


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

    class FakeLocator:
        page = _FakeLivePage()  # every candidate resolves to 1 (confirmed unique)

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
    class FakeLocator:
        page = _FakeLivePage()

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


# --- pure-fake tests: live uniqueness check -------------------------------


@pytest.mark.asyncio
async def test_capture_locator_candidates_annotates_top_n_and_skips_the_rest() -> None:
    """Bounded to the top 3 ranked candidates — the 4th (lowest-tier) never
    gets a live `.count()` check at all."""
    fake_page = _FakeLivePage({"#a": 0, "css=.b": 0, "css=#scope > div": 0})

    class FakeLocator:
        page = fake_page

        async def evaluate(self, script: str) -> dict:
            return {
                "testid": None,
                "role": None,
                "name": "",
                "text": "",
                "label": None,
                "tag": "div",
                "idAttr": "a",
                "nameAttr": None,
                "typeAttr": None,
                "otherDataAttr": None,
                "firstClass": "b",
                "scoped": "#scope > div",
                "absolute": "div:nth-child(1)",
            }

    candidates = await _capture_locator_candidates(FakeLocator())
    # 4 total candidates (id, css_scoped x2, css_absolute) — only the top 3
    # ranked ones are live-checked.
    assert len(fake_page.checked_selectors) == 3
    checked = [c for c in candidates if "live_match_count" in c]
    unchecked = [c for c in candidates if "live_match_count" not in c]
    assert len(checked) == 3
    assert len(unchecked) == 1
    assert all(c["live_match_count"] == 0 for c in checked)


@pytest.mark.asyncio
async def test_live_zero_match_candidate_is_confirmed_invalid_and_ranked_below_a_valid_one() -> None:
    """A stale/incorrect `data-testid` (0 live matches) must never outrank a
    lower-tier candidate that's actually confirmed unique — this is the core
    fix: durability tier alone is no longer enough, live resolution matters."""
    fake_page = _FakeLivePage({'[data-testid="ghost"]': 0, "#real-id": 1})

    class FakeLocator:
        page = fake_page

        async def evaluate(self, script: str) -> dict:
            return {
                "testid": "ghost",
                "role": None,
                "name": "",
                "text": "",
                "label": None,
                "tag": "div",
                "idAttr": "real-id",
                "nameAttr": None,
                "typeAttr": None,
                "otherDataAttr": None,
                "firstClass": None,
                "scoped": None,
                "absolute": None,
            }

    candidates = await _capture_locator_candidates(FakeLocator())
    assert candidates[0]["strategy"] == "id"
    assert candidates[0]["value"] == "#real-id"
    assert candidates[0]["live_match_count"] == 1
    ghost = next(c for c in candidates if c["strategy"] == "testid")
    assert ghost["live_match_count"] == 0
    assert candidates.index(ghost) > 0


@pytest.mark.asyncio
async def test_live_check_failure_leaves_candidate_unannotated_and_never_raises() -> None:
    """An unsupported selector shape (e.g. a Playwright version that can't
    evaluate a chained frame-piercing `>>` selector) must degrade gracefully
    — same tolerance every other capture helper in this module has."""

    class _RaisingPage:
        def locator(self, value: str):
            raise RuntimeError("unsupported selector shape")

    class FakeLocator:
        page = _RaisingPage()

        async def evaluate(self, script: str) -> dict:
            return {
                "testid": "save-button",
                "role": None,
                "name": "",
                "text": "",
                "label": None,
                "tag": "button",
                "idAttr": None,
                "nameAttr": None,
                "typeAttr": None,
                "otherDataAttr": None,
                "firstClass": None,
                "scoped": None,
                "absolute": None,
            }

    candidates = await _capture_locator_candidates(FakeLocator())
    assert candidates[0]["strategy"] == "testid"
    assert "live_match_count" not in candidates[0]


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
    # `id` is now its own dedicated tier (was folded into `css_scoped`).
    assert candidates["bare"][0]["strategy"] == "id"
    assert not any(
        c["strategy"] in ("testid", "data_attr", "aria", "text", "label")
        for c in candidates["bare"]
    )


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


@pytest.mark.skipif(not _db_available(), reason="requires PostgreSQL reachable")
def test_derive_locators_folds_live_invalid_into_fragile_flag() -> None:
    """A candidate that resolved to 0 (or >1) elements live during capture
    must persist as `fragile=True` even when its own `fragile` flag (the
    syntactic heuristic) was `False` — a stale/incorrect `data-testid` is not
    a syntactically fragile value, but it is exactly as untrustworthy as one."""
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
            name="Live Invalid Locator Test App",
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

        component = Component(
            application_id=application.id,
            page_id=page.id,
            form_id=None,
            name="Ghost Button",
            type="button",
            action="click",
        )
        session.add(component)
        session.flush()

        _derive_locators(
            session,
            component,
            [
                (
                    None,
                    [
                        {
                            "strategy": "testid",
                            "value": '[data-testid="ghost"]',
                            "fragile": False,
                            "live_match_count": 0,
                        }
                    ],
                )
            ],
        )

        [locator] = list(
            session.exec(
                select(ComponentLocator).where(ComponentLocator.component_id == component.id)
            ).all()
        )
        assert locator.fragile is True
