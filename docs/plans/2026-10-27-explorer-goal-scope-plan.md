# Explorer Goal as a Strict Scope — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The App Summary's "Goal for this run" text becomes a strict scope every Explorer stage obeys; the section heading becomes "Goal"; confirming with unanswered summary questions is refused with a message.

**Architecture:** After confirmation, one model call turns the goal text plus the known screens into a stored scope (`run.brief["scope"]`) and a per-screen verdict (`explorer_screen.goal_fit`). Screens found later get their verdict from the existing per-screen reading (`brain.perceive`), so no extra model call per screen. Walks stop on arrival at a screen outside the goal or past the stop point; planners, follow-ups, the hunt and the breadth checks only consider screens inside it. An empty goal changes nothing.

**Tech Stack:** Python 3.14, SQLModel/Alembic (Postgres), Temporal workers, Playwright; React + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-explorer-goal-scope-design.md`

## Global Constraints

- Branch `feature-crawl2.0`. Never touch `feature-explorerv3.0`.
- Never edit worker code while an Explorer run is active (check `explorer_run` statuses first).
- Run only the targeted test files named in each task; never a full suite.
- Changes stay in Explorer's modules, `apps/api/src/api/explorer.py`, `packages/explorer_core`, a new migration, and `apps/web/src/explorer/SummaryView.tsx` (+ its test). No shared/Standard code.
- An empty goal (`brief.focus` blank) must behave exactly as today.
- Copy fixed by the spec: heading `Goal`; Live-feed line `Reached the edge of your goal: <screen>`; confirm refusal `Answer the questions first — they change what Explorer tests.`
- UI per CLAUDE.md: nothing invented; button stays looking enabled, a blocked click shows a message; busy state = ring Spinner (`LoadingDots`).
- Match each file's existing line endings (several are CRLF).

## Review Focus

1. A goal written in business words that matches no screen name exactly ("policy search" vs stored "Find your policy") — the stop screen must still be found (Task 4 test `test_stop_point_matched_by_meaning_is_kept_from_the_model`).
2. A scenario whose proof is the screen after the stop point — must stop there and still be provable, not dropped (Task 6 test `test_landing_past_the_stop_ends_the_walk_as_done`).
3. A user-added mission outside the goal — must run, not be stopped (Task 6 test `test_a_users_own_mission_is_not_stopped_at_the_edge`).
4. Run confirmed before this ships, resumed later — scope created lazily (Task 4 test `test_scope_is_created_once_and_reused`).
5. Empty goal — no model call, no filtering anywhere (Task 4 `test_empty_goal_has_no_scope`, Task 7 `test_without_a_goal_every_screen_is_planned`).

---

### Task 1: Confirm is refused while a summary question is unanswered (API)

**Files:**
- Modify: `apps/api/src/api/explorer.py` (`confirm_brief`, ~line 510)
- Test: `apps/api/tests/test_explorer_confirm_needs_answers.py` (new)

**Interfaces:**
- Produces: `unanswered_questions(brief: dict | None) -> int` in `apps/api/src/api/explorer.py`.

- [ ] **Step 1: Write the failing test**

```python
from api.explorer import unanswered_questions

def test_confirm_needs_every_summary_question_answered() -> None:
    brief = {"questions_for_you": [{"question": "A?", "answer": "Yes"}, {"question": "B?", "answer": ""}]}
    assert unanswered_questions(brief) == 1
    assert unanswered_questions({"questions_for_you": [{"question": "A?", "answer": "Yes"}]}) == 0
    assert unanswered_questions(None) == 0
    assert unanswered_questions({}) == 0
