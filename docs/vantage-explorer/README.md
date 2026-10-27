# Vantage Explorer — what's built and how to run it

The plan is in [PLAN.md](PLAN.md). This page covers what exists today.

## Stage 1 (built): "Get to know the app"

Explorer studies an application the way a new QA engineer would:

1. **Signs in** with the application's saved login. It also works for apps with no login.
2. **Looks around with purpose.** It reads every screen it visits (screenshot plus a reading of the page) and names each screen by what it *means*, so 1,000 customer pages count as one screen. GPT-5.6 chooses where to look next by business importance, not link order.
3. **Walks through tasks.** When a screen offers a business task (for example "Report a claim" or "Add employee"), Explorer goes through it step by step:
   - It fills each step with your test data, given on the Start card, or with realistic made-up data.
   - It writes down every choice that probably changes the path (hidden branches).
   - It **stops before anything that would send, save, pay or delete for real.**
   - It notes data it can't invent ("I'll need this from you").
4. **Checks app health.** It records crashes, server errors, hidden errors, broken links and slow screens. These make up the 0–100 health score. Below 60, Explorer switches to "requirements-first" mode.
5. **Doesn't trust the app blindly.** Things that break common sense (impossible dates, contradictory screens, a progress bar on the wrong step) are recorded as **Possible bugs**. They are never treated as correct behavior.
6. **Writes the App Summary.** This covers who uses the app, the main business things and their statuses, key tasks, the rules it expects (each with a trust label), the parts that may only appear sometimes, and multiple-choice questions for you. You review it, edit it, and press **Confirm**.

### The UI

The Explorer tab sits in each application's sidebar, next to Journeys, with a Beta pill. Its tab bar (equal-width tabs; the arrow keys move between them) has four views:
- **Live:** stage progress, counters, a live browser view, the missions, and the "What Explorer is thinking" feed.
- **What it learned:** the App Summary to edit, answer questions on (each has an **Other** choice with a text box) and confirm; then "What you told Explorer" and "Teach Explorer" side by side; then **Things that look wrong**, folded.
- **Screens:** the screens Explorer understood, in the order it found them (sign-in first), with screenshots and where each button leads.
- **Scenarios:** the proven and known-bug test cases.

The **Questions** button in the header shows how many questions are open and pulses when Explorer is waiting on you. It opens the questions in a dialog.

## Stage 2 (built): missions, app map and recordings

After you **confirm the App Summary**, Explorer plans a **Mission Board** of 6–15 goals (more for bigger apps):
- **Key tasks:** complete a business task end to end.
- **Hidden branches:** take a different choice that probably changes the path, such as "someone needs urgent help".
- **New areas:** parts of the app not yet seen.
- **Rule checks:** deliberately test a business rule.

Each mission writes down what *should* happen. That expectation comes from your answers, the summary and common sense, never from the app.

Up to **3 missions run at once**, each in its own **recorded** browser:
- Screens a mission uncovers under its situation are marked **hidden screens**, with "appears when…".
- When a mission finishes, its outcome is compared with what should have happened. A mismatch becomes a **Possible bug**.
- On **test environments** (non-production), missions may press Save, Submit or Create so they can make their own test data.
- Delete, pay, approve, reject, cancel and sign-out are **never** pressed without your OK.
- On production apps, nothing is ever saved.

**Follow-up missions.** The board is planned from the first look, which can't see past screens that need data (a policy number, say). So when a mission reaches a screen the plan didn't know about, it queues a follow-up for each choice there it didn't try ("Try 'Pick up where I left off' on Resume claim report"), and one to carry on from the form or wizard step it stopped on because its own goal was met ("Carry on from Claim type"). A follow-up gets there by replaying the recorded clicks (your answers included). Nothing is repeated, and a run has at most 15 missions; what doesn't fit is listed in the feed as "Not explored".

