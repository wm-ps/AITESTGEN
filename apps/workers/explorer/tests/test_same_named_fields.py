"""Fields that share a name (DenaliTestSeven's New Account: a header search
and three lookups, all "Search field", under Territory / Primary Contact /
Parent Account). Explorer used to type into whichever came first; now it
names them by caption, refuses a bare shared name, can point at one by its
number on a screenshot, and picks from a lookup that only answers typing."""

from explorer_worker.browser import Eyes, locate
from explorer_worker.repair import numbered

LOOKUP = """
<div>{caption}</div>
<div class="lookup">
  <input aria-label="Search field" placeholder="Search {what}..." aria-autocomplete="list"
         data-items="{items}">
  <ul class="dropdown-menu"></ul>
</div>
"""
# Suggestions appear only while typing, and picking one fills the box.
SCRIPT = """<script>
for (const box of document.querySelectorAll('input[data-items]')) {
  const list = box.nextElementSibling;
  box.addEventListener('input', () => {
    const typed = box.value.toLowerCase();
    list.innerHTML = '';
    if (!typed) return;
    for (const item of box.dataset.items.split('|')) {
      if (!item.toLowerCase().includes(typed)) continue;
      const li = document.createElement('li');
      li.textContent = item;
      li.onclick = () => { box.value = item; box.dataset.picked = item; list.innerHTML = ''; };
      list.append(li);
    }
  });
}
</script>"""
PAGE = (
    '<header><span>CRM</span><input aria-label="Search field" placeholder="Search contacts"></header>'
    + LOOKUP.format(caption="Territory", what="territory", items="Pacific Northwest|Gulf Coast")
    + LOOKUP.format(caption="Primary Contact *", what="contact", items="Ana Ruiz|Ben Ode")
    + LOOKUP.format(caption="Parent Account", what="account", items="Northstar Industrial|Acme")
    + SCRIPT
)


async def _picked(eyes: Eyes, what: str) -> str | None:
    assert eyes.page is not None
    return await eyes.page.locator(f'input[placeholder="Search {what}..."]').get_attribute(
        "data-picked"
    )


async def test_shared_names_are_told_apart_by_caption() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        visit = await eyes.look(eyes.page.url, None, 0)
        assert visit.inventory["same_named_fields"] == [
            "Search field (CRM)",
            "Search field (Territory)",
            "Search field (Primary Contact)",
            "Search field (Parent Account)",
        ]

        # A bare shared name is refused, saying which ones there are.
        assert not await eyes.fill_field("Search field", "Pac")
        assert eyes.last_ambiguity and "Parent Account" in eyes.last_ambiguity

        # Named by caption: that very lookup, and its suggestion is picked.
        assert await eyes.fill_field("Search field (Parent Account)", "North")
        assert eyes.last_suggestion == "Northstar Industrial"
        assert await _picked(eyes, "account") == "Northstar Industrial"
        # The recorded locator finds the same box without Explorer's numbers.
        spec = eyes.last_locator
        assert spec is not None
        await eyes.page.evaluate(
            "() => document.querySelectorAll('[data-explorer-mark]')"
            ".forEach(e => e.removeAttribute('data-explorer-mark'))"
        )
        box = locate(eyes.page, spec).filter(visible=True).first
        assert await box.get_attribute("placeholder") == "Search account..."

        # Choosing in a lookup that shows nothing until you type.
        assert await eyes.choose("Search field (Territory)", "Pacific Northwest")
        assert eyes.last_lookup is not None and eyes.last_lookup[1] == "Pacific Northwest"
        assert await _picked(eyes, "territory") == "Pacific Northwest"
        assert not await eyes.choose("Search field", "Ana Ruiz")
        assert eyes.last_ambiguity
    finally:
        await eyes.close()


async def test_a_control_is_picked_by_its_number_on_the_screenshot() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        shot, marks = await eyes.marked_shot()
        assert shot[:2] == b"\xff\xd8"  # a JPEG, the overlay already gone again
        assert not await eyes.page.locator("#__explorer_marks").count()
        listed = numbered(marks)
        contact = next(m for m in marks if m.get("caption") == "Primary Contact")
        assert f"#{contact['n']} input “Search field”" in listed and "after “Primary Contact”" in listed

        spec = await eyes.stable_spec(contact)
        assert spec is not None
        step = await eyes.do_repair({"do": "keys", "target": f"#{contact['n']}", "text": "Ben"}, spec)
        assert step and step["locator"] == spec and step["suggest"] == "Ben Ode"
        assert await _picked(eyes, "contact") == "Ben Ode"
    finally:
        await eyes.close()
