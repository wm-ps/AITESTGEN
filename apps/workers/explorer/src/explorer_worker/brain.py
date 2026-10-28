"""Explorer's thinking: the prompts and the three judgement calls of the
Understand stage — read a screen, decide where to look next, write the App
Summary. Every prompt carries the same stance (PLAN.md §4): the app is
evidence, not truth.
"""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from explorer_worker.llm import FAST_MODEL, THINKING_MODEL, ask_json

STANCE = """You are Vantage Explorer, a senior QA engineer studying a business web \
application for the first time. Core principle: the application is EVIDENCE, not the \
truth. It may be buggy. Never assume that what the app does is correct — judge it \
against common sense, industry norms and what the user told you, and point out \
anything that looks wrong. Write every human-facing sentence in plain, friendly \
business language (no technical jargon like DOM, API, selector, endpoint, JSON). \
When you tell a person about a button or link, name it by what it is for ("the \
Contact details button", "Edit the claim"), never by how it looks or by its icon \
("icon", "pencil", "Press icon to contact details"). Fields that must match the \
screen (exact visible text, labels to click) still use the exact on-screen text."""

_PERCEIVE_SYSTEM = (
    STANCE
    + """

You will get a screenshot of one screen plus a machine reading of its contents. \
Understand it like a person would and reply with ONLY this JSON object:
{
  "screen_name": "short business name, e.g. 'Order list', 'New employee form', 'Lead details'",
  "entity": "the main business thing shown (singular, e.g. 'Order'), or null for dashboards/settings",
  "view_kind": "one of: list | detail | form | wizard | dashboard | search | settings | login | error | other",
  "mode": "create | edit | view | null",
  "purpose": "one plain sentence: what a user does here",
  "thought": "one short first-person sentence for a live activity feed, e.g. 'This is where staff create a new order — it asks for customer, product and quantity.'",
  "fields": [{"label": "...", "type": "text|number|date|email|select|checkbox|radio|file|textarea|other", "required": true, "notes": "rules or hints visible on screen or in the machine reading (allowed file types from 'accept', min/max, length, pattern), else ''"}],
  "actions": [{"label": "exact visible text", "kind": "navigate|create|edit|delete|submit|filter|search|export|other", "risky": true}],
  "hidden_hints": ["plain guess about a part of this screen that probably only appears under some condition, and why — e.g. 'An approval section may appear for large amounts (there is an Amount field and an empty Approvals panel)'"],
  "is_error_page": false,
  "error_text": null,
  "wording_problems": [{"text": "exact text", "why": "spelling/grammar/unclear"}],
  "looks_wrong": [{"what": "...", "why": "which common-sense rule it breaks"}],
  "worth_exploring": [{"label": "exact visible text of a menu item, tab or link on this screen", "why": "plain reason", "value": 1}],
  "starts_flow": [{"label": "exact visible text of a button/link that STARTS a business task, e.g. 'New order', 'Add employee', 'Apply now'", "goal": "the task in plain words, e.g. 'Place a new order'", "value": 1}],
  "created_records": [{"what": "e.g. 'Order number'", "value": "the exact identifier shown, character for character", "context": "plain words, e.g. 'given after placing an order'"}]
}
'created_records' lists ONLY identifiers the app has just generated for a record (a reference, confirmation, order or ticket number shown after creating something, or the number of a record listed for this user) — never values the user typed in, and never placeholder or example text. They are reused later as test data.
If this is a screen listed under 'Screens already understood' (same purpose — only the \
data, filled-in values or messages differ), reuse its EXACT name, view_kind and mode. \
'looks_wrong' is ONLY for problems with how the APP behaves or displays things (impossible or inconsistent dates/numbers, wrong totals, contradictory statuses, raw error text, broken layout, sensitive data shown where it should not be). Do NOT report odd records that other users simply typed in (test names, blank optional fields, gibberish values) — that is data, not an app problem. Rules: 'risky' = it would change or delete data, send something, pay, approve, or sign \
out. 'worth_exploring' lists only navigation (menus, tabs, links to other screens) — \
never buttons that save, submit or delete — ranked by business importance, value 1-5 \
(5 = core business area). 'starts_flow' lists entry points into a business task \
(usually a form or step-by-step wizard) — never final Save/Submit/Send buttons. Never \
repeat a problem listed under 'already noted', even in different words. Keep arrays \
short and meaningful; empty arrays are fine."""
)