You can **skip** missions from Live. Adding your own missions in plain words works through the API (`POST /explorer/runs/{id}/missions`); the tab has no button for it yet. A mission cut off by a worker restart goes back in the queue once.

Where it shows: **Live** lists the missions (Up next, Exploring now, Finished) with one small live browser per running mission; **Screens** shows every screen and, per screen, what each button leads to. Mission recordings are stored and served (`GET /explorer/missions/{id}/recording`) but not played in the tab yet.

## Stage 3 (built): hunting hidden screens

After the missions, Explorer revisits screens it knows and tries to make hidden parts appear:
- **Choices:** it picks each option of every dropdown and radio group and watches which new fields appear.
- **Amounts:** it tries small to very large numbers and watches for new sections or messages.
- **What the server sends back:** inside its own browser only, it pretends the server returned *nothing*, *an error* or *optional features switched on*, or that it is *a year from now*. These are labelled **Simulated**, and the real server is never touched.

Each discovery is a hidden screen on the App Map with its "appears when…" condition. If a screen goes blank when the server fails, that becomes a possible bug.

## Stage 4 (built): questions and memory

- Explorer asks when it needs **test data** it can't make up, when the next step needs **your OK** (approve, delete, pay…), or whether something it saw is **correct or a bug**.
- **Only the mission that asked waits**, with its browser open. Everything else keeps going, and your answer lets it continue where it stopped.
- **Memory per app:** your answers, facts you add and **documents you upload** (PDF, Word, text) are trusted knowledge in every prompt, in this run and every future one.
- Explorer checks memory before asking, so it never asks twice. Answers to the App Summary questions are saved when you confirm.
- Answering "correct" to a possible bug turns it into the agreed rule. Answering "bug" confirms it.
- The **Questions** button opens the open questions in a dialog. A question with choices also has **Other**, which opens a text box for your own answer. What Explorer knows is on **What it learned**.
- In **Things that look wrong**, each finding shows its screenshot, detail and answers at once. **False alarm** takes it off the list, closes its "is this a bug?" question and remembers the behaviour as correct (`POST /explorer/health/{id}/false-alarm`).

## Stage 5 (built): proven test cases

Tests come only in 5 kinds: navigation, validation, error states, data load and form submission. For each test, Explorer:
1. **Plans** it from what it actually saw. Tests that name screens it never saw are dropped.
2. **Builds** it by doing it once in a browser, recording the exact clicks and typing.
3. **Picks a proof** that appears on screen as a result: a message, a heading or an address. A proof that was already on screen before the test acted is rejected.
4. **Proves** it by replaying the recorded steps **3 times without any AI** (the proof must hold every time), then once with the key step removed (the proof must disappear).
5. When the app does something different from what *should* happen, keeps it as a **Known bug** (`test.fixme` with expected vs actual), never as correct behavior.

The **Test cases** tab has a coverage grid (business area × kind), steps, expected result with its trust label, the proof, a proof video and Playwright code. **Download all tests** gives a ready-to-run Playwright project.

## Stage 6 (built): breadth

- **Who can see what:** add other kinds of users (with their logins, kept in the secrets store) on the Start card or the Report. Explorer tries every known screen as each of them and builds an access chart.
- **Pages nothing links to:** it reads the app's own code for page addresses and visits the ones no menu leads to. These are marked as hidden screens.
- **Code-coverage radar:** it reports how much of the app's code ran while visiting everything it knows, and names business-sounding parts that never ran.
- **Faster re-runs:** a new run starts from the previous run's map and only looks for what's new (`EXPLORER_REVISIT_SCREENS`, default 10).

## Stage 7 (built): report and highlight video

- **Report tab:**
  - headline numbers;
  - the **highlight video**: the best moments, with title cards and captions, rendered to MP4 with ffmpeg;
  - possible bugs, test coverage by kind, hidden screens, the access chart and code that never ran.
- **Download report:** one self-contained HTML page, screenshots included, that a client can open anywhere.
- **Download video:** the MP4.

