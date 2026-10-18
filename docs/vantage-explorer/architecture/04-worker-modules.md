# 4. Worker modules: who is responsible for what

All paths are under `apps/workers/explorer/src/explorer_worker/` unless stated otherwise.

## Map by stage

| Stage | What it does | Modules |
|---|---|---|
| Plumbing | Process, workflow, activities, DB, model client | `worker.py`, `workflow.py`, `activities.py`, `db.py`, `llm.py` |
| Shared foundations | Browser, sign-in, reading screens, prompts, pure rules, journaling, memory | `browser.py`, `session.py`, `mind.py`, `brain.py`, `sense.py`, `journal.py`, `memory.py` |
| 1 · Get to know the app | First look, health, App Summary | `understand.py` |
| 2 · Missions | Plan, run, judge, record | `missions.py`, `pursue.py` |
| 3 · Hidden screens | Choices, amounts, simulated server answers | `hunt.py` |
| 4 · Questions and memory | Ask once, remember forever | `memory.py` |
| 5 · Proven tests | Plan, build, prove, export code | `tests_stage.py`, `testkit.py`, `quality.py`, `samples.py` |
| 6 · Breadth | Roles, unlinked pages, code coverage | `breadth.py` |
| 7 · Highlight video | ffmpeg MP4 | `reel.py` |
| 8 · Hand-off | Into Journeys and Scenarios | `promote.py` |
| Resume | Restart from saved rows | `resume.py` |

---

## Plumbing

### `worker.py`

Connects to Temporal (`TEMPORAL_ADDRESS`, default `localhost:7233`) and registers `ExplorerRunWorkflow` plus 16 activities on `explorer-task-queue`. `max_concurrent_activities` comes from `EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES` (default 8). Each run uses up to 3 at once for missions or tests.

### `workflow.py`

Orchestration only. See [document 3](03-technical-flow.md).

### `activities.py`

Thin wrappers that turn every crash into a visible outcome (failed run, failed mission, or dropped test) and never into a silent hang. `build_test_activity` retries once internally after about 60 s.

### `db.py`

Its own SQLModel engine on `DATABASE_URL`. The worker is a separate deployable from the API.

### `llm.py`

The Explorer-only GPT-5.6 client, which calls LiteLLM `/chat/completions`.

- `ask_json(system, user, images=None, model=THINKING_MODEL)` always sets `response_format={"type": "json_object"}`. Images are sent as base64 JPEG data URLs.
- The httpx timeout is 240 s. It makes 3 attempts, backing off 2, 4 and 6 s.
- `_parse_json` strips code fences and takes the text from the first `{` to the last `}`.
- `THINKING_MODEL = EXPLORER_THINKING_MODEL` (`gpt-5.6-sol`). `FAST_MODEL = EXPLORER_FAST_MODEL` (`gpt-5.6-luna`).

---

## Shared foundations

### `browser.py`: `Eyes`, the Playwright layer

- **Launch:** headless Chromium, viewport 1440×900, `ignore_https_errors`, optional `.webm` recording, and an optional `storage_state` for SSO apps.
- **Health signals are captured passively:**

  | Signal | Kind | Severity |
  |---|---|---|
  | console error | `background_error` | low |
  | page error | `background_error` | medium |
  | HTTP ≥ 500 | `server_error` | high |
  | HTTP ≥ 400 on a visited page | `broken_link` | medium |
  | load over 6 s | `slow` | low |
  | 30 s navigation timeout | `crash` | high |
- **`look()`** runs an inventory script and takes a JPEG screenshot (quality 70). The inventory collects up to 150 links, 80 nav items, 60 buttons, 60 fields (with min/max/pattern/accept), 5 tables, 10 alerts, 12 headings, and 2,500 characters of text.
- **Settling:**
  - `settle()` waits for network idle (7 s budget), then for 700 ms with no DOM changes (capped at 5 s).
  - `wait_for_change()` polls a fingerprint (URL + hash of the text) every 500 ms.
- **Acting:**
  - `click_text()` tries exact role, then link, then text, then partial matches.
  - `fill_field()` resolves locators, handles relative dates (`{{today+3d}}`), and drives calendar pickers.
  - `choose()` covers native selects, radios, checkboxes and custom dropdowns.
  - `upload_file()` sets the files on the upload input.
- **Sign-in:**
  - `sign_in()` makes 3 attempts and retries only on a server 5xx. It finds the password box, types the identity into the text input before it, and submits.
  - Success means the password box is gone.
  - It refuses to type a wrong password after the real username, to avoid lockouts.