```

- [ ] **Step 2:** `cd apps/api && uv run pytest tests/test_explorer_confirm_needs_answers.py -q` — expect ImportError.
- [ ] **Step 3: Implement** `unanswered_questions` (count dict items in `brief["questions_for_you"]` whose `answer` is blank) and in `confirm_brief`, after the status checks and before signalling Temporal: `if unanswered_questions(run.brief): raise HTTPException(409, "Answer the questions first — they change what Explorer tests.")`.
- [ ] **Step 4:** re-run the test — PASS.
- [ ] **Step 5: Commit** `feat(explorer): refuse confirming the App Summary with unanswered questions`.

### Task 2: App Summary screen — "Goal" heading and blocked confirm message

**Files:**
- Modify: `apps/web/src/explorer/SummaryView.tsx` (heading at the "What to cover" `SectionTitle`; confirm button `onClick` ~line 128)
- Test: `apps/web/src/explorer/SummaryView.test.tsx` (new)

**Interfaces:** none new; `SummaryView` props unchanged.

- [ ] **Step 1: Write the failing tests** (render `SummaryView` with `run.status = 'awaiting_confirmation'`, `brief.questions_for_you = [{question:'Which policy?', options:['POL-1'], answer: ''}]`, `screens=[]`, `onSave`, `onConfirm = vi.fn()`):
  - `it('calls the coverage section Goal')` — `screen.getByText('Goal')` exists; `screen.queryByText('What to cover')` is null.
  - `it('does not confirm while a question is unanswered, and says why')` — click the confirm button (name `/Looks right — confirm/`); `expect(onConfirm).not.toHaveBeenCalled()`; `screen.getByText('Answer the questions first — they change what Explorer tests.')` is visible.
  - `it('confirms once every question is answered')` — same with `answer: 'POL-1'`; click → `onConfirm` called once.
- [ ] **Step 2:** `cd apps/web && npx vitest run src/explorer/SummaryView.test.tsx` — expect the first two to FAIL.
- [ ] **Step 3: Implement:** rename the heading text to `Goal`. In the confirm `onClick`, when `unanswered > 0`: set a local `confirmBlocked` state, scroll the Questions card into view (`ref.scrollIntoView({ behavior: 'smooth', block: 'center' })`), and return without calling `onConfirm`. Render the message (warn colour, `role="alert"`) next to the button while `confirmBlocked && unanswered > 0`. The button keeps its enabled look.
- [ ] **Step 4:** re-run — PASS; then `npx tsc --noEmit -p tsconfig.app.json` — no errors.
- [ ] **Step 5: Commit** `feat(explorer): App Summary "Goal" heading; confirm asks for unanswered questions first`.

### Task 3: Store each screen's verdict against the goal

**Files:**
- Modify: `packages/explorer_core/src/explorer_core/models.py` (`ExplorerScreen`)
- Create: `migrations/versions/d3a6c9e1f4b8_add_explorer_screen_goal_fit.py` (down_revision `c1f4a7e2d9b6`)
- Modify: `apps/workers/explorer/src/explorer_worker/journal.py` (`upsert_screen`)

**Interfaces:**
- Produces: `ExplorerScreen.goal_fit: str | None` — one of `GOAL_FITS = ("inside", "on_the_way", "past_stop", "outside")`, `None` = no goal / not judged. Export `GOAL_FITS` from `explorer_core`.
- `Journal.upsert_screen` stores `values["goal_fit"]` on insert, and on an existing row only when the row's value is `None` (first verdict wins).
- Produces: `Journal.set_goal_fit(fits: dict[str, str]) -> None` — sets `goal_fit` by screen **name** for this run.

- [ ] **Step 1:** add the column (nullable `String`), the migration (add/drop column), run `uv run alembic upgrade head` locally (no run active), and `uv run alembic heads` shows one head `d3a6c9e1f4b8`.
- [ ] **Step 2:** no unit test (schema only); verified by Task 4/5 tests and `alembic heads`.
- [ ] **Step 3: Commit** `feat(explorer): explorer_screen.goal_fit`.

### Task 4: Turn the goal into a stored scope (`goal.py`)

**Files:**
- Create: `apps/workers/explorer/src/explorer_worker/goal.py`
- Modify: `apps/workers/explorer/src/explorer_worker/brain.py` (new `read_goal`; `scope()` adds the strict rule)
- Test: `apps/workers/explorer/tests/test_goal_scope.py` (new)

**Interfaces:**
- Produces in `brain.py`: `async def read_goal(goal: str, screens: list[dict[str, Any]]) -> dict[str, Any]` returning `{"rule": str, "fits": {screen_name: fit}}`. Prompt: restate the goal as a strict rule in one or two sentences; classify every given screen as `inside` (in the goal, including the stop screen), `on_the_way` (must be passed through to reach the goal), `past_stop` (comes after the stop point), `outside`; match by meaning, not wording (e.g. "policy search" = a screen whose purpose is finding a policy). Read the goal literally (spec "Calls" #2): "only/just X up to Y" — everything outside flow X is `outside`, screens after Y are `past_stop`; a stop point without "only" cuts just that path (the rest stays `inside`); branches inside the named flow before the stop are `inside`; a "leave out Z" goal makes Z `outside` and everything else `inside`. Unknown values are dropped by the caller.
- Produces in `goal.py`:
  - `async def ensure_scope(run_id: uuid.UUID) -> dict[str, Any] | None` — `None` when `brief.focus` is blank. Otherwise returns `brief["scope"]` if present; else calls `brain.read_goal(focus, journal screen payload)`, keeps only valid fits, saves `brief["scope"] = {"rule", "fits"}` via `Journal.update_run(brief=...)`, calls `Journal.set_goal_fit(fits)`, logs a `thought` event `Following your goal` with the rule, and returns the scope.
  - `def in_goal(fit: str | None) -> bool` — True for `None` (no goal or not judged) and `"inside"`.
  - `def stops_walk(fit: str | None) -> bool` — True for `"past_stop"` and `"outside"`.
- `brain.scope(brief)`: when `brief.get("scope")`, the text starts `The user's goal for this run is a STRICT rule: <rule> Plan nothing outside it.` (replacing the soft "follow it first" line); otherwise unchanged.

