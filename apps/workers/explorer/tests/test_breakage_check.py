"""The broken-on-purpose check (testkit.broken_variants) and proofs that
can't tell a test's outcome apart (tests_stage.proof_was_there_before)."""

from explorer_worker.testkit import broken_variants
from explorer_worker.tests_stage import proof_was_there_before

APP = "https://shop.example/app/"
ROUTE = [
    {"do": "goto", "url": APP},
    {"do": "fill", "field": "Policy number", "value": "POL-1"},
    {"do": "click", "label": "Find my policy"},
]


def test_inline_validation_is_caught_by_removing_the_bad_value() -> None:
    # "Mobile number refuses letters": the message shows on typing, so
    # removing the final Continue alone leaves it on screen.
    script = [
        *ROUTE,
        {"do": "fill", "field": "Mobile number", "value": "abc"},
        {"do": "click", "label": "Continue"},
    ]
    assert broken_variants(script, own_from=len(ROUTE)) == [
        script[:-1],  # without the last action, as before
        [*ROUTE, script[-1]],  # without the bad value
    ]


def test_route_steps_are_never_removed() -> None:
    # Only route steps entered something: a broken route would make any
    # proof vanish and prove nothing, so only the last action is tried.
    script = [*ROUTE, {"do": "click", "label": "Continue"}]
    assert broken_variants(script, own_from=len(ROUTE)) == [ROUTE]
    # Where the test's own steps begin is unknown: same.
    fill_last = [*ROUTE, {"do": "fill", "field": "Email", "value": "x"}]
    assert broken_variants(fill_last, own_from=None) == [ROUTE]
    assert broken_variants([{"do": "goto", "url": APP}], own_from=1) == []


def test_a_data_call_made_on_every_step_is_not_proof() -> None:
    saves = [("PATCH", "https://shop.example/api/Claim", 200)] * 3
    submit = [("POST", "https://shop.example/api/Claim/submit", 201)]
    patch = {"kind": "api_call", "value": "PATCH /api/Claim"}
    post = {"kind": "api_call", "value": "POST /api/Claim/submit"}
    assert proof_was_there_before(patch, "", APP, saves + submit)
    assert not proof_was_there_before(post, "", APP, saves + submit)
    assert not proof_was_there_before(patch, "", APP, saves[:1])
