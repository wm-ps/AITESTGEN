"""Explorer's recorded actions reach Vantage's generator in its own
live-flow shape (promote.captured_flow)."""

from explorer_worker.promote import _proof_sentence, captured_flow


def test_recorded_actions_become_generator_steps() -> None:
    flow = captured_flow(
        [
            {"do": "goto", "url": "https://app/#/start"},
            {"do": "fill", "field": "Policy number", "value": "P-1"},
            {"do": "choose", "field": "Hurt?", "option": "No one was hurt"},
            {"do": "click", "label": "Continue"},
        ]
    )
    assert [s["tool_name"] for s in flow] == [
        "browser_navigate",
        "browser_type",
        "browser_click",
        "browser_click",
    ]
    assert flow[1]["value"] == 'get_by_label("Policy number")'
    assert flow[1]["semantic_target"]["value"] == "P-1"
    assert flow[2]["value"] == 'get_by_text("No one was hurt", exact=True)'
    assert flow[3]["value"] == 'get_by_role("button", name="Continue")'
    assert all(s["value"] for s in flow)  # the generator drops steps without one


def test_proof_sentence() -> None:
    assert (
        _proof_sentence({"kind": "text_visible", "value": "Saved"})
        == " Proof of success: the screen shows “Saved”."
    )
    assert _proof_sentence(None) == ""