## The whole run

Sign in → look around → health check and App Summary → **you confirm** → Mission Board (plus follow-up missions) → hidden-screen hunt → breadth checks → proven test cases → hand-off to Vantage's Journeys, Scenarios and Test cases → highlight video.

## Running it

`scripts/dev-start.sh` / `scripts\dev-start.cmd` now also start the Explorer worker. To start it by hand:

```
uv run --env-file .env --package explorer-worker python -m explorer_worker.worker
```

Then open an application, go to **Explorer**, and press **Start exploring**. Give test data under **What it learned → Teach Explorer → Facts and test data**, for example "use policy number POL-10001". It is used in every run of that app. (The API also takes `notes` when a run starts; the Start card has no box for them.)

The worker log shows each phase as it starts and ends, and every model call: the model, what it asks for, and a short form of the reply with how long it took.

| Setting | Default | What it does |
|---|---|---|
| `EXPLORER_THINKING_MODEL` | `gpt-5.6-sol` | Reading screens, walking tasks, writing the summary |
| `EXPLORER_FAST_MODEL` | `gpt-5.6-luna` | Choosing where to look next |
| `EXPLORER_FIRST_LOOK_SCREENS` | `24` | How many distinct screens to understand |
| `EXPLORER_FIRST_LOOK_MINUTES` | `25` | Time limit for the first look |
| `EXPLORER_MISSION_STEPS` | `20` | Most steps a single mission takes |
| `EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES` | `8` | Browser jobs in parallel per worker (each run uses up to 3 for missions) |

## Code map

- `packages/explorer_core`: Explorer's own tables, all prefixed `explorer_`. The migrations are `e7a1c3b5d9f2` (Stage 1), `f3b5d7e9a1c4` (Stage 2), `a4c6e8f0b2d5` (Stage 5), `b5d7f9a1c3e6` (Stage 4), `c6e8a0b2d4f7` (Stages 6–7) and `d7f9b1c3e5a8` (who started a run); `362ae149aa7c` merges them with the discovery branch and is the head.
- `apps/workers/explorer`:
  - `understand.py`: the look-around loop
  - `mind.py`: reading and remembering each screen, map edges
  - `pursue.py`: going after a goal step by step (walk-throughs and missions)
  - `missions.py`: Mission Board planning, running, judging, follow-up missions and recordings
  - `brain.py`: prompts
  - `browser.py`: the browser layer
  - `sense.py`: pure rules, unit-tested
  - `session.py`: signed-in browser
  - `workflow.py`: the run: understand, wait for confirm, mission pool, hunt, breadth, tests, video
  - `memory.py`: questions and per-app memory
  - `hunt.py`: hidden-screen hunting (choices, amounts, simulated server answers)
  - `breadth.py`: roles, unlinked pages, code coverage
  - `tests_stage.py` and `testkit.py`: planning, building, proving and exporting tests
  - `reel.py`: the highlight video
  - `promote.py`: the hand-off to Vantage (Journeys, Pages, Scenarios, and the components and forms self-healing reads)
- `apps/api/src/api/explorer.py`: the `/explorer/...` endpoints.
- `apps/web/src/explorer/`: the Explorer tab.

Explorer is Vantage's discovery: onboarding starts an Explorer run (`EXPLORER_REPLACES_DISCOVERY`, on by default), and at the end of a run `promote.py` writes its results into the classic tables (`journey`, `journey_step`, `page`, `scenario`, plus `component`, `component_locator`, `form` and `form_field` for self-healing). Re-runs retire Explorer's earlier rows instead of deleting them.

## Still to come

**Stage 8**, Explorer replacing the old discovery (PLAN.md §9), is switched on in the code: onboarding starts Explorer and its results land in Journeys, Scenarios and Test cases (see the code map). PLAN.md §10's side-by-side comparison with the old discovery, meant to come before that switch, has not been done. `EXPLORER_REPLACES_DISCOVERY=0` turns the switch off.

