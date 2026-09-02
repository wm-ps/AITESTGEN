"""`_build_scenario_requirements` — Duplicate Prevention for the NLM "Add
Test Case" feature. Pure logic, no DB/AI needed (`identify_scenarios_activity`
itself is a thin I/O wrapper around this).

Regression test for a bug observed live: two separate NLM requests (not
concurrent — submitted minutes apart) each created their own "Calculate loan
EMI" Scenario, because `match_test_case_scenarios`' own semantic judgment on
`reuse_scenario` is best-effort and didn't recognize the second request as
matching the first request's already-created Scenario. An exact (normalized)
name match against any existing Scenario in the catalog must always win over
the AI's own `new_scenario`/`new_journey` choice, regardless of which Journey
it picked.
"""

from ai_provider.scenario_match_candidate import ScenarioMatchCandidate
from generation_worker.add_test_case_activities import _build_scenario_requirements

_EXISTING_LOAN_JOURNEY = {
    "journey_id": "journey-loans",
    "name": "Loan Management",
    "description": "",
    "scenarios": [
        {
            "scenario_id": "scenario-emi",
            "name": "Calculate loan EMI",
            "type": "happy",
            "expected_result": "the EMI amount is displayed",
        }
    ],
}


def test_exact_name_match_overrides_a_new_scenario_proposal_under_a_different_journey() -> None:
    # The AI proposed a brand-new Scenario under a *different* existing
    # Journey than the one "Calculate loan EMI" actually lives under — the
    # exact bug: its own semantic matching missed the existing Scenario
    # entirely, so it never even considered reusing it.
    other_journey = {
        "journey_id": "journey-accounts",
        "name": "Account Management",
        "description": "",
        "scenarios": [],
    }
    candidates = [
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-accounts",
            proposed_scenario_name="Calculate loan EMI",
            functionality_summary="Calculate the EMI for a loan",
        )
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY, other_journey])

    assert len(requirements) == 1
    assert requirements[0].mode == "reuse_scenario"
    assert requirements[0].journey_id == "journey-loans"
    assert requirements[0].scenario_id == "scenario-emi"


def test_exact_name_match_overrides_a_new_journey_proposal() -> None:
    candidates = [
        ScenarioMatchCandidate(
            mode="new_journey",
            proposed_journey_name="Loan Calculators",
            proposed_scenario_name="Calculate loan EMI",
            functionality_summary="Calculate the EMI for a loan",
        )
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert len(requirements) == 1
    assert requirements[0].mode == "reuse_scenario"
    assert requirements[0].journey_id == "journey-loans"
    assert requirements[0].scenario_id == "scenario-emi"


def test_name_match_is_case_and_punctuation_insensitive() -> None:
    candidates = [
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-loans",
            proposed_scenario_name="calculate LOAN emi!!",
        )
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert requirements[0].mode == "reuse_scenario"
    assert requirements[0].scenario_id == "scenario-emi"


def test_genuinely_different_name_is_not_deduped() -> None:
    candidates = [
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-loans",
            proposed_scenario_name="Apply for a home loan",
        )
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert requirements[0].mode == "new_scenario"
    assert requirements[0].scenario_id is None


def test_two_candidates_proposing_the_same_new_scenario_name_collapse_to_one() -> None:
    """Within-batch duplicate — a single prompt decomposed into two
    requirements that both propose the identical new Scenario name (neither
    matches an existing one) must not create two Scenarios."""
    candidates = [
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-loans",
            proposed_scenario_name="Apply for a loan",
        ),
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-loans",
            proposed_scenario_name="Apply for a loan",
        ),
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert len(requirements) == 1


def test_two_candidates_reusing_the_same_existing_scenario_collapse_to_one() -> None:
    candidates = [
        ScenarioMatchCandidate(
            mode="reuse_scenario", journey_id="journey-loans", scenario_id="scenario-emi"
        ),
        ScenarioMatchCandidate(
            mode="reuse_scenario", journey_id="journey-loans", scenario_id="scenario-emi"
        ),
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert len(requirements) == 1
    assert requirements[0].mode == "reuse_scenario"


def test_hallucinated_journey_id_falls_back_to_new_journey() -> None:
    candidates = [
        ScenarioMatchCandidate(
            mode="new_scenario",
            journey_id="journey-does-not-exist",
            proposed_scenario_name="Something new",
        )
    ]

    requirements = _build_scenario_requirements(candidates, [_EXISTING_LOAN_JOURNEY])

    assert requirements[0].mode == "new_journey"
    assert requirements[0].journey_id is None
