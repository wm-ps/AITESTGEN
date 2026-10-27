"""Recorded locators (browser.locate / testkit.ts_locator): the exported test
uses exactly the locator Explorer used, for any app — the generic cure for
cards with split text, placeholder-named fields and styled checkboxes."""

import asyncio

import pytest
from explorer_worker.testkit import playwright_code, ts_locator
from playwright_typecheck.typecheck import typecheck_playwright_code

CARD = {"by": "role", "role": "checkbox", "name": "Property Property such as a house", "exact": True}
PLACEHOLDER = {"by": "placeholder", "text": "Enter full name"}
STYLED_BOX = {"by": "role", "role": "checkbox", "name": "Rear", "exact": True}


def test_each_recorded_locator_becomes_the_same_playwright_call() -> None:
    assert ts_locator(CARD) == (
        "page.getByRole(\"checkbox\", { name: \"Property Property such as a house\", "
        "exact: true }).filter({ visible: true }).first()"
    )
    assert ts_locator(PLACEHOLDER) == (
        "page.getByPlaceholder(\"Enter full name\").filter({ visible: true }).first()"
    )
    assert ts_locator({"by": "text", "text": "Continue", "exact": False}).startswith(
        "page.getByText(\"Continue\", { exact: false })"
    )
    with pytest.raises(ValueError):
        ts_locator({"by": "nonsense"})


SCRIPT = [
    {"do": "goto", "url": "https://app.example/#/Home"},
    {"do": "choose", "field": "Kind of claim", "option": "Property Property such as a house",
     "locator": CARD},
    {"do": "fill", "field": "Enter full name", "value": "Ada Lovelace", "locator": PLACEHOLDER},
    {"do": "choose", "field": "Which parts are damaged?", "option": "Rear", "locator": STYLED_BOX},
    {"do": "click", "label": "Continue",
     "locator": {"by": "role", "role": "button", "name": "Continue", "exact": True}},
]


def test_exported_code_uses_the_recorded_locators_and_compiles() -> None:
    code = playwright_code("Claim with a person", [], SCRIPT, {"kind": "text_visible", "value": "Done"}, "e")
    # The element Explorer used, not a re-guess from its words:
    assert "getByRole(\"checkbox\", { name: \"Property Property such as a house\"" in code
    assert "getByPlaceholder(\"Enter full name\")" in code
    assert "getByText(\"Rear\", { exact: true })" not in code  # the old, intercepted click
    assert "getByLabel(\"Enter full name\")" not in code
    assert asyncio.run(typecheck_playwright_code(code)) == []