The highlight video needs ffmpeg and a font on the machine running the worker. When either is missing, Explorer skips the video and says so in the feed.

## To do (decisions pending)

- **Auto-heal on Explorer's tests.** Vantage's auto-heal currently skips only
  Explorer known-bug tests (`execution_worker/activities.py`,
  `_load_heal_context_sync`). On 2026-10-18 it rewrote a working, proven
  OrangeHRM test ("Valid candidate is saved"), and the rewrite failed its
  typecheck. Decide whether auto-heal should skip every test Explorer has
  proven (`scenario.grounding.proven_code`). A failure would then mean the app
  or its data changed, and the fix would be a fresh Explorer run.
- **Checklist items without full API proof.** "Nothing was saved" items
  (F-05, F-17, L-20) are proven by what the screen shows, not by checking that
  no data call was made. "Data matches the server" items (L-03, L-04, L-17)
  are not compared row by row against the response.
- **Older crawler tests.** Apps onboarded before Explorer still carry the
  crawler's test cases next to Explorer's (Sales vision: 55). Decide whether to
  retire them.

## To do next (from the 2026-10-18 review)

All 14 done (2026-10-19 to 2026-10-21).

Explorer UI (`apps/web/src/explorer/`):

1. ✅ **"What you told Explorer" and "Teach Explorer"** are the same width and
   height, and each says so when it's empty.
2. ✅ **Things that look wrong** has a **False alarm** option, and shows each
   finding's screenshot, detail and answers in a compact grid with nothing to
   expand.
3. ✅ **Screens to cover: no "pending" state.** Already true in the committed
   code: screens have no status (a screen shows once Explorer reaches it),
   and no "pending" mark exists anywhere in the Explorer tab.
4. ✅ **Search input** looks like every other field.
5. ✅ **Questions** moved from a tab to a header button with a count that
   pulses when Explorer is waiting; it opens a dialog.
6. ✅ **Tab order:** "What it learned" comes right after Live.
7. ✅ **Tab order:** Scenarios is last.
8. ✅ **Tabs:** equal-width segmented tabs that don't shift; arrow keys move
   between them.
9. ✅ **Questions for you** are numbered and easier to read, and every question
   (in the summary and during a run) offers **Other** with a text box.
10. ✅ **Plain-word button names.** The shared prompt asks the model to name a
    button by what it is for, never by its icon; the Screens map drops icon
    text and calls a bare icon "an unlabelled button".
11. ✅ **Screens tab:** "Something looks wrong" is gone.
12. ✅ **Screens tab order:** the order Explorer found them, sign-in first.

Explorer worker:

13. ✅ **Feed self-healing.** At hand-off, each screen's Page also gets a
    `component` + `component_locator` (role locator, text fallback) per
    button/link, and a `form` with a `form_field` per field (input type,
    required), in the classic crawler's shape. Persist only.
14. ✅ **Debug logging for model calls**, and phase start/end, in the worker
    log.

## To do next: fewer dropped scenarios (brainstormed 2026-10-18)

**Where we are.** Across the four apps tested on 2026-10-18 (Keystone FNOL,
Digital Banking, Sales vision, OrangeHRM), 141 scenarios were dropped. That
excludes the ones trimmed to keep runs short and the ones you chose to ignore.
About 40–57% of planned scenarios became tests.

| Reason | Count | Share |
|---|---|---|
| Couldn't carry it out far enough | 69 | 49% |
| Still passed with its key step removed | 32 | 23% |
| No reliable proof on the screen | 16 | 11% |
| Proof was already on screen before the test acted | 14 | 10% |
| Different results on repeat runs | 9 | 6% |
| Couldn't set up what it needed | 1 | 1% |

To see the current numbers:

