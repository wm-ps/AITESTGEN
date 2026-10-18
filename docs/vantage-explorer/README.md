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

The Explorer tab sits in each application's sidebar, next to Journeys, with a Beta pill. It has four views:
- **Live:** stage progress, counters, a live browser view and the "What Explorer is thinking" feed.
- **App Summary:** the summary to edit, answer questions on, and confirm.
- **Screens:** the screens Explorer understood, with screenshots and hints about hidden parts.
- **Health:** the health score and the problems found, each with a "See screen" button.

## Stage 2 (built): missions, app map and recordings

After you **confirm the App Summary**, Explorer plans a **Mission Board** of 8–15 goals:
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

You can **add your own missions** in plain words, or **skip** missions. A mission cut off by a worker restart goes back in the queue once.

New views:
- **Missions:** the board (Up next, Exploring now, Finished, Skipped). Each card shows what it should do, the verdict, new screens found, and **Watch recording**, a video with captions synced to Explorer's thoughts.
- **App map:** every screen and the ways between them. Hidden screens have dashed borders and an "appears when…" note. Click a screen for its details.
- **Live:** while missions run, one small live browser per running mission, plus counters for hidden screens found and missions finished.

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
- The **Questions** tab holds the open questions and "What Explorer knows".

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

Sign in → look around → health check and App Summary → **you confirm** → Mission Board → hidden-screen hunt → breadth checks → proven test cases → highlight video.

## Running it

`scripts/dev-start.sh` / `scripts\dev-start.cmd` now also start the Explorer worker. To start it by hand:

```
uv run --env-file .env --package explorer-worker python -m explorer_worker.worker
```

Then open an application, go to **Explorer**, and press **Start exploring**. Put any test data in the notes box, for example "use policy number POL-10001".

| Setting | Default | What it does |
|---|---|---|
| `EXPLORER_THINKING_MODEL` | `gpt-5.6-sol` | Reading screens, walking tasks, writing the summary |
| `EXPLORER_FAST_MODEL` | `gpt-5.6-luna` | Choosing where to look next |
| `EXPLORER_FIRST_LOOK_SCREENS` | `24` | How many distinct screens to understand |
| `EXPLORER_FIRST_LOOK_MINUTES` | `25` | Time limit for the first look |
| `EXPLORER_MISSION_STEPS` | `20` | Most steps a single mission takes |
| `EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES` | `8` | Browser jobs in parallel per worker (each run uses up to 3 for missions) |

## Code map

- `packages/explorer_core`: Explorer's own tables, all prefixed `explorer_`. The migrations are `e7a1c3b5d9f2` (Stage 1), `f3b5d7e9a1c4` (Stage 2), `a4c6e8f0b2d5` (Stage 5), `b5d7f9a1c3e6` (Stage 4) and `c6e8a0b2d4f7` (Stages 6–7).
- `apps/workers/explorer`:
  - `understand.py`: the look-around loop
  - `mind.py`: reading and remembering each screen, map edges
  - `pursue.py`: going after a goal step by step (walk-throughs and missions)
  - `missions.py`: Mission Board planning, running, judging and recordings
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
- `apps/api/src/api/explorer.py`: the `/explorer/...` endpoints.
- `apps/web/src/explorer/`: the Explorer tab.

The classic discovery and scenario code is untouched. Explorer only reads the `application` row and its saved login.

## Still to come

**Stage 8**, Explorer replacing the old discovery, only happens with your approval (PLAN.md §9).

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

Explorer UI (`apps/web/src/explorer/`):

1. **What it learned → "What you told Explorer" and "Teach Explorer".** The
   design needs work, and the two panels don't end at the same height.
2. **Things that look wrong.** Add a "False alarm" option. The screen is too
   dense: show the same information without scrolling.
3. **Screens to cover.** Remove the "pending" state; it isn't needed.
4. **Search input.** Make it match the other input fields.
5. **Questions.** Replace the separate tab with a button that shows a
   notification when there are questions and opens them in a tidy dialog.
6. **Tab order.** "What it learned" comes right after Live.
7. **Tab order.** Scenarios is the last tab.
8. **Tabs.** The tab bar is uneven; use a better tabs component.
9. **Questions for you.** Make them simple to read, and always offer an
   "Other" option with a text box.
10. **Labels like "Press icon to contact details"** (seen on FNOL) don't make
    sense to a reader. Name what the button is for, in plain words.
11. **Screens tab.** Remove "something looks wrong" there. It isn't clear, and
    "things that look wrong" already covers it.
12. **Screens tab order.** Show screens in the order Explorer found them (sign
    in can't be last).

Explorer worker:

13. **Feed self-healing.** Healing relies on the database's `component`,
    `component_locator` (buttons and how to find them), `form` and
    `form_field` (fields and their input types). Have Explorer save this data
    for the screens it learns, so healing finds what it expects. Persist only;
    Explorer's own logic stays the same.
14. **Debug logging for model calls.** Log each phase as it starts and ends,
    each model call (what it asks for), and a short form of what came back,
    so a run can be followed and debugged from the worker log.
