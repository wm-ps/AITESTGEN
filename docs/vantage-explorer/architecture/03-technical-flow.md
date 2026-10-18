# 3. Technical flow

> Diagrams:
> - [Pipeline: activities in order](diagrams/explorer-pipeline.html), the stages and who acts in each
> - [Request sequence](diagrams/explorer-run-sequence.html), who calls whom from Start to proven tests
> - [Run status lifecycle](diagrams/explorer-run-lifecycle.html), the `explorer_run.status` values and transitions

## 1. Starting a run

There are two entry points, and both end in `begin_run` (`apps/api/src/api/explorer.py`):

| Entry | Trigger |
|---|---|
| `POST /explorer/applications/{id}/runs` | The **Start exploring** button. The body is `{notes?}`. |
| `discovery.start_discovery_run` → `_start_explorer` | Onboarding a new application while `EXPLORER_REPLACES_DISCOVERY` ≠ `0`. |

`begin_run` does the following, in order:

1. Returns **409** if the application already has a run in an active status (`ACTIVE_RUN_STATUSES`).
2. Returns **503 `EXPLORER_UNAVAILABLE`** if no worker polls `explorer-task-queue`.
3. Inserts `explorer_run` with status `queued`, the notes and `started_by_id`.
4. Saves the notes as an `explorer_knowledge` fact with source "Run notes", unless the same text is already stored.
5. Marks the app's crawler `DiscoveryRun` as `running` / stage `explorer`, so classic screens show "Explorer is finding this app's journeys".
6. Calls `client.start_workflow("ExplorerRunWorkflow", str(run.id), id="explorer-run-<external_id>", task_queue="explorer-task-queue")`. The mode defaults to `full`.

## 2. The workflow: `ExplorerRunWorkflow`

File: `apps/workers/explorer/src/explorer_worker/workflow.py`. The workflow does orchestration only.

```python
STEPS = ("understand", "confirm", "plan_missions", "missions", "hunt", "plan_tests", "build_tests")
MAX_PARALLEL = 3
```

`run(run_id, mode)` picks a starting step and runs every step from there on:

| Mode | Starts at | Used by |
|---|---|---|
| `full` | `understand` | a new run |
| `missions` | `missions` | after a user adds a mission to a finished run. The run stops after hunt/breadth. |
| `tests` | `plan_tests` | "regenerate tests" |
| `resume` | whatever `explorer_resume_point` returns | Resume after pause, stop or failure |

### Step by step

| # | Step | Activity (name) | Timeout | Notes |
|---|---|---|---|---|
| 1 | understand | `explorer_understand_app` | 2 h, heartbeat 5 min | Sign in, first look, health, App Summary. Returns `awaiting_confirmation`, `failed` or `stopped`; anything other than `awaiting_confirmation` ends the workflow. |
| 2 | confirm | — | `wait_condition` up to **14 days** | Waits for the `brief_confirmed` signal. On timeout the workflow returns `"unconfirmed"`. |
| 3 | plan_missions | `explorer_plan_missions` | 15 min | Returns the number of missions planned. With 0, the workflow returns `"no-missions"`. |
| 4 | missions | pool of `explorer_queued_missions` / `explorer_run_mission` / `explorer_requeue_mission`, then `explorer_finish_exploring` | 45 min per mission, heartbeat 5 min | Up to 3 at once. Missions added meanwhile are picked up too. |
| 5 | hunt | `explorer_hunt_hidden_screens`, then `explorer_breadth` | 40 min each | These are "bonus" steps: a failure is logged and the run carries on. |
| 6 | plan_tests | `explorer_plan_tests` | 20 min | Bonus step. Returns the number of tests planned. |
| 7 | build_tests | pool of `explorer_planned_tests` / `explorer_build_test` / `explorer_requeue_test`, then `explorer_finish_testing` | 45 min per test | Up to 3 at once. |
| 8 | hand-off | `explorer_send_to_vantage` | 10 min | Bonus step. Promotes proven tests into classic Journeys and Scenarios (Stage 8). |
| 9 | highlight video | `explorer_highlight_video` | 20 min | Bonus step. Builds the ffmpeg MP4. |

The workflow returns `"tested"`.

### The pool helper (`_pool`)

Missions and tests use the same loop:

1. Call the **list** activity. It returns ids that are waiting, ordered by priority.
2. Start a **run** activity for each id until 3 are running.
3. `workflow.wait(..., FIRST_COMPLETED)`.
4. When an item fails because its worker died or it timed out, the workflow calls the **requeue** activity **once** for that id. A second failure leaves it as it is.
5. If the failure is a `CancelledError` (Stop or Pause), it is re-raised so the run ends instead of moving on.
6. The loop ends when nothing is running and nothing is waiting.

**Stateful apps** run one item at a time. If screen names or purposes suggest a draft, a cart or saved progress (`keeps_state`), the list activity returns at most one item and nothing while another is busy. This keeps two missions from tripping over the same saved draft.

### Retry policy

Every activity runs with `RetryPolicy(maximum_attempts=1)`. A browser session is not safely replayable, so each activity catches its own exceptions and writes a visible outcome:

- `understand` and `plan_*`: the run becomes `failed` with a one-line reason in `error`.
- A mission: that mission becomes `failed`, and the other missions keep going.
- A test build: it waits about 60 s and tries once more inside the activity, because the first failure is often a network blip. After that, the test is dropped with a reason.
- hunt, breadth, promote, highlight video: the failure is logged, and the run continues.