```sql
select split_part(split_part(drop_reason, ':', 1), ' (', 1), count(*)
from explorer_test_case
where status = 'dropped'
  and drop_reason not in ('Left out to keep the run short', 'Ignored by you')
group by 1
order by 2 desc;
```

### 15. Measure the fixes already made (do this first)

These went in on 2026-10-18 but have not run end to end yet:

- Type-ahead fields pick the matching suggestion (`browser._pick_suggestion`).
- Custom drop-downs are found by their caption (`browser.choose`).
- Scenarios may take 20 steps instead of 12 and must finish every step before
  stopping (`tests_stage.build_and_prove`).
- A second press of Save/Submit no longer fails (`testkit.playwright_code`).
- The scenario judge no longer counts missing extras as bugs.
- F-20 is planned only when the screen itself can make the save fail.

Re-run OrangeHRM (it had the most "couldn't carry it out" drops) and compare
with the table above. Success: that row falls well below 49%.

### 16. "Couldn't carry it out far enough" (49%)

The agent stops before the outcome is on screen. Causes seen in the drop
reasons, and ideas for each:

- **Icon-only buttons on table rows** (edit, view, delete with no text): the
  model can't name them, so it can't open a record (L-18, L-19, F-04, F-14).
  - Option A: the machine reading of a screen also lists unlabelled buttons by
    their `title`, `aria-label`, icon class or tooltip, and their row
    ("row 1: pencil icon").
  - Option B: a "click the Nth row's icon button" action, recorded with a
    stable locator such as `row.getByRole('button').nth(k)`.
  - A is cheaper; B is more reliable. Start with A, add B if needed.
- **Date boxes with placeholders or a fixed format** ("yyyy-dd-mm"): the
  agent's dates are refused. Read the format from the placeholder (or the
  `pattern` attribute) and convert the date before typing. Look for the
  existing date-to-app-format conversion in `browser.fill_field` (it uses
  `resolve_relative` and `_type_into_picker`) and extend it.
- **The agent says "done" too early.** Its instructions now say to finish
  every step first. Also check the planned "how to run" against what was
  done: if a step the plan names ("press Save") never happened, keep going
  instead of stopping.
- **One retry may not be enough.** Today a scenario that falls short gets one
  more try with the lesson from the first. Consider a second try only when
  the first retry got further (more steps matched the plan).
- **Measure by cause.** Add a short `cause` tag to each drop: control,
  early stop, out of steps, navigation. Then the next fix can target the
  biggest bucket.

### 17. "Still passed with its key step removed" (23%)

Explorer replays each test with one step left out, to prove it would catch a
broken app. Today it removes **only the last action**
(`testkit.without_decisive_step`). In a validation test with several fields,
that last action is often one more field, not the step that matters, so a
good test is dropped.

- Option A: try removing each of the last two or three actions. Drop the test
  only if it still passes with every one of them removed. This costs up to
  three extra replays per test.
- Option B: ask the model which step decides the outcome when the proof is
  chosen (`brain.decide_check`), and remove that one.
- Option C: by kind of test. For validation, remove the bad value or the
  empty field. For navigation, remove the click that leads away. For
  form_submission, remove the Save.

C is cheap and needs no model call; B is the fallback for anything else.
Keep the rule that a test which proves nothing is still dropped.

### 18. Proof problems (21%: "no reliable proof" plus "proof already on screen")

- Use the data-call proof (`api_call`) more, for checklist items about the
  server. The page's calls are already recorded.
- When the first proof candidate was already on screen, the proof picker
  gets up to three tries today. Show it what changed between the screen
  before and after the test, so it picks text that only the test caused.
- For "no reliable proof": check a few seconds later before giving up. Some
  messages fade in or arrive after a data call.

### 19. Different results on repeat runs (6%)

Mostly shared demo data that other people change (OrangeHRM's public demo).
Prefer proofs that don't depend on specific records (a heading or message,
not "row 3 is John"). Note in the scenario when the data is shared, so
Test cases can show "may be affected by other users' changes".
