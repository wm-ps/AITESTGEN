"""The scope is counted field by field (scope.field_units): every required
field, dropdown and number/date field of a form needs its own test, a field
rule is never left out as a "duplicate", and what is missing is written by
name. Modelled on a real authoring run that lost 13 of a form's checks."""

from typing import Any

import pytest
from explorer_worker import scope
from explorer_worker.field_checks import FIELD_CHECK, field_checks
from explorer_worker.tests_stage import left_out

FORM = {
    "name": "New Territory form",
    "kind": "form",
    "fields": [
        {"label": "Search field", "type": "text"},  # the header's global search
        {"label": "Territory Name", "type": "text", "required": True},
        {"label": "Type", "type": "select", "required": True},
        {"label": "Region", "type": "select", "required": True},
        {"label": "Director", "type": "select", "required": True},
        {"label": "Quota Target", "type": "number", "required": True},
        {"label": "Expected Reps", "type": "number"},
        {"label": "Reps", "type": "text"},
        {"label": "Start Date", "type": "date"},
    ],
}
S = "New Territory form"


def t(title: str, coverage: str, **more: Any) -> dict[str, Any]:
    # A one-step path on the form: grounded, as the planner writes it.
    return {
        "title": title,
        "coverage": coverage,
        "start_screen": S,
        "path": [{"screen": S}],
        **more,
    }


def test_each_field_is_its_own_scope_item_from_what_the_form_has() -> None:
    units = {(u["id"], u["field"]) for u in scope.field_units([FORM])}
    assert units == {
        ("F-05", None),  # the empty form
        ("F-05", "Territory Name"),
        ("F-05", "Type"),
        ("F-05", "Region"),
        ("F-05", "Director"),
        ("F-05", "Quota Target"),
        ("F-03", "Type"),
        ("F-03", "Region"),
        ("F-03", "Director"),
        ("F-09", "Quota Target"),
        ("F-09", "Expected Reps"),
        ("F-06", "Start Date"),
    }
    # Sign-in and settings screens are planned elsewhere.
    assert scope.field_units([{**FORM, "kind": "login"}]) == []


def test_a_field_counts_as_covered_only_by_a_test_naming_it() -> None:
    units = scope.field_units([FORM])
    planned = field_checks([FORM]) + [
        t("Type offers all territory types", "F-03 Dropdown options"),
        t("Region offers all supported regions", "F-03 Dropdown options"),
        t("Expected Reps refuses a negative count", "F-09 Range"),
        t("Quota Target refuses a negative amount", "F-09 Range"),
    ]
    missing = {(u["id"], u["field"]) for u in scope.uncovered(units, planned)}
    # A required check doesn't cover a range item, nor a range check a required one.
    quota = [x for x in planned if x["title"].startswith("Quota Target is required")]
    assert {(u["id"], u["field"]) for u in units if u["field"] == "Quota Target"} - {
        (u["id"], u["field"]) for u in scope.uncovered(units, quota)
    } == {("F-05", "Quota Target")}
    # "Expected Reps" is not "Reps"; "types" is not the field "Type"'s test twice.
    assert missing == {("F-03", "Director"), ("F-06", "Start Date")}


def test_field_rules_and_a_fields_only_test_are_never_left_out() -> None:
    units = scope.field_units([FORM])
    checks = field_checks([FORM])
    planned = checks + [
        t("Director offers its options", "F-03 Dropdown options"),
        t("Director lists its directors", "F-03 Dropdown options"),
    ]
    # What a real check said: every required field "duplicates" the empty form,
    # and both Director tests went (each as a duplicate of the other).
    leave = {c["title"]: "duplicate of Empty New Territory form can't be saved" for c in checks}
    leave |= {"Director offers its options": "dup", "Director lists its directors": "dup"}
    kept = scope.keep_needed(planned, leave, units)
    assert kept == {"Director lists its directors": "dup"}  # one Director test stays


def test_the_plan_review_never_leaves_out_a_field_rule() -> None:
    planned = [
        t("Empty New Territory form can't be saved", FIELD_CHECK),
        t("Type is required on New Territory form", FIELD_CHECK),
        t("Region is required", "F-05 Required fields"),
        t("Other", "F-17 Cancel"),
        t("Other 2", "F-17 Cancel"),
        t("Other 3", "F-17 Cancel"),
    ]
    out = left_out(
        planned,
        [{"index": 1, "why": "duplicate", "of": 0}, {"index": 2, "why": "duplicate", "of": 0}],
    )
    assert list(out) == [2]  # the planner's own copy may go; the recorded rule stays


async def test_missing_fields_are_written_by_name_and_reported_field_by_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check(*_a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        # The model says dropdowns are covered and wants the field rules gone.
        rows = [
            {"screen": S, "id": "F-03", "status": "covered", "tests": ["Type offers…"]},
            {"screen": S, "id": "F-17", "status": "covered", "tests": ["Cancel"]},
        ]
        return rows, {"Type is required on New Territory form": "duplicate of the empty form"}

    asked: list[str] = []

    async def write(instruction: str, only: list[str]) -> list[dict[str, Any]]:
        asked.append(instruction)
        return [
            t("Director offers its options", "F-03 Dropdown options"),
            t("Expected Reps refuses a negative count", "F-09 Range"),
            t("Start Date refuses an impossible date", "F-06 Invalid format"),
        ]

    monkeypatch.setattr(scope, "check_scope", check)
    events: list[tuple[str, str]] = []
    journal = type("J", (), {"event": lambda self, k, t, d=None: events.append((t, d or ""))})()
    planned = field_checks([FORM]) + [
        t("Type offers all territory types", "F-03 Dropdown options"),
        t("Region offers all supported regions", "F-03 Dropdown options"),
        t("Quota Target refuses a negative amount", "F-09 Range"),
        t("Cancel saves nothing", "F-17 Cancel"),
    ]
    tests = await scope.cover(journal, [FORM], planned, write)  # type: ignore[arg-type]
    titles = [x["title"] for x in tests]
    assert "Type is required on New Territory form" in titles  # not left out
    assert (
        "Director offers its options" in titles
        and "Start Date refuses an impossible date" in titles
    )
    # The gaps were asked for by field name, once.
    assert len(asked) == 1
    for field in ("— Director", "— Expected Reps", "— Start Date"):
        assert field in asked[0]
    headline, detail = events[-1]
    assert "still missing" not in headline
    assert "✓ F-03 Dropdown options — Director — Director offers its options" in detail
    assert "✓ F-05 Required fields — Type — Type is required on New Territory form" in detail