## 3. The human checkpoint

1. `understand` writes `explorer_run.brief`, sets status `awaiting_confirmation`, and emails the starter.
2. The UI switches to **What it learned**. The user may edit the brief (`PUT /runs/{id}/brief`, allowed only while awaiting confirmation) and answer its questions.
3. `POST /runs/{id}/confirm`:
   - sends the Temporal signal `brief_confirmed`;
   - sets status `confirmed` and `brief_confirmed_at`;
   - stores each answered summary question as `explorer_knowledge` (kind `answer`, source "App Summary").
4. The workflow wakes and plans missions.

## 4. Questions during missions

The full mechanism is in [document 4](04-worker-modules.md), under `memory.py`. In short:

1. A mission calls `memory.ask(...)`.
2. If a similar question was answered before, for this app in any run, the stored answer is used immediately.
3. Otherwise an `explorer_question` row is created. Only **this mission** is set to `waiting`, and the starter is emailed.
4. The mission's activity polls the row every 5 s for up to `EXPLORER_WAIT_MINUTES` (default 10), heartbeating, with its browser kept open.
5. `POST /questions/{id}/answer` stores the answer plus a knowledge row. The polling mission picks it up and continues from where it stopped.
6. On timeout the mission carries on without an answer.
7. "Is this a bug?" questions (`kind = rule`) are created with `wait=False` and never block anything.

## 5. Stop, pause and resume

| Action | API | What happens |
|---|---|---|
| **Stop** | `POST /runs/{id}/stop` | Status `stopped`. The workflow is **cancelled**. Running activities see the status on their next check (`journal.status`) and halt. |
| **Pause** | `POST /runs/{id}/pause` | Same as Stop, but status `paused`. The feed says "Press Resume to carry on from here. Nothing finished is lost." |
| **Resume** | `POST /runs/{id}/resume` | Allowed from `paused`, `stopped` or `failed`. Terminates any leftover workflow with the same id, sets status `queued`, then starts the workflow again with `mode="resume"`. |

`explorer_resume_point` (`resume.py`) works out where to restart from the saved rows:

1. It puts cut-off work back in the queue:
   - missions that were `running`, `waiting`, or skipped with the outcome "Stopped before finishing" become `queued`;
   - tests that were `building` become `planned`.
2. It picks the starting step:
   - no brief → `understand`
   - not confirmed → `confirm`
   - no missions → `plan_missions`
   - any mission queued → `missions`
   - tests exist → `build_tests`
   - otherwise → `hunt`

Finished work is never redone.

## 6. Run statuses

`explorer_core.models.RUN_STATUSES`, in order:

| Status | Set by | Meaning |
|---|---|---|
| `queued` | `begin_run`, resume | Waiting for a worker |
| `signing_in` | understand | Opening a signed-in browser |
| `understanding` | understand | First look in progress |
| `summarizing` | understand | Writing the App Summary |
| `awaiting_confirmation` | understand | **Human checkpoint** |
| `confirmed` | `/confirm` | Signal sent |
| `planning` | plan_missions | Building the Mission Board |
| `exploring` | plan_missions, add-mission | Missions running |
| `explored` | finish_exploring | Missions done |
| `hunting` | hunt, breadth | Hidden screens, roles, unlinked pages, coverage |
| `testing` | plan/build tests, regenerate | Writing and proving tests |
| `tested` | finish_testing | Done |
| `failed` | any activity's failure handler | `error` holds a one-line reason |
| `stopped` | `/stop` | Ended by the user |
| `paused` | `/pause` | Ended, and resumable |

`ACTIVE_RUN_STATUSES` (which block a second run): queued, signing_in, understanding, summarizing, awaiting_confirmation, planning, exploring, hunting, testing.

Each status change also sets a one-line `headline`, for example "Reading the Quotes screen". The Live view shows it.

## 7. Mission and test statuses

| Entity | Statuses |
|---|---|
| Mission | `queued` → `running` ⇄ `waiting` → `done` / `blocked` (stuck) / `failed` / `skipped` |
| Test case | `planned` → `building` → `proven` / `known_bug` / `dropped` (with `drop_reason`) |
| Question | `open` → `answered` / `dismissed` |

## 8. After the run: hand-off to classic Vantage

`promote.py` runs once testing finishes:

1. Reads tests with status `proven` or `known_bug`.
2. Groups them by start screen. There is **one `Journey` per start screen**, keyed `explorer:<slug>`.
3. On a re-run, the journey's `attempt` goes up. Old scenarios, suites and assets are retired with `current=False` (never deleted). Journeys no longer produced are set to `retired`.
4. Writes `Page` + `JourneyStep` (the screenshot is copied to the object store) and one `Scenario` per test. The scenario's `grounding` holds:
   - `proven_code`: Explorer's Playwright code;
   - `captured_flow`: the steps as generator actions;
   - `requires_auth`;
   - the proof `check`.
5. Marks the crawler `DiscoveryRun` complete / `analyzed`.

When the user later presses **Generate tests**, the generation worker uses `grounding.proven_code` **as is** if it passes the Playwright type check. Otherwise it falls back to normal AI generation (`_proven_explorer_code` in `generation_worker/activities.py`).
