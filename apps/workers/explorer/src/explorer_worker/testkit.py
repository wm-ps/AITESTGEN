"""Replaying a test's recorded actions without the model, checking its
proof, and exporting it as a Playwright test (Stage 5, PLAN.md §6 / D1)."""

import base64
import json
import mimetypes
import re
from typing import Any

from playwright.async_api import expect

from explorer_worker.browser import (
    _CALENDAR_JS,
    _DOM_QUIET_JS,
    PRESS_WAIT_MS,
    SUGGESTIONS,
    Eyes,
    field_after_caption,
    locate,
)
from explorer_worker.samples import file_names, padding, sample_file, sample_files, upload_shape
from explorer_worker.sense import (
    CONTINUE_LIKE,
    DISMISS_LIKE,
    RESUME_LABEL,
    START_FRESH,
    looks_final,
    resolve_relative,
    resumes_saved_progress,
)

MAX_DETOURS = 3

# Apps that save drafts can bring back boxes ticked by an earlier session.
# Before moving a step on (Continue/Next), untick every box the test didn't
# choose on that screen, so "nothing selected" tests mean what they say.
# The same text runs in Explorer's replay and in the exported test.
UNTICK_UNCHOSEN_JS = r"""(keep) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const nameOf = (b) => norm((b.labels && b.labels[0] && b.labels[0].innerText)
    || (b.closest('label') && b.closest('label').innerText) || b.getAttribute('aria-label'));
  const wanted = keep.map(norm);
  let unticked = 0;
  for (const box of document.querySelectorAll('input[type=checkbox]')) {
    if (!box.checked || box.disabled) continue;
    const name = nameOf(box);
    if (!name || wanted.some((k) => name.includes(k) || k.includes(name))) continue;
    box.click();
    unticked += 1;
  }
  return unticked;
}"""


def chosen_on_screen(script: list[dict[str, Any]], i: int) -> list[str]:
    """The options the test chose since its previous click (= on this screen)."""
    chosen: list[str] = []
    for step in reversed(script[:i]):
        if step.get("do") in ("click", "goto"):
            break
        if step.get("do") == "choose":
            chosen.append(str(step.get("option") or ""))
    return chosen


def advances_step(step: dict[str, Any]) -> bool:
    label = str(step.get("label") or "")
    return (
        step.get("do") == "click"
        and bool(CONTINUE_LIKE.match(label))
        and not DISMISS_LIKE.match(label)
    )


async def replay(eyes: Eyes, script: list[dict[str, Any]], failed: list[str] | None = None) -> bool:
    """Run every recorded action. False as soon as one can't be done (and
    the step that couldn't is appended to `failed`).

    Apps that remember earlier sessions don't always show the same screens:
    a step the app skipped this time (already answered in a saved draft) is
    marked optional when the step after it is already on screen, and an
    in-between screen the recording didn't have ("you already reported
    something similar") is pressed past with its continue-style button and
    added as an optional step. Both are written into `script` itself, so the
    exported test handles them too."""
    assert eyes.page is not None
    eyes.mark_calls()  # an API proof counts only this replay's calls
    fresh = not resumes_saved_progress(script)
    if fresh:
        await eyes.start_fresh_on_resume_prompts()
    detours = 0
    i = 0
    while i < len(script):
        step = script[i]
        if fresh and _starts_fresh(step):
            # The prompt may or may not show this time: press it when it
            # does (the handler may not recognise every wording), skip it
            # when it doesn't.
            before = await eyes.fingerprint()
            if await eyes.click_text(str(step.get("label") or ""), "button"):
                await eyes.wait_for_change(before, 8000)
            i += 1
            continue
        if fresh:
            await eyes.start_fresh_if_asked()
        if advances_step(step):
            try:
                await eyes.page.evaluate(UNTICK_UNCHOSEN_JS, chosen_on_screen(script, i))
            except Exception:  # noqa: BLE001 — a page mid-navigation; the click decides
                pass
        if await _do(eyes, step) or step.get("optional"):
            i += 1
            continue
        following = next((s for s in script[i + 1 :] if s.get("do") != "goto"), None)
        if following is not None and await eyes.present(following):
            step["optional"] = True  # this screen was skipped this time
            i += 1
            continue
        if detours < MAX_DETOURS:
            label = await eyes.press_continue_like()
            if label:
                detours += 1
                script.insert(i, {"do": "click", "label": label, "optional": True})
                i += 1  # then try the same step again
                continue
        if failed is not None:
            failed.append(describe(step))
        return False
    return True


async def _do(eyes: Eyes, step: dict[str, Any]) -> bool:
    assert eyes.page is not None
    action = step.get("do")
    if action == "goto":
        # Leave the page first: re-opening the same single-page-app
        # address doesn't reload it, and leftovers from the previous run
        # (an error message, typed values) would fake the result.
        await eyes.page.goto("about:blank")
        await eyes.goto(str(step["url"]))
        return True
    # A recorded locator is used as-is: the replay proves the very locator
    # the exported test will use (ts_locator), not a fresh guess.
    spec = step.get("locator")
    if action == "fill" and step.get("keys") and spec:
        # A field that reacts to each key (a mask, a suggestion list): typed
        # one character at a time, as the repair that made it work did.
        typed = {"do": "keys", "target": "", "text": str(step["value"])}
        return await eyes.do_repair(typed, spec) is not None
    if action == "fill":
        return await eyes.fill_field(str(step["field"]), str(step["value"]), spec=spec)
    if action == "key":
        pressed = {"do": "key", "key": str(step.get("key") or "")}
        return await eyes.do_repair(pressed, spec) is not None
    if action == "wait":
        await eyes.page.wait_for_timeout(max(0, min(int(step.get("ms") or 0), 5000)))
        return True
    if action == "choose":
        return await eyes.choose(str(step.get("field") or ""), str(step["option"]), spec=spec)
    if action == "click":
        before = await eyes.fingerprint()
        ok = await eyes.click_text(str(step["label"]), "button", spec=spec, wait_ms=PRESS_WAIT_MS)
        if ok and spec and eyes.last_locator and eyes.last_locator != spec:
            # Found another way (the page changed its markup): the step and
            # the exported test use the locator that works now.
            step["locator"] = dict(eyes.last_locator)
        if ok:
            await eyes.wait_for_change(before, 8000)
        return ok
    if action == "upload":
        paths = sample_files(str(step.get("kind") or "image"), *upload_shape(step))
        return await eyes.upload_file(str(step.get("field") or ""), [str(p) for p in paths])
    if action in ("back", "reload", "fail_next_save"):
        return await eyes.browser(str(action))
    return False


