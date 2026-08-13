"""`generation_worker.locator_grounding` — deterministic (non-LLM) check that
every locator the LLM wrote in a generated Playwright spec is actually backed
by real discovery-captured DOM data, not invented. Pure unit tests — no
Postgres/Chromium needed; `GroundingContext` is built by hand or via
`build_grounding_context` from a plain `known_locators` list, matching exactly
what `generation_worker.activities` already passes to `HostedAIProvider.
generate_playwright`.
"""

from generation_worker.locator_grounding import (
    FillFieldMeta,
    GroundingContext,
    build_grounding_context,
    find_ungrounded_locators,
    format_feedback,
)


def _context(**overrides) -> GroundingContext:
    defaults = dict(
        locator_values=frozenset(),
        label_values=frozenset(),
        role_name_pairs=frozenset(),
        fill_field_metadata=(),
    )
    defaults.update(overrides)
    return GroundingContext(**defaults)


def test_empty_context_short_circuits_to_no_violations() -> None:
    """A Journey with nothing captured at all has nothing to ground against
    — flagging every locator in that case would make every such Scenario
    permanently ungenerateable, not more correct."""
    code = "await page.locator('#totally-invented').click();"
    assert find_ungrounded_locators(code, _context()) == []


def test_verbatim_real_locator_is_grounded() -> None:
    context = _context(locator_values=frozenset({'[data-testid="save"]'}))
    code = 'const btn = page.locator(\'[data-testid="save"]\');'
    assert find_ungrounded_locators(code, context) == []


def test_invented_locator_not_in_captured_data_is_a_violation() -> None:
    context = _context(locator_values=frozenset({'[data-testid="save"]'}))
    code = "const btn = page.locator('#totally-invented');"
    violations = find_ungrounded_locators(code, context)
    assert len(violations) == 1
    assert violations[0].locator_text == "#totally-invented"
    assert violations[0].suggested_alternative == '[data-testid="save"]'


def test_comma_combined_selector_is_split_and_checked_per_branch() -> None:
    """The exact `'input[name="x"], input[type="y"]'` pattern the prompt
    itself asks for — grounded only if every branch resolves independently."""
    context = _context(fill_field_metadata=(FillFieldMeta(name="password", input_type="password"),))
    grounded_code = (
        "const f = page.locator('input[name=\"password\"], input[type=\"password\"]');"
    )
    assert find_ungrounded_locators(grounded_code, context) == []

    partially_invented_code = (
        "const f = page.locator('input[name=\"password\"], input[name=\"totally-invented\"]');"
    )
    violations = find_ungrounded_locators(partially_invented_code, context)
    assert len(violations) == 1


def test_derived_css_attribute_from_real_form_field_is_grounded() -> None:
    """`input[name="username"]` is grounded when a real captured form field
    named "username" exists — even though that exact selector string was
    never itself a captured `ComponentLocator.value` (the LLM built it
    itself, correctly, from real metadata)."""
    context = _context(fill_field_metadata=(FillFieldMeta(name="username", input_type="text"),))
    for selector in (
        'input[name="username"]',
        'input[type="text"]',
        'input[type="text"][name="username"]',
        'input[name="username"][type="text"]',
    ):
        code = f"const f = page.locator('{selector}');"
        assert find_ungrounded_locators(code, context) == [], selector


def test_derived_css_attribute_not_backed_by_any_real_field_is_a_violation() -> None:
    context = _context(fill_field_metadata=(FillFieldMeta(name="username", input_type="text"),))
    code = 'const f = page.locator(\'input[name="totally-invented"]\');'
    violations = find_ungrounded_locators(code, context)
    assert len(violations) == 1


def test_field_name_sentinel_is_excluded_from_derived_grounding() -> None:
    """model_builder._get_or_create_component's null-sentinel ("field") for a
    captured FormField with no real `name` must never accidentally ground a
    coincidental literal `input[name="field"]`. The exclusion lives in
    `build_grounding_context` (the sentinel is a `known_locators`-shape
    concept, not something `find_ungrounded_locators` itself knows about) —
    so this must go through that builder, not construct a `GroundingContext`
    by hand."""
    known_locators = [
        {
            "stage_label": "Checkout",
            "component_type": "text",
            "component_name": "field",  # the null-sentinel itself
            "selector": "#some-fallback",
            "strategy": "id",
        }
    ]
    context = build_grounding_context(known_locators)
    assert not context.fill_field_metadata

    code = 'const f = page.locator(\'input[name="field"]\');'
    violations = find_ungrounded_locators(code, context)
    # `context` also carries the sentinel's own `#some-fallback` locator_value
    # (the verbatim entry is still real, only the *derivation* is excluded),
    # so `context.is_empty` is False and the check genuinely runs.
    assert len(violations) == 1


