"""Generic route rules (sense.route_starts_at_entry / about_resuming): a test's
steps must start at an entry point and reach every inner page by the user's
own actions, so they replay in any clean browser, for any app."""

from explorer_worker.sense import about_resuming, route_starts_at_entry

APP = "https://shop.example/app/"
LANDED = "https://shop.example/app/#/Home"  # where sign-in landed
ENTRIES = {APP, LANDED}


def test_clicking_through_from_the_entry_is_a_valid_route() -> None:
    script = [
        {"do": "goto", "url": LANDED},
        {"do": "click", "label": "New order"},
        {"do": "fill", "field": "Email", "value": "a@b.co"},
        {"do": "click", "label": "Continue"},
    ]
    assert route_starts_at_entry(script, ENTRIES)
    # The app's start address with or without a trailing "#/" is the same entry.
    assert route_starts_at_entry([{"do": "goto", "url": APP + "#/"}], ENTRIES)


def test_opening_an_inner_page_by_address_is_never_a_valid_route() -> None:
    jump_midway = [
        {"do": "goto", "url": LANDED},
        {"do": "goto", "url": "https://shop.example/app/#/Checkout/Contact"},
        {"do": "fill", "field": "Mobile number", "value": "4155550101"},
    ]
    starts_inside = [{"do": "goto", "url": "https://shop.example/app/#/Checkout/Review"}]
    assert not route_starts_at_entry(jump_midway, ENTRIES)
    assert not route_starts_at_entry(starts_inside, ENTRIES)
    assert not route_starts_at_entry([{"do": "click", "label": "Go"}], ENTRIES)
    assert not route_starts_at_entry([], ENTRIES)


def test_only_resume_scenarios_keep_a_saved_draft() -> None:
    assert about_resuming("Pick up where I left off restores the saved claim")
    assert about_resuming("Save and exit keeps the answers for later")
    assert about_resuming("An unfinished order can be resumed")
    assert not about_resuming("Mobile number refuses fewer than 10 digits")
    assert not about_resuming("Property can be selected as the claim type")