def _starts_fresh(step: dict[str, Any]) -> bool:
    return step.get("do") == "click" and bool(START_FRESH.search(str(step.get("label") or "")))


def describe(step: dict[str, Any]) -> str:
    action = step.get("do")
    if action == "fill":
        return f"typing into “{step.get('field')}”"
    if action == "choose":
        return f"choosing “{step.get('option')}”"
    if action == "click":
        return f"pressing “{step.get('label')}”"
    if action == "upload":
        count, size_mb = upload_shape(step)
        what = f"{count} {step.get('kind') or 'image'} files" if count > 1 else (
            f"a {step.get('kind') or 'image'} file"
        )
        return f"attaching {what}" + (f" of {size_mb:g} MB" if size_mb else "")
    if action in ("back", "reload"):
        return f"pressing the browser's {'Back' if action == 'back' else 'Refresh'}"
    if action == "fail_next_save":
        return "making the next save fail"
    if action == "key":
        return f"pressing the {step.get('key')} key"
    if action == "wait":
        return "waiting for the page"
    return "opening the screen"


def api_call_made(calls: list[tuple[str, str, int]], value: str) -> bool:
    """`value` is "METHOD address-part", e.g. "POST /api/claims": did the
    page make that call, and did the server accept it (status below 400)?"""
    return api_call_count(calls, value) > 0


def api_call_count(calls: list[tuple[str, str, int]], value: str) -> int:
    method, _, part = value.strip().partition(" ")
    return sum(
        1
        for m, url, status in calls
        if m.upper() == method.upper() and part.strip() in url and status < 400
    )


# A field the app flagged after the test acted: marked invalid for screen
# readers (aria-invalid), refused by the browser's own check (which focuses
# the first field it refuses), or styled as an error the way UI kits do it —
# on the field or its wrapper (Bootstrap is-invalid / has-error, MUI and Ant
# "...-error", Angular ng-invalid once touched; a form's own class never
# counts, it would flag every field). Shared by `holds` and the exported test.
FIELD_FLAGGED_JS = (
    "e => { if (e.getAttribute('aria-invalid') === 'true') return true; "
    "if (e.validity && !e.validity.valid && document.activeElement === e) return true; "
    "for (let el = e, i = 0; el && i < 3 && el.tagName !== 'FORM'; el = el.parentElement, i++) { "
    "const c = ' ' + (typeof el.className === 'string' ? el.className : '') + ' '; "
    "if (/[\\s_-](is-invalid|has-error|invalid|error)\\s/i.test(c) "
    "&& !/\\s(ng-untouched|ng-pristine)\\s/.test(c)) return true; } return false; }"
)
# Controls a person reads as names, not outcomes: a proof that only shows one
# (a field's label, a button, a column header) is on screen whatever the app
# does, so it proves nothing.
_CONTROL_LINE = re.compile(
    r'^\s*-\s*(?:textbox|combobox|button|checkbox|radio|spinbutton|searchbox|switch|'
    r'slider|columnheader|listbox)\s+"([^"]*)"',
    re.M,
)


def names_a_control(check: dict[str, Any], aria: str) -> bool:
    """Is this text proof just the name of a control on the final screen?"""
    if check.get("kind") not in (None, "", "text_visible"):
        return False

    def plain(text: str) -> str:
        return " ".join(text.replace("*", "").replace(":", " ").split()).lower()

    value = plain(str(check.get("value") or ""))
    return bool(value) and any(plain(name) == value for name in _CONTROL_LINE.findall(aria))


def seen_message(check: dict[str, Any], messages: list[str]) -> bool:
    """A text proof the app showed during the test, though it may be gone
    by now (a toast fades after a few seconds)."""
    value = " ".join(str(check.get("value") or "").split()).lower()
    return (
        check.get("kind") in (None, "", "text_visible")
        and bool(value)
        and any(value in " ".join(m.split()).lower() for m in messages)
    )


# Same as the exported test's ASSERTION_TIMEOUT_MS for its final check.
PROOF_WAIT_MS = 15000
# Proving a proof is ABSENT (the broken-on-purpose run): the page has already
# settled, so a short look is enough — waiting the full 15s for something
# that should not appear cost ~15s on every scenario that passed the check.
ABSENT_WAIT_MS = 3000


def _state_target(page: Any, check: dict[str, Any]) -> Any:
    """The element an element_state proof is about, as the exported test finds
    it: by role and name; an unnamed one by the locator the test used on it,
    else the first of its role (the list on the screen)."""
    if check.get("locator"):
        return locate(page, check["locator"]).first
    if not str(check.get("name") or "").strip():
        return page.get_by_role(str(check["role"])).first
    return page.get_by_role(str(check["role"]), name=str(check["name"]), exact=True).first