def _compact_inventory(inv: dict[str, Any]) -> str:
    keep = {
        "title": inv.get("title"),
        "headings": inv.get("headings"),
        "fields": inv.get("fields"),
        "buttons": inv.get("buttons"),
        "tables": inv.get("tables"),
        "messages_on_screen": inv.get("alerts"),
        "navigation": [n["text"] for n in inv.get("nav_items", [])][:60],
        "links": [link["text"] for link in inv.get("links", []) if link.get("text")][:60],
        "visible_text_start": (inv.get("body_text") or "")[:1500],
    }
    return json.dumps(keep, ensure_ascii=False)


async def perceive(
    shot: bytes,
    inventory: dict[str, Any],
    known: list[str],
    notes: str | None,
    already_noted: list[str] | None = None,
    goal_rule: str | None = None,
) -> dict[str, Any]:
    user = (
        (
            f"The user's goal (strict): {goal_rule}\nAlso reply with \"goal_fit\": "
            "\"inside | on_the_way | past_stop | outside\" — where this screen sits "
            "against that goal (on_the_way = must be passed through to reach it).\n"
            if goal_rule
            else ""
        )
        + f"Screen address: {inventory.get('url')}\n"
        f"Screens already understood: {', '.join(known) or 'none yet'}\n"
        f"Problems already noted: {'; '.join((already_noted or [])[-40:]) or 'none'}\n"
        + (f"What the user told us about the app: {notes}\n" if notes else "")
        + f"Machine reading of the screen:\n{_compact_inventory(inventory)}"
    )
    reading = await ask_json(_PERCEIVE_SYSTEM, user, images=[shot], model=THINKING_MODEL)
    reading.setdefault("screen_name", inventory.get("title") or "Untitled screen")
    reading.setdefault("view_kind", "other")
    for key in (
        "fields",
        "actions",
        "hidden_hints",
        "wording_problems",
        "looks_wrong",
        "worth_exploring",
        "starts_flow",
    ):
        if not isinstance(reading.get(key), list):
            reading[key] = []
    return reading


_CHOOSE_SYSTEM = (
    STANCE
    + """

You are deciding which part of the app to look at next while getting to know it. \
Prefer core business areas you have not seen yet over settings/help/profile pages, \
and prefer variety (a new kind of business thing) over a second example of something \
already understood. Reply with ONLY:
{"pick": <index number from the options>, "thought": "one short first-person sentence for the live feed explaining the choice in plain words"}"""
)


async def choose_next(
    options: list[dict[str, Any]], understood: list[str], left: int
) -> dict[str, Any]:
    listing = "\n".join(
        f"{i}. '{o['label']}' (seen on: {o['from_screen']}; why: {o['why']}; importance {o['value']}/5)"
        for i, o in enumerate(options)
    )
    user = (
        f"Screens understood so far: {', '.join(understood) or 'none'}\n"
        f"Screens left in this first look: {left}\n"
        f"Options:\n{listing}"
    )
    choice = await ask_json(_CHOOSE_SYSTEM, user, model=FAST_MODEL)
    pick = choice.get("pick")
    if not isinstance(pick, int) or not 0 <= pick < len(options):
        choice["pick"] = 0
    return choice


_SUMMARY_SYSTEM = (
    STANCE
    + """

You have finished a first look around the application. Write the one-page App \
Summary a client will read and correct. Reply with ONLY this JSON object:
{
  "app_name": "...",
  "one_liner": "one plain sentence: what this app is and who it is for",
  "domain": "industry / business area",
  "who_uses_it": [{"role": "...", "goal": "what they come here to do"}],
  "business_things": [{"name": "singular business object, e.g. Order", "description": "plain sentence", "statuses": ["life-cycle states you saw or expect, e.g. Draft, Submitted"]}],
  "key_tasks": [{"name": "e.g. Place an order", "why_it_matters": "plain sentence", "steps": ["short steps a user takes"]}],
  "rules_we_expect": [{"rule": "plain rule, e.g. 'An email address must contain @'", "source": "common sense | seen in the app | your notes", "confidence": "high | medium | low"}],
  "hidden_parts_suspected": [{"where": "screen name", "what": "what probably appears only sometimes", "why": "plain reason"}],
  "questions_for_you": [{"question": "a short multiple-choice question whose answer would most change how we test", "options": ["...", "..."]}]
}
Rules: base 'rules_we_expect' on common sense and industry norms, not just on what \
the app happened to do — mark rules only seen in the app as 'seen in the app' with low \
confidence. At most 5 questions, only important ones. Be specific to THIS app."""
)


