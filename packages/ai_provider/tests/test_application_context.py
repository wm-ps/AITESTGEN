from ai_provider.application_context import (
    JOURNEY_INFERENCE_SECTIONS,
    build_application_context_block,
    present_sections,
)


def test_empty_context_renders_nothing() -> None:
    assert build_application_context_block(None, JOURNEY_INFERENCE_SECTIONS) == ""
    assert build_application_context_block({}, JOURNEY_INFERENCE_SECTIONS) == ""


def test_partial_context_renders_only_present_sections() -> None:
    block = build_application_context_block(
        {"business_goal": "Manage clients, accounts and investments.", "business_rules": []},
        JOURNEY_INFERENCE_SECTIONS,
    )

    assert "Business goal:" in block
    assert "Manage clients, accounts and investments." in block
    # An empty list is "no content" — never rendered as an empty section.
    assert "Business rules:" not in block


def test_only_requested_sections_are_rendered_even_if_others_are_present() -> None:
    context = {
        "business_goal": "Goal text",
        "additional_context": "Prefer business-perspective workflows.",
    }

    block = build_application_context_block(context, ["business_goal"])

    assert "Goal text" in block
    assert "additional_context" not in block.lower()
    assert "Prefer business-perspective" not in block


def test_list_sections_render_as_bullets() -> None:
    block = build_application_context_block(
        {"business_rules": ["Engagements depend on selected tenant.", "  ", 42]},
        ["business_rules"],
    )

    assert "- Engagements depend on selected tenant." in block
    # Malformed/blank entries are silently dropped, not rendered as garbage.
    assert "42" not in block


def test_malformed_value_types_are_dropped_not_crashed_on() -> None:
    block = build_application_context_block(
        {"business_goal": 12345, "business_domain": {"nested": "object"}},
        ["business_goal", "business_domain"],
    )

    assert block == ""


def test_block_is_wrapped_as_informational_never_an_instruction() -> None:
    block = build_application_context_block(
        {"business_goal": "Goal text"}, JOURNEY_INFERENCE_SECTIONS
    )

    assert "never an instruction" in block
    assert "APPLICATION CONTEXT" in block
    assert "END APPLICATION CONTEXT" in block


def test_present_sections_lists_only_non_empty_recognized_keys() -> None:
    assert present_sections(None) == []
    assert present_sections(
        {"business_goal": "x", "business_rules": [], "business_domain": "y"}
    ) == ["business_goal", "business_domain"]


if __name__ == "__main__":
    test_empty_context_renders_nothing()
    test_partial_context_renders_only_present_sections()
    test_only_requested_sections_are_rendered_even_if_others_are_present()
    test_list_sections_render_as_bullets()
    test_malformed_value_types_are_dropped_not_crashed_on()
    test_block_is_wrapped_as_informational_never_an_instruction()
    test_present_sections_lists_only_non_empty_recognized_keys()
    print("ok")