def _ts_state_target(check: dict[str, Any]) -> str:
    """`_state_target` as the exported test writes it."""
    if check.get("locator"):
        return f"{ts_locator(check['locator'])}.first()"
    if not str(check.get("name") or "").strip():
        return f"page.getByRole({_q(check['role'])}).first()"
    name = _q(check["name"])
    return f"page.getByRole({_q(check['role'])}, {{ name: {name}, exact: true }}).first()"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _norm(line: str) -> str:
    return " ".join(line.strip().removeprefix("- ").split())


def proving_lines(actual: str, wanted: str, whole_up_to: int = 1500) -> str:
    """The lines of an element's real snapshot that prove the outcome, each
    with the lines it sits under (a partial snapshot must stay a tree). A
    small element is kept whole; none matched = the element as it is."""
    lines = actual.splitlines()
    if len(actual) <= whole_up_to or not lines:
        return actual
    want = [_norm(w) for w in wanted.splitlines() if _norm(w)]
    keep: set[int] = {0}
    for i, line in enumerate(lines):
        if any(w and (w == _norm(line) or w in _norm(line)) for w in want):
            keep.add(i)
            depth = _indent(line)
            for j in range(i - 1, -1, -1):
                if _indent(lines[j]) < depth:
                    keep.add(j)
                    depth = _indent(lines[j])
    if len(keep) <= 1:
        return actual[:1500]
    kept = [lines[i] for i in sorted(keep)]
    # A line whose children were cut keeps no trailing ':' (an empty YAML
    # value is not a valid snapshot).
    return "\n".join(
        line.rstrip(":") if i + 1 == len(kept) or _indent(kept[i + 1]) <= _indent(line) else line
        for i, line in enumerate(kept)
    )


async def ground_state(eyes: Eyes, check: dict[str, Any]) -> dict[str, Any] | None:
    """An element_state proof made of the element's REAL accessibility
    snapshot (role, name, options, selected/checked state, value) — never the
    model's wording, so it matches on replay. None: no such element."""
    assert eyes.page is not None
    if not str(check.get("role") or "").strip() or not str(check.get("name") or "").strip():
        return None
    try:
        actual = await _state_target(eyes.page, check).aria_snapshot(timeout=5000)
    except Exception:  # noqa: BLE001 — no such element (or the page broke)
        return None
    value = proving_lines(actual, str(check.get("value") or ""))
    return {**check, "kind": "element_state", "value": value} if value.strip() else None


_ROLE_LINE = re.compile(r'^\s*-\s+([a-z]+)\s+"((?:[^"\\]|\\.)+)"')
_ROLE_ONLY = re.compile(r"^\s*-\s+([a-z]+)")
# Elements that hold a list's rows: their changed rows prove a search, filter,
# sort or page change.
_LIST_ROLES = ("grid", "table", "treegrid", "list", "listbox")