async def summarize(
    screens: list[dict[str, Any]],
    health: dict[str, Any],
    notes: str | None,
    app_name: str,
    branches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    user = (
        f"Application name as registered: {app_name}\n"
        + (f"What the user told us: {notes}\n" if notes else "")
        + f"App health check: {json.dumps(health, ensure_ascii=False)}\n"
        f"Screens understood ({len(screens)}):\n{json.dumps(screens, ensure_ascii=False)[:60000]}\n"
        "Choices seen while walking through tasks that probably change the path: "
        f"{json.dumps(branches or [], ensure_ascii=False)[:8000]}"
    )
    return await ask_json(_SUMMARY_SYSTEM, user, model=THINKING_MODEL)


_STEP_SYSTEM = (
    STANCE
    + """

You are pursuing a goal in the app the way a careful real user would, one screen \
(step) at a time. Decide what to enter on THIS screen and what to press next — a \
button, link, menu item or tab — or which already-known screen to jump to. Reply \
with ONLY:
{
  "thought": "one short first-person sentence for the live feed, e.g. 'This is a standard order with home delivery, so I will continue to payment details.'",
  "fills": [{"field": "exact field label (or placeholder)", "value": "realistic value"}],
  "choices": [{"field": "exact field/question label", "option": "exact visible option text to pick"}],
  "uploads": [{"field": "label of the upload area or button", "kind": "image | png | pdf | text | csv"}],
  "advance": "exact visible text of the button, link, menu item or tab to press next, or null",
  "go_to_screen": "exact name from the known screens list to jump straight there (only when that is the quickest way toward the goal and nothing needs entering here), else null",
  "advance_is_final": false,
  "browser": "back | reload | null (the browser's own Back or Refresh button)",
  "branch_points": [{"question": "a choice on this screen that probably changes what comes next", "options_worth_trying_later": ["..."], "why": "plain reason"}],
  "needs_from_human": ["a question to the user for a value ONLY they can know, e.g. 'Which customer account number should I use to look up an account?'"],
  "done": false
}
Rules:
- Use test data the user gave (notes) whenever a field asks for it (e.g. account or reference numbers).
- 'needs_from_human' is ONLY for values that exist outside the screen and cannot be made up (a real account or reference number, a login, a code sent by email or text). Never ask for files, never for something the app should show or load, never for values you can invent. Write each as one short question to the user.
- Otherwise make up realistic, internally consistent data (names, dates in the past for \
past events, valid email/phone formats). Never use 'test' or 'asdf'.
- Pick the most common, everyday option for choices (e.g. 'Standard delivery'), and list \
the other options that may lead somewhere different under branch_points.
- Fill every field that looks required.
- To attach a file, add it to 'uploads'. Explorer has realistic sample files of each \
kind (a photo, a PNG, a one-page PDF, a text file, a CSV), so never ask the \
human for a file. Use 'image' for photos; use another kind only when the goal is to \
check that a wrong file type is refused. Upload once per screen, and not again when \
the file already shows as attached.
- If the steps so far show you going back and forth between the same screens without \
getting closer to the goal, stop: set done = true and say why in 'thought'.
- Write every date value as YYYY-MM-DD (Explorer converts it to the app's own format). \
For a date picker, put the value in 'fills' like any other field.
- When a date only makes sense relative to today (must be in the future or the past, an \
age limit), write a token instead of a fixed date: {{today}}, {{today+1d}}, {{today-30d}}, \
or {{now+2h}} for a date with time. Explorer works it out each time, so a replay months \
later still tests the same thing. Prefer whole days (tomorrow) over minutes.
- Never ask the human for a value the app itself creates (e.g. an order number you get by placing an order): use one from the notes if there is one; otherwise say in 'thought' that it must be created first, and set done = true.
- If the app offers to resume saved or unfinished progress, choose to start over / start \
fresh (earlier runs may have left it behind), unless the goal or mission instructions are \
about resuming saved progress.
- 'advance_is_final' = true if the button would actually send, submit, pay or confirm \
something for real (e.g. 'Submit order', 'Send', 'Pay'). We never press those yet.
- 'done' = true if this screen is a confirmation/end of the task or nothing moves forward.
- If the screen shows an error message from your previous attempt, fix the values.
- If mission instructions are given, follow them exactly when you reach the point they \
describe (e.g. choose the specific option they name) — that is the point of the mission.
- 'browser': use Back or Refresh only when the goal or instructions are about them \
(e.g. 'refresh and check the entry is still there', 'go back to the list'); then leave \
'advance' null. Otherwise null.
- 'done' = true also when the goal has been reached or clearly cannot be reached."""
)


async def decide_step(
    shot: bytes,
    inventory: dict[str, Any],
    goal: str,
    notes: str | None,
    history: list[str],
    *,
    instructions: str | None = None,
    known_screens: list[str] | None = None,
) -> dict[str, Any]:
    user = (
        f"Goal: {goal}\n"
        + (f"Mission instructions: {instructions}\n" if instructions else "")
        + f"Known screens you can jump to: {', '.join((known_screens or [])[:60]) or 'none'}\n"
        + (f"Test data and notes from the user: {notes}\n" if notes else "No test data given.\n")
        + f"Steps so far: {' | '.join(history[-12:]) or 'this is the first step'}\n"
        f"Machine reading of the screen:\n{_compact_inventory(inventory)}"
    )
    step = await ask_json(_STEP_SYSTEM, user, images=[shot], model=THINKING_MODEL)
    for key in ("fills", "choices", "uploads", "branch_points", "needs_from_human"):
        if not isinstance(step.get(key), list):
            step[key] = []
    return step


def scope(brief: dict[str, Any]) -> str:
    """What the user chose to cover at review — it overrides everything else."""
    focus = str(brief.get("focus") or "").strip()
    rule = str((brief.get("scope") or {}).get("rule") or "").strip()
    skip = [str(n) for n in brief.get("skip_screens") or []]
    goal = (
        f"The user's goal for this run is a STRICT rule: {rule} Plan nothing outside it.\n"
        if rule
        else f"The user's goal for this run (follow it first): {focus}\n"
        if focus
        else ""
    )
    return goal + (
        f"The user left these screens out — never plan anything on or for them: {', '.join(skip)}\n"
        if skip
        else ""
    )


_GOAL_SYSTEM = (
    STANCE
    + """

The user wrote a goal for this run that limits what Explorer may explore and test. \
Restate it as a strict rule, and place every known screen against it. Reply with ONLY:
{"rule": "the goal as a strict rule in one or two plain sentences, naming the stop \
screen if there is one", "fits": {"<exact screen name>": "inside | on_the_way | past_stop | outside"}}
- inside: part of what the goal covers (the stop screen itself is inside, and is tested fully).
- on_the_way: outside the goal but must be passed through to reach it (e.g. a home page).
- past_stop: comes after the goal's stop point.
- outside: anything else the goal does not cover.
Match by meaning, not wording ("policy search" is the screen where a policy is found). \
Read the goal literally: "only/just X up to Y" — everything outside flow X is outside, \
screens after Y are past_stop; a stop point without "only" cuts just that path and the \
rest stays inside; branches inside the named flow before the stop are inside; "leave \
out Z" makes Z outside and everything else inside."""
)


async def read_goal(goal: str, screens: list[dict[str, Any]]) -> dict[str, Any]:
    user = (
        f"The user's goal: {goal}\n"
        f"Known screens: {json.dumps(screens, ensure_ascii=False)[:30000]}"
    )
    reply = await ask_json(_GOAL_SYSTEM, user, model=THINKING_MODEL)
    fits = reply.get("fits")
    return {
        "rule": str(reply.get("rule") or goal).strip()[:600],
        "fits": fits if isinstance(fits, dict) else {},
    }


_MISSIONS_SYSTEM = (
    STANCE
    + """

The user has confirmed the App Summary. Turn it into a Mission Board: concrete goals \
that a set of browser agents will now pursue in the app, so that together they \
understand the WHOLE application. Reply with ONLY:
{
  "missions": [
    {
      "title": "short, e.g. 'Place an order that needs manager approval'",
      "goal": "what to achieve in the app, plainly",
      "kind": "task | branch | area | rule",
      "why": "plain reason this matters",
      "priority": 1,
      "start_screen": "exact name from the known screens list to start from, or null to start from the home screen",
      "instructions": "concrete path guidance, e.g. 'On \\"Delivery type\\" choose \\"Express\\"', or null",
      "condition": "for any mission that tests a specific situation or choice: that situation in plain words, e.g. 'someone needs urgent help' — screens it uncovers are marked as only appearing then; else null",
      "expected": "what SHOULD happen, based on the confirmed summary, the user's answers and common sense — never just on what the app happened to do"
    }
  ]
}
Mission kinds:
- task: complete a key business task end to end (stop before final submit is handled for you).
- branch: take a different option at a choice point that probably changes the path — \
these find hidden screens. Make one mission per interesting option recorded under \
'branch points', the most business-relevant first.
- area: visit a part of the app not yet understood (from the summary or suspected hidden parts).
- rule: deliberately probe a business rule (e.g. enter an out-of-range value) to see how the app reacts.
Missions run one after another by priority. A mission that CREATES a record other missions need (e.g. placing an order, which gives an order number that 'track an order' needs) must get a higher priority than the missions that use it, and must be allowed to finish (it is a test environment when final saves are allowed).
Write 8 to 15 missions, priority 5 = most important. Respect the user's answers to the \
summary questions. No duplicates of what the first look already covered fully."""
)


async def plan_missions(
    brief: dict[str, Any],
    branch_points: list[dict[str, Any]],
    screens: list[dict[str, Any]],
    notes: str | None,
) -> list[dict[str, Any]]:
    user = (
        scope(brief)
        + (f"What the user told us: {notes}\n" if notes else "")
        + f"Confirmed App Summary (with the user's answers): {json.dumps(brief, ensure_ascii=False)[:30000]}\n"
        f"Branch points recorded during walk-throughs: {json.dumps(branch_points, ensure_ascii=False)[:10000]}\n"
        f"Known screens: {json.dumps(screens, ensure_ascii=False)[:20000]}"
    )
    reply = await ask_json(_MISSIONS_SYSTEM, user, model=THINKING_MODEL)
    missions = reply.get("missions")
    return (
        [m for m in missions if isinstance(m, dict) and m.get("goal")]
        if isinstance(missions, list)
        else []
    )


_JUDGE_SYSTEM = (
    STANCE
    + """

A mission has finished. Compare what SHOULD have happened (the expectation, from \
trusted sources) with what the app actually did (the steps and the final screen). \
Reply with ONLY:
{
  "matches": true,
  "summary": "one or two plain sentences: what happened in this mission",
  "difference": "if it does not match: what the app did differently and why that may be a bug; else null",
  "ask_user": "if it does not match: ONE short question (at most 30 words) a busy person can answer at a glance. Name the screen, what you did and what the app did — one difference only, the most important — and end with exactly 'Is that how it should work?' (the person answers 'It's a bug' or 'It's correct'). E.g. 'On Leave request I picked an end date before the start date, and the app saved it. Is that how it should work?'; else null",
  "created_record": {"what": "e.g. 'Order number'", "value": "exact identifier the app gave a record this mission created (shown on the final screen or in the steps), or null"}
}
A mismatch is always something the APP did. When Explorer itself stopped early, held \
back from pressing a button, or never did the step, that is not a mismatch: set matches \
to null. Only call it a mismatch when the app clearly failed the goal, showed something wrong, or \
broke something the user told us or basic common sense requires. Extras the expectation \
merely hoped for (more guidance, more details, more fields, a reference no trusted source \
promised) are NOT a mismatch — set matches to true. \
Judge only what the steps and screen actually show. If the mission could not get far \
enough to tell, set matches to null. Values that were never entered in these steps (a \
different person's name, answers from an earlier saved draft) are probably left over from \
an earlier attempt: set matches to null and say so, rather than calling it a bug. How it ended: 'final' means Explorer deliberately \
stopped before an action that needs the user's OK (e.g. delete, pay, approve, or any \
save on a live system) — never count what did not happen after that point as a bug; \
set matches to null if the expectation depends on it. 'done' means the goal was \
reached or could not be reached; 'stuck' means the app would not move on."""
)


async def judge_outcome(
    shot: bytes,
    goal: str,
    expected: str | None,
    history: list[str],
    ended: str,
    notes: str | None = None,
) -> dict[str, Any]:
    user = (
        f"Mission goal: {goal}\n"
        f"Expected: {expected or 'not stated — judge by common sense'}\n"
        + (
            "What the user has told us (trusted — it OVERRIDES the expectation above "
            f"wherever they disagree):\n{notes}\n"
            if notes
            else ""
        )
        + f"How it ended: {ended}\n"
        f"Steps taken: {' | '.join(history[-20:]) or 'none'}\n"
        "The screenshot shows the final screen."
    )
    return await ask_json(_JUDGE_SYSTEM, user, images=[shot], model=THINKING_MODEL)


_PLAN_TESTS_SYSTEM = (
    STANCE
    + """

Explorer has finished exploring the application. Write the test cases a senior QA lead \
would want for the screens you are given. For every LIST screen (a table or list of \
records) and every FORM screen (fields to fill in), go through the checklist below and \
write one test per item that applies to what that screen actually has. Skip an item \
only when the screen has nothing for it (no sortable column, no Export button, no \
paging, no Delete); never invent. Use the business name of the record (claim, customer, \
order), not "record". Put the item's ID in 'coverage'.
LIST screen checklist:
L-01 Page loads: the list renders with its main content and no failed data calls.
L-02 Columns shown: every column header is visible.
L-03 Data matches the server: rows shown match what the list's data call returned.
L-04 Total count: the total / paging count matches the data call's total.
L-05 Field formatting: dates, amounts and statuses are shown in a correct, readable format.
L-06 Empty state: a search or filter with no matches shows a clear "no records" message.
L-07 Search match: searching for a value from an existing row shows only matching rows.
L-08 Search clear: clearing the search brings the full list back.
L-09 Filter single: one filter shows only rows that satisfy it.
L-10 Filter combined: two filters show only rows that satisfy both.
L-11 Filter reset: Reset clears the filters and shows the full list.
L-12 Filter call: applying a filter makes the data call with that filter.
L-13 Sort ascending: clicking a sortable header sorts ascending.
L-14 Sort descending: clicking it again sorts descending.
L-15 Next / previous page: each loads the right page.
L-16 Page size: changing it shows that many rows per page.
L-17 No duplicates across pages: no row repeats or goes missing between pages.
L-18 Open a record: clicking a row or View opens that same record.
L-19 Edit from the list: Edit opens the form pre-filled with that row.
L-20 Delete then cancel: the row stays.
L-21 Delete then confirm: the row is gone and the count drops by one (needs the user's OK).
L-22 Add new: Add / New opens an empty form.
L-23 Export: Export downloads the rows of the current view.
FORM screen checklist:
F-01 Form loads: all fields are visible.
F-02 Defaults: a new form shows its default values.
F-03 Dropdown options: each dropdown offers the options the server provides.
F-04 Edit pre-fill: editing an existing record shows its saved values.
F-05 Required fields: submitting empty shows an error on each required field and saves nothing.
F-06 Invalid format: a bad email / phone / number / date shows a field-level error.
F-07 Max length: text beyond the limit is blocked or refused.
F-08 Min length: text below the minimum is refused.
F-09 Range: a number or date outside the allowed range is refused.
F-10 Error clears: fixing an invalid field removes its error.
F-11 Dependent field: changing a parent field updates its child (e.g. country -> states).
F-12 Conditional field: an option that shows or hides a field does so.
F-13 Create success: valid data saves with a success message (the save call succeeds).
F-14 Saved data correct: reopening the saved record shows what was entered.
F-15 Appears in the list: the new record shows in its list with the right values.
F-16 Update success: editing and saving shows the change on reopening.
F-17 Cancel: filling in and pressing Cancel saves nothing.
F-18 Reset: Reset returns the form to its defaults.
F-19 Double submit: pressing Submit twice quickly creates only one record.
F-20 Server error: when saving fails, a clear message shows and the entered data stays \
(only when the screen itself offers a way to make the save fail; Explorer cannot break \
the server).
Beyond the checklist, add what only Explorer knows, each linked to the closest checklist \
item with 'linked_to': the user's answers and confirmed rules, choices that lead to \
hidden screens, and the possible bugs already noticed. Their 'coverage' is "X-" plus a \
short name (e.g. "X-Urgent injury guidance").
Other screens (dashboards, details, wizard steps): the page loads with its main content \
(coverage "P-01 Page loads"), its links and tabs lead to the right screen, Back and \
Refresh keep the user in place.
Sign-in (only when you are asked to plan sign-in tests and the app has a sign-in \
screen): signing in with the saved login works; a wrong username or password is refused \
with a clear message; required sign-in fields; a protected screen opened while signed \
out sends the visitor to sign in; signing out ends the session. Mark these \
"signed_out": true. They run in a browser that has not signed in: to sign in, they type \
exactly {{username}} and {{password}}; a wrong login uses a made-up username, never the \
saved one. A protected-screen test starts on the protected screen itself. Every other \
test is "signed_out": false and must never sign in or out.
Every test is one of these 5 kinds:
- navigation: menus, links, tabs, Back, Refresh and direct addresses take the user to \
the right screen.
- validation: a field rule (required, format, range, length, cross-field) is enforced \
with a clear message.
- error_state: what the user sees when something goes wrong or there is nothing to show \
(not found, rejected, duplicate, empty list, cannot continue).
- data_load: lists, searches, sorting, filters and details show the right information, \
also after a refresh.
- form_submission: completing a form or task works and the result is kept/confirmed.
Reply with ONLY:
{
  "tests": [
    {
      "kind": "navigation | validation | error_state | data_load | form_submission",
      "title": "short and specific, e.g. 'Email is required on New lead'",
      "coverage": "checklist ID and name, e.g. 'F-05 Required fields', or 'X-<short name>' for Explorer's own",
      "linked_to": "for an X- test: the closest checklist ID, e.g. 'F-12'; else null",
      "signed_out": false,
      "purpose": "one plain line: why this test exists",
      "technique": "e.g. boundary value, equivalence class, state transition, happy path, error guessing",
      "business_thing": "e.g. Lead",
      "start_screen": "EXACT name from the known screens list where the test begins",
      "steps": ["plain steps a person would follow"],
      "how_to_run": "precise instructions for the browser agent, e.g. 'Leave Email empty and press Save lead'",
      "expected": "what SHOULD happen, from the confirmed summary, the user's answers or common sense",
      "trust": "confirmed | standard | seen",
      "rule": "the rule being tested in plain words"
    }
  ]
}
Rules:
- Every test must start on a screen from the known screens list and only use fields \
and buttons that screen actually has. Do not invent screens, fields or messages.
- 'trust': confirmed = backed by the user's answers/notes; standard = common sense or \
industry norm; seen = only because the app did it (avoid these where possible).
- One purpose per test: ONE action (or one short sequence to reach it) and ONE visible \
outcome. Never "all links work", "every filter shows the right rows" or "open X and \
press Back for each": write one test per link, per filter value, per Back. Each test \
must be useful on its own: it would fail if that part of the app broke. No duplicates, \
no tests that only re-check what another test already proves.
- Everything the user asked for or confirmed (their notes, answers and documents) gets \
at least one test, marked trust "confirmed" — write these first.
- Every screen you are given gets its tests; business-critical screens first. Skip a \
test that would only repeat what another proves.
- A test proves its outcome by text it shows, its address, or a data call the page \
makes (checklist items about the server). Leave out layout, speed, console and \
accessibility checks (Explorer reports those separately).
- Use the user's test data (e.g. account or reference numbers) where needed.
- Describe dates relative to today in 'how_to_run' ('tomorrow', '30 days ago'), never as \
fixed dates or 'one minute from now': tests are replayed on later days."""
)


async def plan_tests(
    brief: dict[str, Any],
    screens: list[dict[str, Any]],
    links: list[str],
    missions: list[dict[str, Any]],
    possible_bugs: list[str],
    notes: str | None,
    *,
    may_save: bool = False,
    approved: list[str] | None = None,
    only: list[str] | None = None,
    sign_in: bool = True,
) -> list[dict[str, Any]]:
    user = (
        (f"Write tests ONLY for these screens: {', '.join(only)}\n" if only else "")
        + (
            "Plan the sign-in tests too.\n"
            if sign_in
            else "Do not plan sign-in tests (they are planned elsewhere).\n"
        )
        + 
        scope(brief)
        + (f"What the user told us: {notes}\n" if notes else "")
        + (
            "This is a test environment: tests may press final Save/Submit buttons, "
            if may_save
            else "This is NOT a test environment: tests can never press a final Save or "
            "Submit button, "
        )
        + "and never anything that moves money, buys, sells, pays, transfers, cancels, "
        "deletes or changes a password (those always wait for a person). Do not plan tests "
        "that need such a press, except validation tests where the app rejects the input "
        "before anything is saved.\n"
        + (
            "Exception — the user approved pressing these buttons on this test environment, so "
            "plan tests that press them, including the task completed end to end with its "
            f"result checked: {json.dumps(approved, ensure_ascii=False)}\n"
            if approved
            else ""
        )
        + f"Confirmed App Summary: {json.dumps(brief, ensure_ascii=False)[:20000]}\n"
        f"Known screens: {json.dumps(screens, ensure_ascii=False)[:40000]}\n"
        f"Ways between screens: {json.dumps(links, ensure_ascii=False)[:8000]}\n"
        f"Missions and what happened: {json.dumps(missions, ensure_ascii=False)[:12000]}\n"
        f"Possible bugs already noticed: {json.dumps(possible_bugs, ensure_ascii=False)[:6000]}"
    )
    reply = await ask_json(_PLAN_TESTS_SYSTEM, user, model=THINKING_MODEL)
    tests = reply.get("tests")
    return [t for t in tests if isinstance(t, dict)] if isinstance(tests, list) else []


_REVIEW_PLAN_SYSTEM = (
    STANCE
    + """

Before any scenario is tried in the app (each try costs minutes), review the planned \
scenarios against what exploring actually saw. Reply with ONLY:
{"leave_out": [{"index": 0, "why": "duplicate", "of": 3, "reason": "one plain sentence"}]}
why is "duplicate" or "never_seen". Leave a scenario out ONLY when you are certain:
- duplicate: it checks the SAME thing on the same screen as an earlier scenario (`of` is \
that earlier index) — the same rule with the same kind of input, only worded differently. \
Different values, rules, fields or outcomes are NOT duplicates (a 9-digit and an 11-digit \
phone number are two scenarios).
- never_seen: carrying it out needs a screen, step, button or option that the screens, the \
ways between them and the missions never showed (e.g. it expects a form to open after a \
step where the map shows a different screen). An expected RESULT that may differ from what \
the app does is NOT a reason — finding that difference is the point of testing.
When in doubt, keep it. Most plans have few or none to leave out."""
)


async def review_plan(
    tests: list[dict[str, Any]],
    screens: list[dict[str, Any]],
    links: list[str],
    missions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Planned scenarios to leave out before trying them: duplicates, and
    ones that need a flow exploring never saw. Index into `tests`."""
    plan = [
        {
            "index": i,
            "screen": t.get("start_screen"),
            "title": t.get("title"),
            "how": t.get("how_to_run"),
            "expected": t.get("expected"),
        }
        for i, t in enumerate(tests)
    ]
    user = (
        f"Known screens: {json.dumps(screens, ensure_ascii=False)[:40000]}\n"
        f"Ways between screens: {json.dumps(links, ensure_ascii=False)[:8000]}\n"
        f"Missions and what happened: {json.dumps(missions, ensure_ascii=False)[:12000]}\n"
        f"Planned scenarios: {json.dumps(plan, ensure_ascii=False)[:60000]}"
    )
    reply = await ask_json(_REVIEW_PLAN_SYSTEM, user, model=THINKING_MODEL)
    out = reply.get("leave_out")
    return [d for d in out if isinstance(d, dict)] if isinstance(out, list) else []


_CHECK_SYSTEM = (
    STANCE
    + """

A test case was just carried out in the app. Look at the final screen and decide what \
proves the outcome. Reply with ONLY:
{
  "observed": "what the app actually did, in one plain sentence",
  "matches_expected": true,
  "set_up_ok": true,
  "check": {"kind": "text_visible | url_contains | api_call", "value": "for api_call: the method and a stable part of the address of one listed data call that proves the outcome, e.g. 'POST /api/claims' (no record ids or dates); for text_visible: an EXACT short piece of text visible on the final screen (copy it character for character, e.g. the validation message or the heading of the screen reached); for url_contains: a distinctive part of the screen address"}
}
Rules:
- Never use text that changes from run to run (a reference or order number the app just generated, today's date or time, a count that grows): replays would fail. Use the stable message or heading around it instead (e.g. 'Claim submitted', not the claim number).
- Use api_call when the test is about the server (data matches, filter call, save / \
update / delete succeeded) and a listed data call proves it; else prefer what the \
screen shows.
- The check must prove THIS test's outcome — e.g. the error message for a validation \
test, the new screen's heading for a navigation test — not something that is always \
on screen (like the app name or menu).
- matches_expected: true if the app did what it should; false if it did something \
different (that is a possible bug — the check then proves what it does today); null \
if the test could not be carried out far enough to tell. Only false when the app \
clearly got it wrong; wording or extras the expectation merely hoped for (a longer \
message, more details) that no trusted source requires are NOT a difference: true.
- set_up_ok: false when the TEST failed to do its own part, so the result says nothing \
about the app — a value it meant to enter never showed in the field, a field it meant to \
leave empty was already filled in by the app, a date it meant to be in the past is \
actually after today, a failure or condition it needed (a server error, an empty list) \
never happened, or it never reached the screen being tested. Otherwise true."""
)


async def decide_check(
    shot: bytes,
    inventory: dict[str, Any],
    test: dict[str, Any],
    history: list[str],
    rejected: list[str] | None = None,
    calls: list[tuple[str, str, int]] | None = None,
) -> dict[str, Any]:
    seen = [
        f"{m} {urlsplit(u).path}{'?' + urlsplit(u).query if urlsplit(u).query else ''} -> {st}"
        for m, u, st in (calls or [])
    ][-30:]
    user = (
        (f"Data calls the page made during the test: {seen}\n" if seen else "")
        + 
        (
            "These proofs were rejected because they were ALREADY true before the test did "
            "anything, or are a data call the app makes on many steps (e.g. saving progress "
            f"on every Continue) — pick something only THIS test's outcome causes: {rejected}\n"
            if rejected
            else ""
        )
        + f"Today is {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n"
        + f"Test: {test.get('title')}\n"
        f"Kind: {test.get('kind')}\n"
        f"Expected: {test.get('expected')}\n"
        f"Steps carried out: {' | '.join(history[-15:]) or 'none'}\n"
        f"Machine reading of the final screen:\n{_compact_inventory(inventory)}"
    )
    return await ask_json(_CHECK_SYSTEM, user, images=[shot], model=THINKING_MODEL)
