"""A "this screen opens" scenario (checklist F-01 / L-01 / P-01) is built
without the model (tests_stage.opens_check / heading_proof): the saved route
plus the screen's own heading as proof — then proven like any other."""

from explorer_worker.tests_stage import heading_proof, opens_check


def test_only_the_screen_opens_checklist_items_skip_the_model() -> None:
    assert opens_check({"coverage": "F-01 Form loads"})
    assert opens_check({"coverage": "L-01 Page loads"})
    assert opens_check({"coverage": "P-01 Page loads"})
    # Anything that judges data or behaviour still needs the model.
    assert not opens_check({"coverage": "F-02 Defaults"})
    assert not opens_check({"coverage": "L-03 Data matches the server"})
    assert not opens_check({"coverage": "F-010 Something"})
    assert not opens_check({"coverage": "X-Urgent injury guidance"})
    assert not opens_check({})


def test_the_proof_is_the_first_heading_that_stays_the_same_every_run() -> None:
    inventory = {"headings": ["Claim FNOL-W84R-7NRY", "  When did   it happen? ", "Other"]}
    assert heading_proof(inventory) == {"kind": "text_visible", "value": "When did it happen?"}
    assert heading_proof({"headings": ["Order 1042 created"]}) is None  # only changing text
    assert heading_proof({"headings": []}) is None
    assert heading_proof({}) is None


def test_a_screen_without_heading_tags_uses_its_page_title() -> None:
    styled = {"headings": [], "title": "When did it happen?"}
    assert heading_proof(styled) == {"kind": "text_visible", "value": "When did it happen?"}
    assert heading_proof({"headings": ["Your vehicle"], "title": "Claims"})["value"] == "Your vehicle"  # type: ignore[index]