def test_getbylabel_checked_against_label_values_not_general_locator_values() -> None:
    context = _context(
        locator_values=frozenset({'[data-testid="save"]'}),
        label_values=frozenset({"Username"}),
    )
    assert find_ungrounded_locators("page.getByLabel('Username');", context) == []
    violations = find_ungrounded_locators("page.getByLabel('Totally Invented Label');", context)
    assert len(violations) == 1
    # The real captured label is suggested — never a general locator value,
    # which would render as an invalid `getByLabel(...)` argument.
    assert violations[0].suggested_alternative == "Username"


def test_getbyrole_grounded_by_exact_or_partial_case_insensitive_match() -> None:
    context = _context(role_name_pairs=frozenset({("button", "save")}))
    assert find_ungrounded_locators("page.getByRole('button', { name: 'Save' });", context) == []
    assert find_ungrounded_locators("page.getByRole('button', { name: 'SAVE' });", context) == []
    # Partial/regex match legitimizes the multi-fragment accessible-name rule
    # (an icon/price/chevron-decorated real name) — the given text need only
    # be a substring of the real captured accessible name.
    context2 = _context(role_name_pairs=frozenset({("link", "health plan from ₹12,500/yr")}))
    assert find_ungrounded_locators(
        "page.getByRole('link', { name: /Health Plan/i });", context2
    ) == []


def test_getbyrole_with_unmatched_role_or_name_is_a_violation() -> None:
    context = _context(role_name_pairs=frozenset({("button", "save")}))
    violations = find_ungrounded_locators(
        "page.getByRole('button', { name: 'Totally Invented' });", context
    )
    assert len(violations) == 1


def test_template_literal_with_interpolation_is_skipped_not_flagged() -> None:
    """A computed selector built from a runtime variable is unresolvable
    statically — this is a documented, accepted gap, not a false positive."""
    context = _context(locator_values=frozenset())
    code = "const f = page.locator(`#item-${id}`);"
    assert find_ungrounded_locators(code, context) == []


def test_get_by_text_and_placeholder_are_never_flagged() -> None:
    """No captured-data set exists for arbitrary assertion/placeholder text —
    the prompt legitimately allows these when taken verbatim from Test data/
    Expected result, so flagging them would only produce unfixable
    false-positive violations."""
    context = _context(locator_values=frozenset({'[data-testid="save"]'}))
    code = (
        "page.getByText('Order confirmed');\n"
        "page.getByPlaceholder('Search products');\n"
    )
    assert find_ungrounded_locators(code, context) == []


def test_resolve_unique_and_click_when_ready_helper_calls_are_checked() -> None:
    """The prompt now routes CSS-attribute selectors through `resolveUnique`/
    `clickWhenReady` instead of a bare `.locator(...).first()` — the selector
    argument there is a plain function argument, not a `.locator(` call, and
    must still be grounded."""
    context = _context(fill_field_metadata=(FillFieldMeta(name="password", input_type="password"),))
    grounded = (
        "const f = await resolveUnique(page, 'input[name=\"password\"]', 'password field');"
    )
    assert find_ungrounded_locators(grounded, context) == []

    ungrounded = "await clickWhenReady(page, '#invented-submit', 'submit button');"
    violations = find_ungrounded_locators(ungrounded, context)
    assert len(violations) == 1


def test_build_grounding_context_from_known_locators_list() -> None:
    """Mirrors exactly the shape `generation_worker.activities.
    _resolve_known_application_model_sync` already builds for the AI prompt —
    no new query, no new shape."""
    known_locators = [
        {
            "stage_label": "Login",
            "component_type": "text",
            "component_name": "username",
            "selector": '[name="username"]',
            "strategy": "name",
        },
        {
            "stage_label": "Login",
            "component_type": "button",
            "component_name": "Login button",
            "selector": 'role=button[name="Login"]',
            "strategy": "aria",
        },
        {
            "stage_label": "Login",
            "component_type": "text",
            "component_name": "Remember me",
            "selector": "Remember me",
            "strategy": "label",
        },
        {
            "stage_label": "Login",
            "component_type": "text",
            "component_name": "field",  # null-sentinel — must be excluded
            "selector": "#some-fallback",
            "strategy": "id",
        },
    ]

    context = build_grounding_context(known_locators)

    assert '[name="username"]' in context.locator_values
    assert 'role=button[name="Login"]' in context.locator_values
    assert "Remember me" in context.label_values
    assert "Remember me" not in context.locator_values
    assert ("button", "login") in context.role_name_pairs
    assert FillFieldMeta(name="username", input_type="text") in context.fill_field_metadata
    assert not any(f.name == "field" for f in context.fill_field_metadata)


def test_build_grounding_context_from_empty_known_locators_is_empty() -> None:
    context = build_grounding_context(None)
    assert context.is_empty
    context2 = build_grounding_context([])
    assert context2.is_empty


def test_format_feedback_names_the_offending_locator_and_a_real_alternative() -> None:
    context = _context(locator_values=frozenset({'[data-testid="save"]'}))
    violations = find_ungrounded_locators("page.locator('#invented');", context)
    feedback = format_feedback(violations)
    assert "#invented" in feedback
    assert '[data-testid="save"]' in feedback
