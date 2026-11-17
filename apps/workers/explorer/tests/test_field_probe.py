"""A form that checks its fields in its own code (no required/maxlength on
the field) only says so once a value is wrong: Explorer provokes each
message, reads it under the field, and the field check expects it word for
word."""

from explorer_worker.browser import Eyes
from explorer_worker.field_checks import field_checks
from explorer_worker.field_probe import read_messages

# Messages appear only on blur, in the field's own wrapper; a counter is noise.
PAGE = """
<form>
  <div class="group"><label for="ln">Last Name</label><input id="ln">
    <small class="count"></small><span class="err"></span></div>
  <div class="group"><label for="em">Email</label><input id="em"><span class="err"></span></div>
</form>
<script>
  const rule = {
    ln: (v) => !v ? 'Last name is required' : v.length > 50 ? 'Maximum 50 characters' : '',
    em: (v) => v && !v.includes('@') ? 'Enter a valid email address' : '',
  };
  for (const id of ['ln', 'em']) {
    const box = document.getElementById(id);
    box.addEventListener('blur', () => {
      box.parentElement.querySelector('.err').textContent = rule[id](box.value);
      const count = box.parentElement.querySelector('.count');
      if (count) count.textContent = `${box.value.length} / 50`;
    });
  }
</script>
"""


async def test_messages_under_the_field_are_read_per_wrong_value() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        last = await read_messages(eyes, "Last Name", {"label": "Last Name", "type": "text"})
        email = await read_messages(eyes, "Email", {"label": "Email", "type": "email"})
    finally:
        await eyes.close()
    assert {m["probe"]: m["message"] for m in last} == {
        "required": "Last name is required",
        "long": "Maximum 50 characters",
    }
    # The email message belongs to the email check alone (not "too short" or
    # "wrong format"), and the other field's message is never taken.
    assert {m["probe"]: m["message"] for m in email} == {"email": "Enter a valid email address"}


def test_read_messages_become_field_checks_that_expect_them_word_for_word() -> None:
    form = {
        "name": "New Lead form",
        "kind": "form",
        "fields": [
            {
                "label": "Last Name",
                "maxlength": "80",  # the form's own message wins over the code limit
                "messages": [
                    {
                        "probe": "required",
                        "entered": "left empty",
                        "message": "Last name is required",
                    },
                    {
                        "probe": "long",
                        "entered": "300 characters",
                        "message": "Maximum 50 characters",
                    },
                ],
            },
            {"label": "Company", "required": True},
        ],
    }
    tests = {t["title"]: t for t in field_checks([form])}
    # Required because the form said so, though nothing marked it.
    assert "“Last name is required”" in tests["Last Name is required on New Lead form"]["expected"]
    long = tests["Last Name refuses too many characters on New Lead form"]
    assert "“Maximum 50 characters”" in long["expected"]
    assert "300 characters" in long["how_to_run"]
    assert "“Last name is required”" in tests["Empty New Lead form can't be saved"]["expected"]


async def test_probing_a_form_mid_walk_puts_back_what_was_typed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import uuid

    from explorer_worker import field_probe

    saved: dict[str, object] = {}
    monkeypatch.setattr(field_probe, "_save_messages", lambda _id, found: saved.update(found))
    events: list[str] = []
    journal = type("J", (), {"event": lambda self, kind, title, *a: events.append(title)})()
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        await eyes.page.fill("#ln", "Smith")  # the walk had typed this already
        read = await field_probe.probe_here(
            eyes,
            journal,  # type: ignore[arg-type]
            uuid.uuid4(),
            "New Lead form",
            [{"label": "Last Name", "type": "text"}, {"label": "Email", "type": "email"}],
            lambda: None,
        )
        assert await eyes.page.input_value("#ln") == "Smith"
        assert await eyes.page.input_value("#em") == ""
    finally:
        await eyes.close()
    assert read == 3 and set(saved) == {"Last Name", "Email"}
    assert events == ["Read 3 field message(s) on New Lead form"]


# The Opportunity form's shape: an Owner lookup (no ARIA, a `.dropdown-menu`
# of people), a <select>, and messages that appear only when Save is pressed.
SAVE_PAGE = """
<form onsubmit="return false">
  <div><label for="nm">Opportunity Name</label><input id="nm"><span class="err"></span></div>
  <div><label for="ow">Owner</label><input id="ow">
    <ul class="dropdown-menu" style="display:none"><li>Sam Reed</li><li>Megan Alvarez</li></ul>
    <span class="err"></span></div>
  <div><label for="st">Stage</label>
    <select id="st"><option></option><option>Qualification</option></select></div>
  <button id="save">Save Opportunity</button>
</form>
<script>
  const ow = document.getElementById('ow'), menu = document.querySelector('.dropdown-menu');
  ow.addEventListener('input', () => { menu.style.display = ow.value ? 'block' : 'none'; });
  for (const li of menu.children) li.onclick = () => { ow.value = li.textContent;
    menu.style.display = 'none'; };
  document.getElementById('save').onclick = () => {
    const nm = document.getElementById('nm').value;
    document.querySelector('#nm + .err').textContent =
      !nm ? 'Opportunity Name is required' : nm.length > 80 ? 'At most 80 characters' : '';
  };
</script>
"""


async def test_a_lookup_takes_a_suggestion_and_save_messages_are_read() -> None:
    from explorer_worker.field_probe import read_on_save

    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(SAVE_PAGE)
        # "SR" matches no one: a lookup still takes its first suggestion.
        assert await eyes.fill_field("Owner", "SR")
        assert await eyes.page.input_value("#ow") == "Sam Reed"
        assert await eyes.choose("Stage", "Qualification")
        fields = [
            {"label": "Opportunity Name", "type": "text"},
            {"label": "Owner", "type": "text"},  # a lookup: never probed
            {"label": "Search contacts", "type": "text"},
        ]
        assert await read_messages(eyes, "Owner", fields[1]) == []
        found, left = await read_on_save(eyes, fields)
    finally:
        await eyes.close()
    assert not left and set(found) == {"Opportunity Name"}
    assert {m["probe"]: m["message"] for m in found["Opportunity Name"]} == {
        "required": "Opportunity Name is required",
        "long": "At most 80 characters",
    }


# Territory's shape: Save shows one message above the form, naming the field.
TOP_PAGE = """
<div id="top" role="alert"></div>
<form onsubmit="return false">
  <label for="tn">Territory Name *</label><input id="tn">
  <button id="save">Save Territory</button>
</form>
<script>
  document.getElementById('save').onclick = () => {
    document.getElementById('top').textContent =
      document.getElementById('tn').value ? '' : 'Territory Name is required.';
  };
</script>
"""


async def test_a_message_at_the_top_of_the_form_belongs_to_the_field_it_names() -> None:
    from explorer_worker.field_probe import read_on_save

    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(TOP_PAGE)
        found, left = await read_on_save(eyes, [{"label": "Territory Name *", "type": "text"}])
    finally:
        await eyes.close()
    assert not left
    assert found["Territory Name *"][0] == {
        "probe": "required",
        "entered": "left empty",
        "message": "Territory Name is required.",
    }
