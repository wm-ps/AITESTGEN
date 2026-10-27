"""Saved routes (pursue.remember_route / tests_stage.route_screens): a route
is filed under the stored screen, never under the name a model gave it on
one visit, so the next scenario on that screen replays it instead of the
model walking in again."""

import asyncio
import uuid
from types import SimpleNamespace

from explorer_worker.pursue import is_shorter
from explorer_worker.tests_stage import QuietMind, route_screens

APP = "https://shop.example/app"


def _screen(pattern: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), url_pattern=pattern)


def test_only_an_address_that_shows_one_screen_gets_a_route() -> None:
    contact, resume_a, resume_b = (
        _screen("//shop.example/app#/Contact"),
        _screen("//shop.example/app#/Resume"),
        _screen("//shop.example/app#/Resume"),
    )
    ids = route_screens([contact, resume_a, resume_b])  # type: ignore[list-item]
    assert ids == {"//shop.example/app#/Contact": contact.id}


class _Journal:
    def event(self, *args: object) -> None:
        pass

    def shot(self, data: bytes) -> None:
        return None

    def screen_rows(self) -> list[object]:
        return []


def test_quiet_mind_knows_the_stored_screen_by_its_address() -> None:
    mind = QuietMind(_Journal(), None, lambda: None)  # type: ignore[arg-type]
    contact = uuid.uuid4()
    visit = SimpleNamespace(
        url=f"{APP}#/Contact", inventory={"headings": ["Contact details"]}, shot=b""
    )

    # No screens given (signed out, or continuing a draft): nothing is saved.
    assert asyncio.run(mind.take_in(visit, None)) == "Contact details"  # type: ignore[arg-type]
    assert mind.last_screen_id is None

    mind.screen_ids = {"//shop.example/app#/Contact": contact}
    asyncio.run(mind.take_in(visit, None))  # type: ignore[arg-type]
    assert mind.last_screen_id == contact
    asyncio.run(mind.take_in(SimpleNamespace(url=f"{APP}#/Other", inventory={}, shot=b""), None))  # type: ignore[arg-type]
    assert mind.last_screen_id is None  # never filed under the previous screen


def test_only_a_shorter_route_replaces_the_saved_one() -> None:
    two = [{"do": "goto", "url": APP}, {"do": "click", "label": "Next"}]
    assert is_shorter(two, None)
    assert is_shorter(two[:1], two)
    assert not is_shorter(two, two)


def test_scenarios_are_tried_screen_by_screen_journeys_first() -> None:
    from explorer_worker.tests_stage import screen_by_screen

    rows = [
        ("a1", "validation", "Contact"),
        ("b1", "data_load", "Photos"),
        ("j1", "journey", "Home"),
        ("a2", "navigation", "Contact"),
        ("b2", "validation", "Photos"),
        ("a3", "data_load", "Contact"),
    ]
    assert screen_by_screen(rows) == ["j1", "a1", "a2", "a3", "b1", "b2"]


def test_a_second_try_only_when_the_first_reached_the_screen() -> None:
    from explorer_worker.tests_stage import reached_screen

    def screen(name: str, pattern: str) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), name=name, url_pattern=pattern)

    screens = [
        screen("Claim legal notice", "//app#/LegalNotice"),
        screen("Claim photo upload", "//app#/Photos"),
        screen("Resume claim", "//app#/Resume"),
        screen("Resume claim report", "//app#/Resume"),  # one address, two screens
    ]
    walked = {"//app#/ReportClaim", "//app#/Photos"}
    assert not reached_screen(screens, "Claim legal notice", walked)  # never got there
    assert reached_screen(screens, "Claim photo upload", walked)
    # Can't be told from the address: assume it may have (retry as before).
    assert reached_screen(screens, "Resume claim", walked)
    assert reached_screen(screens, "A screen not on the map", walked)
