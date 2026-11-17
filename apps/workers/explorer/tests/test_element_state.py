"""State, not text, as a test's proof: a dropdown's options (drawn by the
browser outside any screenshot), a selected value, what a field holds — read
from the accessibility snapshot, for native and custom controls alike."""

from explorer_worker.browser import Eyes
from explorer_worker.testkit import (
    ground_state,
    holds,
    playwright_code,
    proving_lines,
    state_of_changed_list,
    state_of_last_entry,
)
from explorer_worker.tests_stage import proof_was_there_before

PAGE = """
<label for="ty">Type</label>
<select id="ty"><option>Geographic</option><option>Vertical</option><option>Named Account</option></select>
<span id="rl">Region</span>
<div role="combobox" aria-labelledby="rl" aria-expanded="false" tabindex="0">APAC</div>
<label for="nm">Name</label><input id="nm">
"""


async def test_a_dropdowns_options_are_proven_from_its_state() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        visit = await eyes.look(eyes.page.url, None, 0)
        # A control the app draws itself is a field too.
        assert {"label": "Region", "type": "combobox", "required": False} in visit.inventory[
            "fields"
        ]
        assert 'option "Vertical"' in visit.inventory["aria"]
        # The model's lines are checked against the element's real snapshot.
        check = await ground_state(
            eyes,
            {"kind": "element_state", "role": "combobox", "name": "Type", "value": "- option"},
        )
        assert check is not None and 'option "Named Account"' in check["value"]
        assert await holds(eyes, check, wait_ms=2000)
        assert not await holds(
            eyes, {**check, "value": '- combobox "Type":\n  - option "Mars"'}, 1000
        )
        assert await ground_state(eyes, {"role": "combobox", "name": "Nope", "value": "x"}) is None
        # Last resort: what the field the test typed in holds.
        await eyes.page.fill("#nm", "Pacific West")
        typed = [{"do": "fill", "field": "Name", "locator": {"by": "label", "text": "Name"}}]
        state = await state_of_last_entry(eyes, typed)
        assert state is not None and state["role"] == "textbox" and "Pacific West" in state["value"]
    finally:
        await eyes.close()
    # Not on the entry screen before the test: a real proof.
    assert not proof_was_there_before(check, "", "", None, '- heading "Home"')
    assert proof_was_there_before(check, "", "", None, visit.inventory["aria"])
    code = playwright_code("Type offers its choices", [], [], check, "x")
    assert (
        'getByRole("combobox", { name: "Type", exact: true }).first()).toMatchAriaSnapshot(' in code
    )


def test_a_long_snapshot_keeps_the_proving_lines_under_their_parents() -> None:
    rows = "\n".join(f'    - row "Territory {i}"' for i in range(80))
    actual = f'- table "Territories":\n  - rowgroup:\n{rows}'
    kept = proving_lines(actual, '- row "Territory 42"')
    assert kept.splitlines() == [
        '- table "Territories":',
        "  - rowgroup:",
        '    - row "Territory 42"',
    ]


LIST_PAGE = """
<div role="combobox" tabindex="0" id="st">All Statuses</div>
<table><thead><tr><th>Name</th><th>Status</th></tr></thead>
<tbody id="rows"><tr><td>Acme</td><td>Active</td></tr><tr><td>Bolt</td><td>Inactive</td></tr></tbody></table>
<script>
document.getElementById('st').onclick = () => {
  document.getElementById('st').textContent = 'Active';
  document.getElementById('rows').innerHTML = '<tr><td>Acme</td><td>Active</td></tr>';
};
</script>
"""


async def test_an_unnamed_dropdown_and_a_lists_rows_are_backup_proofs() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(LIST_PAGE)
        before = await eyes.page.locator("body").aria_snapshot()
        await eyes.page.click("#st")
        # The dropdown has no name: found again by the test's own locator.
        chose = [{"do": "choose", "locator": {"by": "css", "selector": "#st"}}]
        state = await state_of_last_entry(eyes, chose)
        assert state is not None and state["role"] == "combobox" and state["name"] == ""
        assert "Active" in state["value"] and await holds(eyes, state, wait_ms=2000)
        # The list: its rows that changed since the test started.
        rows = await state_of_changed_list(eyes, before)
        assert rows is not None and rows["role"] == "table"
        assert await holds(eyes, rows, wait_ms=2000)
        # A list that didn't change proves nothing.
        now = await eyes.page.locator("body").aria_snapshot()
        assert await state_of_changed_list(eyes, now) is None
    finally:
        await eyes.close()
    code = playwright_code("Filter to Active", [], [], rows, "x")
    assert 'page.getByRole("table").first()).toMatchAriaSnapshot(' in code