- **Saved progress:** `start_fresh_on_resume_prompts()` auto-answers "start over" prompts, but only when a resume button is also present.

### `session.py`

- `load_target(run_id)` builds a `Target`: app name, URLs, auth method, `secret_ref`, `non_production = safety_posture == "non_production"`, and notes. The notes are the run's notes plus every remembered fact for the app, under the heading "What the user has told Explorer before (trusted)".
- `open_signed_in()` reads the login from Vault, then either reuses an SSO `storage_state` or signs in with the username and password. On failure it posts a readable error event with a screenshot.
- `open_signed_out()` is used by sign-in tests. It knows the login but has not signed in.
- `needs_sign_in()` decides the `@auth`/`@public` tag on exported tests.

### `mind.py`: reading and remembering a screen

`Mind.take_in(visit, reached_by, action)` is called for every screen in Stage 1, missions and breadth:

1. Saves the screenshot.
2. Reuses a cached reading if the revisit key (URL pattern + first heading) was seen before. Otherwise it calls `brain.perceive` (thinking model, with the image). Confirmation and "thank you" pages are always re-read.
3. Computes the **screen signature** (`sense.screen_signature`) and upserts `explorer_screen`. Many URLs collapse into one screen.
4. Draws an App Map edge (`explorer_transition`) from the previous screen.
5. Posts feed events: "Understood: X", or **"Hidden screen found: X"** when the Mind has a `condition`.
6. Records health issues: browser signals, error pages, wording problems, and "looks wrong" observations.
7. Remembers records the app created ("Test data the app showed: …") so later missions can reuse them.

### `brain.py`: every prompt

Every system prompt begins with the same stance: *the application is EVIDENCE, not the truth*, written in plain business language.

| Function | Model | Image | Returns |
|---|---|---|---|
| `perceive` | thinking | yes | screen name, entity, view kind, mode, purpose, fields, actions, hidden hints, error page?, wording problems, looks-wrong, where to explore next, tasks it starts, records created |
| `choose_next` | **fast** | no | index of the next lead + a thought |
| `summarize` | thinking | no | App Summary: name, one-liner, domain, users, business things, key tasks, expected rules, suspected hidden parts, ≤ 5 questions |
| `decide_step` | thinking | yes | the next step: fills, choices, uploads, the button to press, final?, branch points, needs from a human, done |
| `plan_missions` | thinking | no | 8–15 missions with kind, priority, start screen, instructions, condition, **expected** |
| `judge_outcome` | thinking | yes (final screen) | matches?, summary, difference, question for the user, record created |
| `plan_tests` | thinking | no | tests in the 5 kinds, each with expected, trust and start screen |
| `decide_check` | thinking | yes | the proof (`text_visible` or `url_contains`), observed, matches?, set-up OK? |

### `sense.py`: pure rules (unit-tested, no I/O)

- **`url_pattern`** turns ids (digits, UUIDs, long hex, `ABC-1234`) into `{id}`, keeps meaningful query keys like `tab=` or `status=`, and keeps hash routes.
- **`screen_signature`** is `subject|view_kind|mode`. The subject is the normalised entity (or the name). Each wizard or form step gets its own screen.
- **Click safety:** `is_risky_label`, `is_risky_link`, `looks_final`, `needs_human_ok`, `may_commit`. See [document 5](05-trust-safety-and-proof.md).
- **`health_score`:**
  - weights: high 12, medium 5, low 2;
  - repeats add up to ×2;
  - the total is scaled by `max(0.5, min(1.5, 10/pages_seen))`;
  - the result is clamped to 0–100;
  - labels: ≥ 85 Healthy, ≥ 60 Some problems, below that Unhealthy;
  - below 60 sets `requirements_first`.
- **`going_in_circles`:** the same 1–3 screen cycle repeated 3 times, or one screen landed on more than 4 times.
- Date variants, relative dates, and saved-progress label rules.

### `journal.py`: every write for a run

There is one short DB session per write.

- `update_run` never overwrites a `paused` run unless the status itself is changing.
- `status()` reports `paused` as `stopped`, so in-flight work halts.
- `upsert_screen` deduplicates on signature, then name, then URL pattern + view kind. A repeat increments `visits` and merges hints.
- `health_issue` deduplicates on kind + title + place, and a repeat increments `occurrences`.
- `email_starter` sends the "needs you" email (`explorer_core.notify`).

### `memory.py`: knowledge and questions