- [ ] **Step 1: Write the failing tests** (monkeypatch `brain.read_goal` and a fake `Journal` like `tests/test_plan_no_missions.py`):
  - `test_empty_goal_has_no_scope` — brief `{"focus": "  "}` → `ensure_scope` returns `None`; `read_goal` never called.
  - `test_scope_is_created_once_and_reused` — first call calls `read_goal` once and saves `brief["scope"]`; second call (brief now has scope) does not call it again.
  - `test_stop_point_matched_by_meaning_is_kept_from_the_model` — `read_goal` returns fits `{"Find your policy": "inside", "Policy selection": "past_stop", "Check a claim": "outside", "Bogus": "maybe"}`; saved fits drop `Bogus`; `set_goal_fit` receives the 3 valid ones.
  - `test_in_goal_and_stops_walk` — `in_goal(None)`, `in_goal("inside")` True; `in_goal("on_the_way")`, `in_goal("past_stop")`, `in_goal("outside")` False; `stops_walk("past_stop")`, `stops_walk("outside")` True; `stops_walk("on_the_way")`, `stops_walk(None)` False.
  - `test_scope_text_is_strict_only_with_a_goal` — `brain.scope({"focus": "x", "scope": {"rule": "Only claim reporting up to Find your policy."}})` contains `STRICT` and the rule; `brain.scope({})` == `""`.
- [ ] **Step 2:** `cd apps/workers/explorer && uv run pytest tests/test_goal_scope.py -q` — FAIL.
- [ ] **Step 3: Implement** as specified above.
- [ ] **Step 4:** re-run — PASS.
- [ ] **Step 5: Commit** `feat(explorer): turn the run's goal into a strict scope`.

### Task 5: Judge every newly found screen against the goal

