"""Replaying a test's recorded actions without the model, checking its
proof, and exporting it as a Playwright test (Stage 5, PLAN.md §6 / D1)."""

import base64
import json
import mimetypes
import re
from typing import Any

from explorer_worker.browser import _CALENDAR_JS, _DOM_QUIET_JS, Eyes, field_after_caption
from explorer_worker.samples import sample_file
from explorer_worker.sense import (
    CONTINUE_LIKE,
    DISMISS_LIKE,
    RESUME_LABEL,
    START_FRESH,
    looks_final,
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
    if action == "fill":
        return await eyes.fill_field(str(step["field"]), str(step["value"]))
    if action == "choose":
        return await eyes.choose(str(step.get("field") or ""), str(step["option"]))
    if action == "click":
        before = await eyes.fingerprint()
        ok = await eyes.click_text(str(step["label"]), "button")
        if ok:
            await eyes.wait_for_change(before, 8000)
        return ok
    if action == "upload":
        path = sample_file(str(step.get("kind") or "image"))
        return await eyes.upload_file(str(step.get("field") or ""), str(path))
    if action in ("back", "reload"):
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
        return f"attaching a {step.get('kind') or 'image'} file"
    if action in ("back", "reload"):
        return f"pressing the browser's {'Back' if action == 'back' else 'Refresh'}"
    return "opening the screen"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def api_call_made(calls: list[tuple[str, str, int]], value: str) -> bool:
    """`value` is "METHOD address-part", e.g. "POST /api/claims": did the
    page make that call, and did the server accept it (status below 400)?"""
    method, _, part = value.strip().partition(" ")
    return any(
        m.upper() == method.upper() and part.strip() in url and status < 400
        for m, url, status in calls
    )


async def holds(eyes: Eyes, check: dict[str, Any]) -> bool:
    """Is the test's proof true on the current screen?"""
    assert eyes.page is not None
    value = str(check.get("value") or "")
    if not value:
        return False
    if check.get("kind") == "url_contains":
        return value.lower() in eyes.page.url.lower()
    if check.get("kind") == "api_call":
        return api_call_made(eyes.calls_since_mark(), value)
    body = await eyes.page.evaluate("() => document.body ? document.body.innerText : ''")
    return _norm(value) in _norm(body)


def without_decisive_step(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 'deliberately broken' run: drop the last real action (the click
    or entry that makes the difference). A test whose proof still holds
    without it proves nothing."""
    # A trailing Back/Refresh only re-shows a screen, so its test proves the
    # step that reached that screen: drop that one instead.
    for index in range(len(script) - 1, -1, -1):
        if script[index].get("do") not in ("goto", "back", "reload"):
            return script[:index] + script[index + 1 :]
    return script


def _q(text: object) -> str:
    return json.dumps(str(text), ensure_ascii=False)


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
            field = (
                f"page.getByLabel({_q(step['field'])})"
                + (
                    f".or(page.locator({_q(field_after_caption(str(step['field'])))}))"
                    if '"' not in str(step["field"])
                    else ""
                )
                + ".filter({ visible: true }).first()"
            )
            if optional:
                body.append(act(field, f"fill({value}, {{ timeout: ASSERTION_TIMEOUT_MS }})"))
            else:
                uses_fill = True
                body.append(f"  await fillField(page, await ensureVisible({field}), {value});")
            if step.get("suggest"):
                # A type-ahead field: pick the suggestion Explorer picked.
                body.append(
                    f"  await page.getByRole('option', {{ name: {_q(step['suggest'])} }})"
                    ".filter({ visible: true }).first().click({ timeout: ASSERTION_TIMEOUT_MS });"
                )
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
            button = (
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
            # The sample file travels inside the test, so it runs anywhere.
            path = sample_file(str(step.get("kind") or "image"))
            data = base64.b64encode(path.read_bytes()).decode()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            body.append(
                "  await page.locator('input[type=file]').first().setInputFiles("
                f"{{ name: {_q(path.name)}, mimeType: {_q(mime)}, "
                f"buffer: Buffer.from({_q(data)}, 'base64') }});"
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
    elif check and check.get("kind") == "url_contains":
        body.append(
            f"  await expect(page).toHaveURL(new RegExp({_q(re.escape(str(check['value'])))}), "
            "{ timeout: ASSERTION_TIMEOUT_MS });"
        )
    elif check:
        body.append(
            f"  await expect(page.getByText({_q(check['value'])}).filter({{ visible: true }}).first())"
            ".toBeVisible({ timeout: ASSERTION_TIMEOUT_MS });"
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
    "async function fillField(page: Page, box: Locator, value: string): Promise<void> {",
    "  const readOnly = await box.evaluate((e) => (e as HTMLInputElement).readOnly === true);",
    "  if (!value.trim()) {",
    "    if (readOnly) {",
    "      await box.click();",
    "      await page.keyboard.press('Control+A');",
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
    "      await page.keyboard.press('Control+A');",
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
    "function rel(v: string): string {",
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