- `known_facts(app)` returns up to 60 facts, newest first: answers and facts first, then document passages. They go into every prompt through `session._with_memory`.
- `similar(a, b)` is word overlap after removing stop-words, with a threshold of 0.6.
- `ask(...)`:
  1. reuses an earlier answer from any run of the app;
  2. otherwise reuses a similar open question;
  3. otherwise creates one.

  With `wait=True` it sets only this mission to `waiting`, emails the starter, polls every 5 s for `EXPLORER_WAIT_MINUTES` (default 10), and finally returns the mission to `running`.

---

## Stage 1 · `understand.py`

`understand_app(run_id)` runs these steps:

1. Sets status `signing_in`, then `open_signed_in`.
2. `seed_from_previous_run`: if an earlier run of the same app has screens, copies its unconditional screens, transitions and branch points. The budget then drops to `EXPLORER_REVISIT_SCREENS` (10) new screens, so a re-run only looks for what's new.
3. `_first_look`, a loop until `EXPLORER_FIRST_LOOK_SCREENS` (24) new screens or `EXPLORER_FIRST_LOOK_MINUTES` (25) have passed:
   1. Sort the leads by value.
   2. `choose_next` (fast model) picks one from the top 20.
   3. A **flow** lead ("Report a claim") is clicked and then walked with `pursue`, which collects branch points. A **visit** lead is followed, and the screen is read with `Mind.take_in`.
   4. New leads come from the model's suggestions (`worth_exploring`, `starts_flow`) plus up to 60 plain links. Risky, logout, off-site, file and already-seen links are filtered out.
4. `_write_summary`:
   - computes the health score from technical issues only;
   - sets `requirements_first` when the score is below 60;
   - fails with "I couldn't get into the app" when fewer than 2 screens were seen and none had fields or actions;
   - otherwise calls `summarize`, stores the brief, sets `awaiting_confirmation`, and emails the starter.

## Stages 2 and 4 · `missions.py` + `pursue.py`

### `pursue()`: the goal-directed walker

Used by flows, missions and test builds. Each step:

1. Stop if the run was stopped. If signed out, sign in again once. If going in circles, end as `stuck`.
2. Call `decide_step` (thinking model, with the screenshot, the last 12 steps and up to 60 known screens).
3. Collect branch points. Ask for needed data through `memory.ask`. File needs are never asked; a built-in sample file is used instead.
4. Fill, choose and upload. Optionally jump straight to a known screen (only when no inputs are needed).
5. **Safety gate before pressing `advance`:**
   - if the button needs a human OK, or it is final and committing isn't allowed, ask "May I press …?". Without a yes, stop before it;
   - a final button is never pressed twice.
6. Click and wait for change. If nothing changed after 2 retries, end as `stuck`.

It records a replayable `actions` script (`goto`, `fill`, `choose`, `click`, `upload`, `back`, `reload`). It also records the shortest path to each screen in `PATHS`, which is used to fast-forward stateful apps without model calls.

### `missions.py`

- **Plan:**
  - leaves out `brief.skip_screens`;
  - calls `brain.plan_missions`;
  - sorts by priority;
  - keeps `mission_cap(screens) = max(6, min(15, screens // 3 + 4))`;
  - inserts `explorer_mission` rows, each with its **expected** outcome.
- **Run:**
  1. Opens a **recorded** signed-in browser.
  2. Goes to the start screen, or on stateful apps fast-forwards along the known path.
  3. Runs `pursue` with up to `EXPLORER_MISSION_STEPS` (20) steps. A `Mind(condition=…)` marks any new screens as hidden screens.
  4. Optionally repeats the walk `EXPLORER_TASK_PASSES` times and compares the paths. Screens that appear in only some passes get a condition.