async def state_of_last_entry(
    eyes: Eyes, actions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The last-resort proof: the state of the field the test last typed in
    or chose from (its value, its selected option), found by the very locator
    that worked. Never a button: pressing one leaves it as it was."""
    assert eyes.page is not None
    for action in reversed(actions):
        if action.get("do") not in ("fill", "choose") or not action.get("locator"):
            continue
        try:
            snap = await locate(eyes.page, action["locator"]).first.aria_snapshot(timeout=3000)
        except Exception:  # noqa: BLE001 — the field is gone (the screen moved on)
            continue
        named = _ROLE_LINE.match(snap)
        if named:
            role, name = named[1], named[2].replace('\\"', '"')
            state = await ground_state(
                eyes, {"kind": "element_state", "role": role, "name": name, "value": snap}
            )
            if state is not None:
                return state
        # No accessible name (a custom dropdown, a bare search box): found by
        # the very locator the test used on it.
        role = _ROLE_ONLY.match(snap)
        if role and snap.strip():
            return {
                "kind": "element_state",
                "role": role[1],
                "name": "",
                "locator": action["locator"],
                "value": snap[:1500],
            }
    return None


def _block(aria: str, role: str) -> list[str]:
    """The first element of `role` in a page snapshot, as normalised lines."""
    lines = aria.splitlines()
    for i, line in enumerate(lines):
        if _norm(line).split(" ")[0].rstrip(":") == role:
            out = [_norm(line)]
            for after in lines[i + 1 :]:
                if _indent(after) <= _indent(line):
                    break
                out.append(_norm(after))
            return out
    return []


async def state_of_changed_list(eyes: Eyes, start_aria: str) -> dict[str, Any] | None:
    """The other last resort, for a list's tests (search, filter, sort, next
    page): when the screen's list is no longer what it was when the test
    started, its first rows now, in order (a partial aria match keeps the
    order, so a sort is proven too), under their parent lines."""
    assert eyes.page is not None
    for role in _LIST_ROLES:
        try:
            snap = await eyes.page.get_by_role(role).first.aria_snapshot(timeout=2000)
        except Exception:  # noqa: BLE001 — no element of that role
            continue
        lines = [line for line in snap.splitlines() if _norm(line)]
        if [_norm(line) for line in lines] == _block(start_aria, role):
            return None  # the list didn't change: it proves nothing about the test
        rows = [line for line in lines if _norm(line).startswith(("row", "listitem", "option"))]
        value = proving_lines(snap, "\n".join((rows or lines)[:8]), whole_up_to=0)
        return {"kind": "element_state", "role": role, "name": "", "value": value}
    return None


async def holds(eyes: Eyes, check: dict[str, Any], wait_ms: int = PROOF_WAIT_MS) -> bool:
    """Is the test's proof true on the current screen?"""
    assert eyes.page is not None
    value = resolve_relative(str(check.get("value") or ""), unique=eyes.unique)
    if not value:
        return False
    if check.get("kind") == "element_state":
        # As the exported test checks it (toMatchAriaSnapshot): a partial
        # match, so an option added later doesn't break it.
        try:
            await expect(_state_target(eyes.page, check)).to_match_aria_snapshot(
                value, timeout=wait_ms
            )
            return True
        except Exception:  # noqa: BLE001 — not (or no longer) in that state
            return False
    if check.get("kind") == "url_contains":
        return value.lower() in eyes.page.url.lower()
    if check.get("kind") == "api_call":
        return api_call_made(eyes.calls_since_mark(), value)
    if check.get("kind") == "download":
        # A download may finish a moment after the click.
        for _ in range(max(1, wait_ms // 250)):
            if any(value.lower() in n.lower() for n in eyes.downloads_since_mark()):
                return True
            await eyes.page.wait_for_timeout(250)
        return False
    if check.get("kind") == "field_invalid":
        field = eyes.page.get_by_label(value).first
        try:
            await eyes.page.wait_for_function(
                f"el => ({FIELD_FLAGGED_JS})(el)",
                arg=await field.element_handle(timeout=wait_ms),
                timeout=wait_ms,
            )
            return True
        except Exception:  # noqa: BLE001 — no such field, or never flagged
            return False
    # Exactly what the exported test checks (`getByText(value)`, visible): one
    # element showing the text. Several labels joined into one string ("Mobile
    # number Email Continue") are in the page's text but in no single element,
    # so they were "proof" here and never matched in the exported test.
    # And waiting as it waits (expect().toBeVisible, ASSERTION_TIMEOUT_MS): a
    # confirmation that appears once the app's server answers ("Claim
    # received" after Send) is proof, not "not on screen" a moment too early.
    try:
        await eyes.page.get_by_text(value).filter(visible=True).first.wait_for(
            state="visible", timeout=wait_ms
        )
        return True
    except Exception:  # noqa: BLE001 — never appeared (or the page broke): not proven
        return False


def without_decisive_step(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 'deliberately broken' run: drop the last real action (the click
    or entry that makes the difference). A test whose proof still holds
    without it proves nothing."""
    # A trailing Back/Refresh only re-shows a screen, so its test proves the
    # step that reached that screen: drop that one instead.
    for index in range(len(script) - 1, -1, -1):
        if script[index].get("do") not in ("goto", "back", "reload", "fail_next_save"):
            return script[:index] + script[index + 1 :]
    return script


_INPUTS = ("fill", "choose", "upload")


def broken_variants(
    script: list[dict[str, Any]], own_from: int | None = None
) -> list[list[dict[str, Any]]]:
    """The deliberately broken runs to try, in order; the test catches a
    breakage when its proof fails in any one of them. First without the last
    real action (`without_decisive_step`). Then — when it is known where the
    test's own steps begin (`own_from`, after the route to its screen) —
    without the last thing the test entered or chose: an inline validation
    message appears on typing, so removing the final Continue changes nothing,
    while removing the bad value does. Never a step of the route itself: a
    route that breaks would make any proof vanish and prove nothing."""
    variants: list[list[dict[str, Any]]] = []
    last = without_decisive_step(script)
    if last != script:
        variants.append(last)
    if own_from is not None:
        for index in range(len(script) - 1, max(own_from, 1) - 1, -1):
            if script[index].get("do") in _INPUTS:
                variant = script[:index] + script[index + 1 :]
                if variant not in variants:
                    variants.append(variant)
                break
    return variants


def _q(text: object) -> str:
    return json.dumps(str(text), ensure_ascii=False)


def ts_locator(spec: dict[str, Any]) -> str:
    """The exported test's locator for a recorded one (browser.locate): the
    same Playwright call Explorer made, so the test finds the element Explorer
    actually used — never a re-guess from the label."""
    by = spec.get("by")
    exact = "true" if spec.get("exact") else "false"
    if by == "role":
        base = (
            f"page.getByRole({_q(spec['role'])}, {{ name: {_q(spec['name'])}, exact: {exact} }})"
        )
    elif by in ("label", "select_label"):
        base = f"page.getByLabel({_q(spec['text'])}, {{ exact: {exact} }})"
    elif by == "placeholder":
        base = f"page.getByPlaceholder({_q(spec['text'])})"
    elif by == "text":
        base = f"page.getByText({_q(spec['text'])}, {{ exact: {exact} }})"
    elif by == "css":
        base = f"page.locator({_q(spec['selector'])})"
    elif by == "select_with":
        base = (
            "page.locator('select').filter({ has: page.locator('option', "
            f"{{ hasText: {_q(spec['option'])} }}) }})"
        )
    else:
        raise ValueError(f"unknown locator {spec!r}")
    return base + ".filter({ visible: true }).first()"


# Same rule as Eyes._choose_by: an option already selected stays selected.
_CHECKABLE = (
    "(e) => e.matches('input[type=checkbox],input[type=radio],[role=checkbox],[role=radio]')"
)


def playwright_code(
    title: str,
    steps: list[str],
    script: list[dict[str, Any]],
    check: dict[str, Any] | None,
    expected: str,
    known_bug_observed: str | None = None,
    tag: str | None = None,
) -> str:
    """A readable Playwright (TypeScript) test that mirrors how Explorer
    finds things: by what a person reads on screen. Written in the same
    house style as Vantage's generated and recorded tests (timeout
    constants, every interaction through the project's shared
    `ensureVisible` helper) so it sits in Test cases, the exported project,
    authoring and healing exactly like any other test. `tag` ("@auth" /
    "@public") tells the project's Playwright config whether to run it
    signed in; Vantage re-applies it from its own ground truth anyway."""
    lines = [f"// {s}" for s in steps]
    body: list[str] = [
        "  test.setTimeout(TEST_TIMEOUT_MS);",
        # Resolves once the page has gone quiet (no DOM changes for 0.7 s),
        # the same "screen has settled" signal Explorer's own replay uses.
        "  const settle = () => page.evaluate('(' + DOM_QUIET + ')()').catch(() => {});",
    ]

    optional = False  # set per step below

    def act(locator: str, call: str) -> str:
        if optional:
            # A screen the app shows only sometimes (see replay): act on it
            # when it appears within a few seconds, carry on when it doesn't.
            return (
                f"  {{ const target = {locator}; "
                "if (await target.waitFor({ state: 'visible', timeout: 4000 }).then(() => true, () => false)) "
                # Nor when it is there but disabled (a Save the app greys out
                # after the first press): an optional step never fails a test.
                f"await target.{call.replace('ASSERTION_TIMEOUT_MS', '4000')}.catch(() => {{}}); }}"
            )
        return f"  await (await ensureVisible({locator})).{call};"

    fresh = not resumes_saved_progress(script)
    if fresh:
        # Same as Eyes.start_fresh_on_resume_prompts: a "resume your saved
        # progress?" screen may or may not show, depending on earlier runs.
        body += [
            "  await page.addLocatorHandler(",
            f"    page.getByRole('button', {{ name: /{START_FRESH.pattern}/i }})"
            f".or(page.getByRole('link', {{ name: /{START_FRESH.pattern}/i }})).first(),",
            "    async (button) => {",
            f"      if (!(await page.getByRole('button', {{ name: /{RESUME_LABEL.pattern}/i }}).count())) return;",
            "      await button.click();",
            # Starting over re-renders the screen: acting before it settles
            # loses the next tick or press (seen on a draft-saving wizard).
            "      await button.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});",
            "      await settle();",
            "    },",
            "    { noWaitAfter: true },",
            "  );",
            # The handler only fires before actions, not while ensureVisible
            # waits for the next step's element — so after every page change
            # answer the prompt directly too.
            "  const startFreshIfAsked = async () => {",
            f"    const fresh = page.getByRole('button', {{ name: /{START_FRESH.pattern}/i }})"
            f".or(page.getByRole('link', {{ name: /{START_FRESH.pattern}/i }})).filter({{ visible: true }}).first();",
            f"    if (!(await fresh.count()) || !(await page.getByRole('button', {{ name: /{RESUME_LABEL.pattern}/i }}).count())) return;",
            "    await fresh.click({ timeout: 3000 }).catch(() => {});  // the handler may have pressed it already",
            "    await fresh.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});",
            "    await settle();",
            "  };",
        ]
    uses_rel = uses_untick = uses_fill = uses_login = False
    for i, step in enumerate(script):
        action = step.get("do")
        optional = bool(step.get("optional")) or (
            action == "click" and bool(DISMISS_LIKE.match(str(step.get("label") or "")))
        )
        # The second press of a double-submit test: an app that disables the
        # button after the first press is behaving correctly.
        previous = script[i - 1] if i else {}
        if (
            action == "click"
            and previous.get("do") == "click"
            and previous.get("label") == step.get("label")
            and looks_final(str(step.get("label") or ""))
        ):
            optional = True
        if fresh and _starts_fresh(step):
            continue
        if action == "goto":
            body.append(
                f"  await page.goto({_q(step['url'])}, {{ timeout: NAVIGATION_TIMEOUT_MS }});"
            )
            body.append(
                "  await page.waitForLoadState('domcontentloaded', { timeout: NAVIGATION_TIMEOUT_MS });"
            )
            if fresh:
                body.append("  await startFreshIfAsked();")
        elif action == "fill":
            value = _q(step["value"])
            token = str(step["value"]).strip().lower()
            if token in ("{{username}}", "{{password}}"):
                # The project's own login settings, never the secret itself.
                uses_login, value = True, f"CREDENTIALS.{token.strip('{}')}"
            elif "{{" in str(step["value"]):
                uses_rel, value = True, f"rel({value})"
            field = ts_locator(step["locator"]) if step.get("locator") else (
                f"page.getByLabel({_q(step['field'])})"
                + (
                    f".or(page.locator({_q(field_after_caption(str(step['field'])))}))"
                    if '"' not in str(step["field"])
                    else ""
                )
                + ".filter({ visible: true }).first()"
            )
            if step.get("keys"):
                # A field that reacts to each key (a mask, suggestions): typed
                # one character at a time, as Explorer's repair found it needs.
                body.append(
                    f"  {{ const box = await ensureVisible({field}); await box.fill(''); "
                    f"await box.pressSequentially({value}, {{ delay: 60 }}); }}"
                )
            elif optional:
                body.append(act(field, f"fill({value}, {{ timeout: ASSERTION_TIMEOUT_MS }})"))
            else:
                uses_fill = True
                fmt = f", {_q(step['date_format'])}" if step.get("date_format") else ""
                body.append(f"  await fillField(page, await ensureVisible({field}), {value}{fmt});")
            if step.get("suggest"):
                # A type-ahead field: pick the suggestion Explorer picked
                # (ARIA options or a widget's plain list rows).
                body.append(
                    f"  await page.locator({_q(SUGGESTIONS)})"
                    f".filter({{ hasText: {_q(step['suggest'])}, visible: true }})"
                    ".first().click({ timeout: ASSERTION_TIMEOUT_MS });"
                )
        elif action == "choose" and step.get("locator"):
            option = _q(step["option"])
            target = ts_locator(step["locator"])
            if step["locator"].get("by") in ("select_label", "select_with"):
                body.append(
                    act(
                        target,
                        f"selectOption({{ label: {option} }}, {{ timeout: ASSERTION_TIMEOUT_MS }})",
                    )
                )
            else:
                pick = (
                    f"if (!((await target.evaluate({_CHECKABLE})) && "
                    "(await target.isChecked().catch(() => false)))) "
                    "await target.click({ timeout: ASSERTION_TIMEOUT_MS });"
                )
                if optional:
                    body.append(
                        f"  {{ const target = {target}; if (await target.waitFor("
                        "{ state: 'visible', timeout: 4000 }).then(() => true, () => false)) "
                        f"{{ {pick} }} }}"
                    )
                else:
                    body.append(f"  {{ const target = await ensureVisible({target}); {pick} }}")
        elif action == "choose":
            option = _q(step["option"])
            # Choosing means "make sure it's selected": an option a saved
            # draft already ticked would be unticked by a plain click.
            text = (
                f"page.getByText({option}, {{ exact: true }}).filter({{ visible: true }}).first()"
            )
            picked = (
                f"page.getByRole('checkbox', {{ name: {option} }})"
                f".or(page.getByRole('radio', {{ name: {option} }})).first()"
            )
            is_picked = "((await picked.count()) && (await picked.isChecked().catch(() => false)))"
            # A plain dropdown list can't be clicked open like other options:
            # select the option in the dropdown that offers it (as Eyes.choose).
            body.append(
                "  { const select = page.locator('select').filter({ visible: true })"
                f".filter({{ has: page.locator('option', {{ hasText: {option} }}) }}).first();"
            )
            body.append(
                f"  if (await select.count()) await select.selectOption({{ label: {option} }}, "
                "{ timeout: ASSERTION_TIMEOUT_MS }); else"
            )
            if optional:
                body.append(
                    f"  {{ const picked = {picked}; if (!{is_picked}) "
                    + act(text, "click({ timeout: ASSERTION_TIMEOUT_MS })").strip()
                    + " } }"
                )
            else:
                # Look only once the option is on screen: finding it can
                # first answer a resume prompt, which restores the draft.
                body.append(
                    f"  {{ const target = await ensureVisible({text}); const picked = {picked}; "
                    f"if (!{is_picked}) await target.click({{ timeout: ASSERTION_TIMEOUT_MS }}); }} }}"
                )
        elif action == "click":
            label = _q(step["label"])
            # Wait for the screen to react before the next step, as Explorer's
            # replay does: two "Continue" presses in a row otherwise both land
            # on the first screen while the second is still rendering.
            body.append("  { const before = await page.locator('body').innerText();")
            button = ts_locator(step["locator"]) if step.get("locator") else (
                f"page.getByRole('button', {{ name: {label} }})"
                f".or(page.getByRole('link', {{ name: {label} }})).filter({{ visible: true }}).first()"
            )
            if advances_step(step) and not optional:
                # Untick right before the press, once the screen (and any
                # draft it restores) is there — see UNTICK_UNCHOSEN.
                uses_untick = True
                keep = json.dumps(json.dumps(chosen_on_screen(script, i), ensure_ascii=False))
                body.append(f"  const target = await ensureVisible({button});")
                body.append(
                    f"  await page.evaluate('(' + UNTICK_UNCHOSEN + ')(' + {keep} + ')').catch(() => 0);"
                )
                body.append("  await target.click({ timeout: ASSERTION_TIMEOUT_MS });")
            else:
                body.append(act(button, "click({ timeout: ASSERTION_TIMEOUT_MS })"))
            body.append(
                "  await page.waitForFunction((b) => document.body.innerText !== b, before, "
                "{ timeout: 5000 }).catch(() => {}); await settle(); }"
            )
            if fresh:
                body.append("  await startFreshIfAsked();")
        elif action == "upload":
            # The sample file travels inside the test, so it runs anywhere; a
            # big one is padded by the test itself (not megabytes of text),
            # several get their own names — the same files Explorer attached.
            path = sample_file(str(step.get("kind") or "image"))
            count, size_mb = upload_shape(step)
            data = base64.b64encode(path.read_bytes()).decode()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            pad = padding(path, size_mb)
            buffer = (
                f"Buffer.concat([Buffer.from({_q(data)}, 'base64'), Buffer.alloc({pad})])"
                if pad
                else f"Buffer.from({_q(data)}, 'base64')"
            )
            files = ", ".join(
                f"{{ name: {_q(name)}, mimeType: {_q(mime)}, buffer: {buffer} }}"
                for name in file_names(path, count, size_mb)
            )
            body.append(
                f"  await page.locator('input[type=file]').first().setInputFiles([{files}]);"
            )
        elif action == "key":
            # A keystroke a repair found the field needs (Enter confirms it…).
            if step.get("locator"):
                body.append(f"  await {ts_locator(step['locator'])}.focus();")
            body.append(f"  await page.keyboard.press({_q(str(step.get('key') or ''))});")
        elif action == "wait":
            ms = max(0, min(int(step.get("ms") or 0), 5000))
            body.append(f"  await page.waitForTimeout({ms});")
        elif action == "fail_next_save":
            # The app's next save gets a server error, once (Eyes.browser).
            body.append(
                "  { let used = false; await page.route('**/*', async (route) => { "
                "const r = route.request(); if (!used && ['POST', 'PUT', 'PATCH'].includes("
                "r.method()) && ['xhr', 'fetch'].includes(r.resourceType())) { used = true; "
                "await route.fulfill({ status: 500, contentType: 'application/json', "
                "headers: { 'Access-Control-Allow-Origin': r.headers()['origin'] ?? '*' }, "
                "body: '{\"error\": \"Simulated server error\"}' }); } "
                "else { await route.fallback(); } }); }"
            )
        elif action in ("back", "reload"):
            call = "goBack" if action == "back" else "reload"
            body.append(
                f"  await page.{call}({{ waitUntil: 'domcontentloaded', timeout: NAVIGATION_TIMEOUT_MS }});"
            )
            body.append("  await settle();")
    if check and check.get("kind") == "api_call":
        method, _, part = str(check["value"]).strip().partition(" ")
        # Listen from the start: the call happens during the steps.
        body[1:1] = [
            "  const calls: { method: string; url: string; status: number }[] = [];",
            "  page.on('response', (r) => { const t = r.request().resourceType(); "
            "if (t === 'xhr' || t === 'fetch') calls.push({ method: r.request().method(), "
            "url: r.url(), status: r.status() }); });",
        ]
        body.append(
            f"  await expect.poll(() => calls.some((c) => c.method === {_q(method.upper())} && "
            f"c.url.includes({_q(part.strip())}) && c.status < 400), "
            "{ timeout: ASSERTION_TIMEOUT_MS }).toBe(true);"
        )
    elif check and check.get("kind") == "download":
        body[1:1] = [
            "  const downloads: string[] = [];",
            "  page.on('download', (d) => downloads.push(d.suggestedFilename()));",
        ]
        body.append(
            f"  await expect.poll(() => downloads.some((n) => n.toLowerCase().includes("
            f"{_q(str(check['value']).lower())})), {{ timeout: ASSERTION_TIMEOUT_MS }}).toBe(true);"
        )
    elif check and check.get("kind") == "url_contains":
        body.append(
            f"  await expect(page).toHaveURL(new RegExp({_q(re.escape(str(check['value'])))}), "
            "{ timeout: ASSERTION_TIMEOUT_MS });"
        )
    elif check and check.get("kind") == "element_state":
        state = _q(check["value"])
        if "{{" in str(check["value"]):  # a name this run created ({{unique}})
            uses_rel, state = True, f"rel({state})"
        body.append(
            f"  await expect({_ts_state_target(check)}).toMatchAriaSnapshot("
            f"{state}, {{ timeout: ASSERTION_TIMEOUT_MS }});"
        )
    elif check and check.get("kind") == "field_invalid":
        body.append(
            f"  await expect.poll(() => page.getByLabel({_q(check['value'])}).first()"
            f".evaluate({FIELD_FLAGGED_JS}), {{ timeout: ASSERTION_TIMEOUT_MS }}).toBe(true);"
        )
    elif check:
        text = _q(check["value"])
        if "{{" in str(check["value"]):  # a name this run created ({{unique}})
            uses_rel, text = True, f"rel({text})"
        proof = f"page.getByText({text}).filter({{ visible: true }}).first()"
        # Watched from the start: a message that shows for a few seconds (a
        # toast, a pop-up) counts though it is gone by the time the steps end.
        body[1:1] = [
            f"  const shown = {proof}.waitFor({{ state: 'visible', timeout: 600000 }})"
            ".then(() => true, () => false);",
        ]
        body.append(
            "  if (!(await Promise.race([shown, page.waitForTimeout(0).then(() => false)]))) "
            f"await expect({proof}).toBeVisible({{ timeout: ASSERTION_TIMEOUT_MS }});"
        )
    if known_bug_observed:
        # A plain `test(...)` (so the sign-in tag is applied like any test)
        # parked with `test.fixme(true, reason)`: the reason reaches the run
        # report, which shows it as "blocked: Known bug — ..." not "errored".
        reason = (
            f"Known bug — should: {expected.rstrip('.')}. The app currently: {known_bug_observed}"
        )
        body.insert(0, f"  test.fixme(true, {_q(reason[:400])});")
    header = "test"
    note = (
        [
            f"// KNOWN BUG — should: {expected}",
            f"// the app currently: {known_bug_observed}",
            "// The check below proves today's (wrong) behaviour; fix the app, then update it.",
        ]
        if known_bug_observed
        else [f"// Expected: {expected}"]
    )
    return "\n".join(
        [
            (
                "import { test, expect, type Locator, type Page } from '@playwright/test';"
                if uses_fill
                else "import { test, expect } from '@playwright/test';"
            ),
            "import { ensureVisible } from '../../support/interactions';",
            *(["import { CREDENTIALS } from '../../support/config';"] if uses_login else []),
            "",
            "const NAVIGATION_TIMEOUT_MS = 30000;",
            "const ASSERTION_TIMEOUT_MS = 15000;",
            "const TEST_TIMEOUT_MS = 180000;",
            f"const DOM_QUIET = {json.dumps(_DOM_QUIET_JS.strip())};",
            "",
            *(_REL_TS if uses_rel else []),
            *(
                [f"const CALENDAR = {json.dumps(_CALENDAR_JS.strip())};", "", *_FILL_TS]
                if uses_fill
                else []
            ),
            *(
                [
                    "// Saved drafts can bring back boxes an earlier session ticked; untick what this test didn't choose.",
                    f"const UNTICK_UNCHOSEN = {json.dumps(UNTICK_UNCHOSEN_JS)};",
                    "",
                ]
                if uses_untick
                else []
            ),
            *lines,
            *note,
            (
                f"{header}({_q(title)}, {{ tag: '{tag}' }}, async ({{ page }}) => {{"
                if tag
                else f"{header}({_q(title)}, async ({{ page }}) => {{"
            ),
            *body,
            "});",
            "",
        ]
    )


# TypeScript twin of sense.resolve_relative: dates relative to the day the
# test runs ("{{today+1d}}" = tomorrow), so date-rule tests never go stale.
# Read-only boxes are date/time pickers: typing changes only the text, not
# the app's value. Pick from the calendar like Explorer does (Eyes.
# _pick_from_calendar, same CALENDAR script); otherwise fill as usual.
_FILL_TS = [
    "async function fillField(page: Page, box: Locator, value: string, format?: string): Promise<void> {",
    # A date typed into a text box in the field's own format (Explorer read
    # it from the page: Eyes._date_hint), twin of sense.format_date.
    "  if (format) {",
    r"    const d = /^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$/.exec(value);",
    "    if (d) {",
    "      const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];",
    "      const [y, mo, dd] = [Number(d[1]), Number(d[2]), Number(d[3])];",
    "      const parts: Record<string, string> = { yyyy: String(y).padStart(4, '0'), yy: String(y % 100).padStart(2, '0'), mmmm: months[mo - 1], mmm: months[mo - 1].slice(0, 3), mm: String(mo).padStart(2, '0'), m: String(mo), dd: String(dd).padStart(2, '0'), d: String(dd) };",
    "      value = format.replace(/yyyy|yy|mmmm|mmm|mm|m|dd|d/gi, (t) => parts[t.toLowerCase()]);",
    "    }",
    "  }",
    "  const readOnly = await box.evaluate((e) => (e as HTMLInputElement).readOnly === true);",
    "  if (!value.trim()) {",
    "    if (readOnly) {",
    "      await box.click();",
    "      await page.keyboard.press('ControlOrMeta+A');",
    "      await page.keyboard.press('Delete');",
    "      await page.keyboard.press('Escape');",
    "    } else {",
    "      await box.fill('', { timeout: ASSERTION_TIMEOUT_MS });",
    "    }",
    "    return;",
    "  }",
    "  if (!readOnly) {",
    "    await box.fill(value, { timeout: ASSERTION_TIMEOUT_MS });",
    "    return;",
    "  }",
    r"  const m = /^\s*(\d{4})-(\d{1,2})-(\d{1,2})/.exec(value);",
    "  if (!m) return;",
    "  const wanted = JSON.stringify({ year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) });",
    "  await box.click();",
    "  await page.waitForTimeout(500);",
    "  let reopened = false;",
    "  for (let i = 0; i < 40; i++) {",
    "    let out = await page.evaluate('(' + CALENDAR + ')(' + wanted + ')');",
    "    if (out === 'none' && !reopened) {",
    "      reopened = true;",
    "      await box.click();",
    "      await page.waitForTimeout(500);",
    "      out = await page.evaluate('(' + CALENDAR + ')(' + wanted + ')');",
    "    }",
    "    if (out === 'none') break;",
    "    if (out === 'click') {  // an arrow, the header, a year or a month",
    "      await page.locator('[data-explorer-pick]').first().click();",
    "      await page.waitForTimeout(300);",
    "      continue;",
    "    }",
    "    await page.waitForTimeout(300);",
    "    if (out === 'pick') {",
    "      await page.locator('[data-explorer-pick]').first().click();",
    "      await page.waitForTimeout(500);",
    "      if (!(await box.inputValue()).trim()) {",
    "        for (const word of ['OK', 'Done', 'Apply', 'Set', 'Select']) {",
    "          const ok = page.getByRole('button', { name: word, exact: true }).filter({ visible: true });",
    "          if (await ok.count()) { await ok.first().click(); break; }",
    "        }",
    "      }",
    "      await page.keyboard.press('Tab');",
    "      break;",
    "    }",
    "  }",
    # No calendar (or the date is years away): type it in the display
    # formats people use until one sticks — same list as sense.date_variants.
    "  if (!(await box.inputValue()).trim()) {",
    "    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];",
    "    const [y, mo, d] = [m[1], Number(m[2]), Number(m[3])];",
    "    const p2 = (n: number) => String(n).padStart(2, '0');",
    "    const name = months[mo - 1] ?? '';",
    "    const variants = [value, `${name.slice(0, 3)} ${d}, ${y}`, `${p2(mo)}/${p2(d)}/${y}`, `${p2(d)}/${p2(mo)}/${y}`,",
    "      `${y}-${p2(mo)}-${p2(d)}`, `${p2(d)}-${p2(mo)}-${y}`, `${name} ${d}, ${y}`, `${d} ${name.slice(0, 3)} ${y}`];",
    "    for (const v of variants) {",
    "      await box.evaluate((e) => e.removeAttribute('readonly'));",
    "      await box.click();",
    "      await page.keyboard.press('ControlOrMeta+A');",
    "      await page.keyboard.type(v);",
    "      await page.keyboard.press('Tab');",
    "      await page.waitForTimeout(300);",
    # Showing the text isn't enough: the app must accept it (not flag the box invalid).
    "      if ((await box.inputValue()).trim() && (await box.getAttribute('aria-invalid')) !== 'true') break;",
    "    }",
    "  }",
    "  await expect(box).not.toHaveValue('', { timeout: ASSERTION_TIMEOUT_MS });",
    "}",
    "",
]

_REL_TS = [
    # This run's {{unique}}: the same all through the test, new every run.
    "const UNIQUE = Date.now().toString(16).slice(-7);",
    "function rel(v: string): string {",
    "  v = v.replace(/\\{\\{\\s*unique\\s*\\}\\}/gi, UNIQUE);",
    r"  return v.replace(/\{\{\s*(today|now)\s*(?:([+-])\s*(\d+)\s*([dhm]))?\s*\}\}/gi, (_m, base: string, sign?: string, n?: string, unit?: string) => {",
    "    const step = { d: 86400000, h: 3600000, m: 60000 }[(unit || 'd').toLowerCase() as 'd' | 'h' | 'm'];",
    "    const t = new Date(Date.now() + step * Number(n || 0) * (sign === '-' ? -1 : 1));",
    "    const p = (x: number) => String(x).padStart(2, '0');",
    "    const day = `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}`;",
    "    return base.toLowerCase() === 'today' ? day : `${day} ${p(t.getHours())}:${p(t.getMinutes())}`;",
    "  });",
    "}",
    "",
]