**Files:**
- Modify: `apps/workers/explorer/src/explorer_worker/brain.py` (`perceive` gets `goal_rule: str | None = None`; when set, the user message adds `The user's goal (strict): <rule>` and the reply gains `"goal_fit": "inside | on_the_way | past_stop | outside"`)
- Modify: `apps/workers/explorer/src/explorer_worker/mind.py` (`Mind.__init__` takes `goal_rule: str | None = None`; `take_in` passes it to `perceive`, writes `reading.get("goal_fit")` (if in `GOAL_FITS`) into the `upsert_screen` values, and sets `self.last_goal_fit` from the stored row's value)
- Modify: `apps/workers/explorer/src/explorer_worker/tests_stage.py` (`QuietMind.take_in` sets `self.last_goal_fit` from the matched screen row's `goal_fit`, `None` when no row matched)
- Test: `apps/workers/explorer/tests/test_goal_scope.py` (extend)

**Interfaces:**
- Produces: `Mind.last_goal_fit: str | None` (and on `QuietMind`).
- Consumes: Task 3 `goal_fit`, Task 4 `GOAL_FITS`.

- [ ] **Step 1: Write the failing test** `test_quiet_mind_knows_a_known_screens_goal_fit` — QuietMind with `screen_ids` mapping a pattern to a screen whose `goal_fit` is `"past_stop"` (fake journal returning that row) → after `take_in`, `mind.last_goal_fit == "past_stop"`; on an unmatched address → `None`.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3: Implement** as specified. `goal_rule` is only passed when a scope exists, so an empty goal sends exactly today's prompt.
- [ ] **Step 4:** run Task 4–5 tests plus `tests/test_saved_routes.py` — PASS.
- [ ] **Step 5: Commit** `feat(explorer): judge new screens against the goal while reading them`.

### Task 6: Walks stop at the edge of the goal

**Files:**
- Modify: `apps/workers/explorer/src/explorer_worker/pursue.py` (`pursue` gets `obey_goal: bool = True`)
- Modify: `apps/workers/explorer/src/explorer_worker/missions.py` (run a mission with `obey_goal=mission.added_by != "user"`; create its `Mind` with `goal_rule=(await ensure_scope(run_id) or {}).get("rule")`)
- Modify: `apps/workers/explorer/src/explorer_worker/tests_stage.py` (scenario `pursue` call: default `obey_goal=True`)
- Test: `apps/workers/explorer/tests/test_goal_edge.py` (new)

**Interfaces:**
- Produces: a pure helper in `pursue.py`: `def edge_reached(fit: str | None, obey_goal: bool) -> bool` = `obey_goal and stops_walk(fit)`.
- Behaviour: after each `mind.take_in` (start screen included), if `edge_reached(mind.last_goal_fit, obey_goal)`: `result.ended = "done"`, `result.outcome = f"Reached the edge of your goal: {step_name}"`, one `phase` event with that title, and `break`. `"done"` (not `"stuck"`) so a scenario landing on the screen after its stop point goes on to proof selection on that screen.

- [ ] **Step 1: Write the failing tests:**
  - `test_landing_past_the_stop_ends_the_walk_as_done` — `edge_reached("past_stop", True)` and `edge_reached("outside", True)` are True; `edge_reached("on_the_way", True)`, `edge_reached("inside", True)`, `edge_reached(None, True)` False.
  - `test_a_users_own_mission_is_not_stopped_at_the_edge` — `edge_reached("outside", False)` is False.
- [ ] **Step 2:** `uv run pytest tests/test_goal_edge.py -q` — FAIL.
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4:** run `tests/test_goal_edge.py tests/test_follow_ups.py tests/test_journeys.py tests/test_saved_routes.py` — PASS.
- [ ] **Step 5: Commit** `feat(explorer): stop walks at the edge of the user's goal`.

### Task 7: Planning, follow-ups and scenarios only inside the goal

**Files:**
- Modify: `apps/workers/explorer/src/explorer_worker/missions.py` (`plan_missions`: call `ensure_scope` first; drop screens whose `goal_fit` is not `in_goal`; `_queue_follow_ups`: drop follow-ups whose screen's stored `goal_fit` is not `in_goal`)
- Modify: `apps/workers/explorer/src/explorer_worker/tests_stage.py` (`plan_tests`: call `ensure_scope`; filter `screens` with `in_goal(s.goal_fit)` alongside `skip_screens`)
- Test: `apps/workers/explorer/tests/test_goal_scope.py` (extend)

**Interfaces:**
- Produces: `def screens_in_goal(screens: list[ExplorerScreen]) -> list[ExplorerScreen]` in `goal.py` (keeps `in_goal(s.goal_fit)`), used by missions, tests_stage, hunt and breadth.

- [ ] **Step 1: Write the failing tests:**
  - `test_only_screens_inside_the_goal_are_planned` — screens with fits `inside`, `None`, `on_the_way`, `past_stop`, `outside` → `screens_in_goal` keeps the `inside` and `None` ones.
  - `test_without_a_goal_every_screen_is_planned` — all `goal_fit=None` → all kept.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3: Implement** as specified (follow-up filter: look up the screen named by the follow-up's `start_screen`; missing row → keep).
- [ ] **Step 4:** run `tests/test_goal_scope.py tests/test_follow_ups.py tests/test_plan_review.py tests/test_plan_no_missions.py` — PASS.
- [ ] **Step 5: Commit** `feat(explorer): plan missions, follow-ups and scenarios only inside the goal`.

### Task 8: Hidden-screen hunt and breadth checks only inside the goal

**Files:**
- Modify: `apps/workers/explorer/src/explorer_worker/hunt.py` (`hunt`: `screens = screens_in_goal(journal.screen_rows())`)
- Modify: `apps/workers/explorer/src/explorer_worker/breadth.py` (`breadth`: when `ensure_scope` returns a scope, skip `_unlinked_pages` (their screens can't be judged before visiting) and limit `_roles_sweep` to `screens_in_goal`)
- Test: `apps/workers/explorer/tests/test_goal_scope.py` (extend)

- [ ] **Step 1: Write the failing test** `test_hunt_only_probes_screens_inside_the_goal` — monkeypatch `hunt` collaborators (`Journal.screen_rows` returns one `inside` form and one `outside` form; `_probe_choices`/`_probe_amounts` record screens; `open_signed_in` returns a fake eyes) → only the inside form is probed.
- [ ] **Step 2:** run — FAIL.
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4:** run `tests/test_goal_scope.py tests/test_hunt.py tests/test_breadth.py` — PASS.
- [ ] **Step 5: Commit** `feat(explorer): hunt and breadth checks stay inside the goal`.

### Task 9: Live check (manual, no code)

- [ ] With no run active and workers reloaded: add the FNOL test app (sign-in off), wait for the App Summary, answer its questions, type the goal `Only the claim reporting flow, up to policy search`, confirm.
- [ ] Expect: a `Following your goal` event; missions only on Claims support → Safety check → Find your policy (and Find your policy another way); `Reached the edge of your goal: …` lines; no scenarios on screens after Policy selection; Policy selection used only as proof. Stop the run once scenario building has shown this.
