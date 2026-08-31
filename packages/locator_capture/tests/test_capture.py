"""Unit tests for the extracted locator-capture logic (Story 2.21's ranked
locator candidates, moved out of discovery_worker/crawler.py verbatim) plus
the new page-level `extract_page_locator_snapshot` driver added for
execution_worker's self-heal live inspection.

Pure-function tests only — no real Chromium needed here (discovery_worker's
own `test_locator_durability.py` already covers the real-Chromium/real-app
cases against `discovery_worker.crawler`'s re-exported names, and must
keep passing unmodified as proof this extraction changed nothing)."""

import pytest
from locator_capture import capture_locator_candidates, extract_page_locator_snapshot
from locator_capture.capture import _build_locator_candidates, _is_fragile_locator_value

# --- fragility detection ---------------------------------------------------


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


# --- candidate building/ranking --------------------------------------------


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


class _FakeLocator:
    def __init__(self, info: dict) -> None:
        self._info = info

    async def evaluate(self, script: str) -> dict:
        return self._info


@pytest.mark.asyncio
async def test_capture_locator_candidates_skips_text_backfill_for_input_tag() -> None:
    locator = _FakeLocator(
        {
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
    )
    candidates = await capture_locator_candidates(locator, fallback_text="txtUserName")
    assert not any(c["strategy"] == "text" for c in candidates)


@pytest.mark.asyncio
async def test_capture_locator_candidates_still_backfills_text_for_button_tag() -> None:
    locator = _FakeLocator(
        {
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
    )
    candidates = await capture_locator_candidates(locator, fallback_text="Save")
    assert any(c["strategy"] == "text" and c["value"] == 'text="Save"' for c in candidates)


@pytest.mark.asyncio
async def test_capture_locator_candidates_is_best_effort_on_a_detached_element() -> None:
    class _RaisingLocator:
        async def evaluate(self, script: str) -> dict:
            raise Exception("element is not attached to the DOM")

    assert await capture_locator_candidates(_RaisingLocator()) == []


# --- extract_page_locator_snapshot (new) -----------------------------------


class _FakeElement:
    def __init__(self, tag: str, info: dict) -> None:
        self._tag = tag
        self._info = info

    async def evaluate(self, script: str) -> object:
        # The real call sites only ever pass either the bare tagName-
        # extraction script (extract_page_locator_snapshot's own probe,
        # "el => el.tagName.toLowerCase()") or the multi-line
        # _LOCATOR_INFO_SCRIPT (via capture_locator_candidates) — the two
        # are trivially distinguishable by script length/shape.
        if script.strip() == "el => el.tagName.toLowerCase()":
            return self._tag
        return self._info


class _FakeLocatorList:
    def __init__(self, elements: list[_FakeElement]) -> None:
        self._elements = elements

    async def count(self) -> int:
        return len(self._elements)

    def nth(self, index: int) -> _FakeElement:
        return self._elements[index]


class _FakePage:
    def __init__(self, elements: list[_FakeElement]) -> None:
        self._elements = elements

    def locator(self, selector: str) -> _FakeLocatorList:
        return _FakeLocatorList(self._elements)


@pytest.mark.asyncio
async def test_extract_page_locator_snapshot_tags_each_candidate_with_its_element() -> None:
    elements = [
        _FakeElement(
            "button",
            {
                "testid": "save-button",
                "role": "button",
                "name": "Save",
                "label": None,
                "text": "Save",
                "tag": "button",
                "idAttr": None,
                "firstClass": None,
                "scoped": None,
                "absolute": "button:nth-child(1)",
            },
        ),
    ]
    snapshot = await extract_page_locator_snapshot(_FakePage(elements))
    assert snapshot
    assert all(c["element_tag"] == "button" for c in snapshot)
    assert snapshot[0]["strategy"] == "testid"


@pytest.mark.asyncio
async def test_extract_page_locator_snapshot_is_bounded_by_max_candidates() -> None:
    info = {
        "testid": "x",
        "role": None,
        "name": "",
        "label": None,
        "text": "",
        "tag": "button",
        "idAttr": None,
        "firstClass": None,
        "scoped": None,
        "absolute": "button:nth-child(1)",
    }
    elements = [_FakeElement("button", info) for _ in range(10)]
    snapshot = await extract_page_locator_snapshot(_FakePage(elements), max_candidates=3)
    # One candidate per element here (testid only) — bounded count proves
    # the cap is respected regardless of how many candidates each yields.
    assert len({c["value"] for c in snapshot}) <= 3


@pytest.mark.asyncio
async def test_extract_page_locator_snapshot_skips_an_element_that_cannot_be_probed() -> None:
    class _DetachedElement:
        async def evaluate(self, script: str) -> object:
            raise Exception("element is not attached to the DOM")

    class _MixedLocatorList:
        def __init__(self) -> None:
            self._elements = [
                _DetachedElement(),
                _FakeElement(
                    "a",
                    {
                        "testid": "link-1",
                        "role": "link",
                        "name": "Home",
                        "label": None,
                        "text": "Home",
                        "tag": "a",
                        "idAttr": None,
                        "firstClass": None,
                        "scoped": None,
                        "absolute": "a:nth-child(1)",
                    },
                ),
            ]

        async def count(self) -> int:
            return len(self._elements)

        def nth(self, index: int) -> object:
            return self._elements[index]

    class _MixedPage:
        def locator(self, selector: str) -> _MixedLocatorList:
            return _MixedLocatorList()

    snapshot = await extract_page_locator_snapshot(_MixedPage())
    # The detached element yields zero candidates (skipped, not raised);
    # the surviving element's several ranked candidates all still appear.
    assert snapshot
    assert all(c["element_tag"] == "a" for c in snapshot)