- **Judge:**
  - `judge_outcome` compares the final screen with `expected` and re-reads the notes, so answers that arrived meanwhile count;
  - when it does not match (and the walk wasn't stuck): a `looks_wrong` health issue, plus a non-blocking "It's a bug / It's correct" question linked to it.
- **Finish:**
  - the mission becomes `done` or `blocked`;
  - the webm is stored in `explorer_recording`;
  - `finish_exploring` marks stragglers `blocked`, sets the run to `explored`, and posts a summary.

## Stage 3 · `hunt.py`

Revisits up to 10 form or wizard screens and 10 data screens (list, search, dashboard, detail), within a 25-minute limit:

| Technique | How it works | Condition recorded |
|---|---|---|
| Choices | Each radio group or select (≤ 4 groups × ≤ 5 options): reload, pick, then diff the visible labels and headings | `"<question>" is "<option>"` |
| Amounts | Up to 3 amount-like fields with 1, 999, 15,000 and 1,000,000, then Tab | `"<field>" is 1,000,000` |
| Server returns nothing | `page.route` empties lists and zeroes count fields on xhr/fetch responses | `Simulated: the server returns no records` |
| Server error | xhr/fetch answered with 500 `{"error":"simulated"}` | `Simulated: the server has a problem`. A blank page also becomes a possible bug. |
| Features switched on | Flips `false` feature/flag/beta/enable/show keys to `true` | `Simulated: optional features are switched on` |
| A year from now | `page.clock.install(now + 400 days)` | `Simulated: it is a year from now` |

Each find is upserted as a screen variant with signature `<base>|<key>`, plus a transition from the base screen.

## Stage 5 · `tests_stage.py` + `testkit.py` + `quality.py`

- **Plan:**
  1. Calls `brain.plan_tests` with screens, links, mission outcomes and possible bugs.
  2. Balances the tests by kind and start screen, with a cap of `test_cap(screens) = max(10, min(60, 5 × screens))`.
  3. **Grounding rule:** a test whose start screen Explorer never saw is dropped.
  4. Adds page-quality checks per URL pattern (skipped for stateful apps).
- **Build and prove:** see [document 5 §4](05-trust-safety-and-proof.md#4-how-a-test-is-proven).
- **`testkit.replay`:**
  - replays a script with no AI;
  - can mark a step `optional` when the next step is already reachable;
  - can press past up to 3 unexpected "Continue" screens.
- **`testkit.holds`:** checks the proof.
- **`testkit.without_decisive_step`:** builds the broken copy.
- **`testkit.playwright_code`:** emits the TypeScript Playwright test.
- **`quality.py`:** four browser-measured checks with no model involved: `loads_cleanly`, `no_broken_images`, `fits_phone` (390×844), and `fields_labelled`.
- **`samples.py`:** built-in upload files (JPG, PNG, PDF, TXT, CSV).

## Stage 6 · `breadth.py`

- **Who can see what:**
  - signs in as each `explorer_role` (its login comes from Vault);
  - tries up to 40 known screens;
  - a screen counts as blocked on a 401/403 response, a sign-in page, "access denied" text, or a bounce to home;
  - writes `explorer_access` rows.
- **Unlinked pages:**
  1. Fetches up to 15 same-origin JS bundles.
  2. Extracts route strings from them.
  3. Visits up to 10 unknown ones.
  4. Records them with the condition "it's opened directly — nothing in the app links to it".
- **Code coverage:**
  - uses Chrome DevTools Profiler precise coverage while visiting up to 40 screens;
  - counts only the app's own named functions, ignoring library bundles;
  - lists business-sounding functions that never ran.
- Saves everything in `explorer_run.insights`.

## Stage 7 · `reel.py`

- Scores the recordings. A mission that didn't match expectations ranks highest, then known-bug tests, then missions with new screens, then proven tests.
- Takes the top 6.
- Builds the video with ffmpeg at 1280×800, 30 fps: an intro card, then for each pick a title card (2.6 s) and a 7 s clip with a caption bar, then an outro.
- Stores it as `explorer_recording` with kind `reel`.
- Skips, with a feed message, when ffmpeg or a bold font is missing.

## Stage 8 · `promote.py`

See [document 3 §8](03-technical-flow.md#8-after-the-run-hand-off-to-classic-vantage). The test-type mapping:

- navigation, data_load, form_submission → `happy`
- validation, error_state, page_quality → `negative`

`captured_flow()` converts the script into generator `live_action_sequence` steps.

## Tests that guard the worker

`apps/workers/explorer/tests/`:

| File | What it covers |
|---|---|
| `test_sense.py` | URL patterns, risky labels, signatures, health bands, cycles, dates |
| `test_testkit.py` | decisive-step removal, proof must be caused by the test, replay detours, code export, sign-in never writing secrets |
| `test_compare_paths.py` | repeated walk comparison |
| `test_hunt.py` | `emptied` and `switched_on` |
| `test_breadth.py` | route extraction and coverage counting |
| `test_memory.py` | question similarity |
| `test_promote_flow.py` | `captured_flow` and the proof sentence |
| `test_workflow.py` | bounded mission pool, and cancel ends the run |

`apps/workers/generation/tests/test_proven_explorer_code.py` covers reuse of the proven code.
