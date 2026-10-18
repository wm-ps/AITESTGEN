# 6. Data model

All Explorer tables live in `packages/explorer_core/src/explorer_core/models.py` and are prefixed `explorer_`. They follow the platform id convention:

- `id` is an internal UUIDv7 primary key;
- `external_id` (UUIDv4, unique, indexed) is the only id that leaves the backend, and only on tables the API exposes by id;
- `explorer_event` uses a BigInteger identity id, so the live feed can page with `after=<id>`.

## Entity overview

```
application ─┬─< explorer_run ─┬─< explorer_event
             │                 ├─< explorer_shot            (JPEG bytes)
             │                 ├─< explorer_screen ─< explorer_transition (from/to screen)
             │                 ├─< explorer_health_issue
             │                 ├─< explorer_mission
             │                 ├─< explorer_recording       (webm/mp4 bytes; mission | proof | reel)
             │                 ├─< explorer_test_case
             │                 ├─< explorer_question
             │                 └─< explorer_access          (role × screen)
             ├─< explorer_knowledge   (per app, across runs)
             └─< explorer_role        (per app; login in Vault)
platform_user ─< explorer_run.started_by_id (SET NULL)
```

Run-scoped tables cascade-delete with their run. Application-scoped tables cascade-delete with the application.

## Tables

### `explorer_run`: one exploration

| Column | Purpose |
|---|---|
| `application_id` | FK to `application` (CASCADE) |
| `status`, `headline` | Lifecycle state and the one-line live text. See [document 3 §6](03-technical-flow.md#6-run-statuses). |
| `health_score`, `requirements_first` | 0–100. `requirements_first` is true when the score is below 60. |
| `brief` (JSONB), `brief_confirmed_at` | The App Summary and when you confirmed it. Includes `questions_for_you[].answer`, `key_tasks`, `focus` and `skip_screens`. |
| `notes` | Text from the Start card |
| `started_by_id` | Who to email when the run needs someone |
| `insights` (JSONB) | Stage 6 output: `unlinked`, `coverage`, `roles` |
| `branch_points` (JSONB) | Choices noticed during walk-throughs. These seed the branch missions. |
| `error` | One-line failure reason |

### `explorer_event`: the live feed

`kind` is one of thought, action, screen, health, phase, summary, error or question. The row also holds `title`, `detail`, an optional `shot_id` and `mission_id`. The UI polls `GET /runs/{id}/events?after=<last id>`.

### `explorer_shot`

Screenshot bytes (JPEG, viewport only, about 60–150 KB each). Served by `GET /explorer/shots/{id}`.

### `explorer_screen`: a screen as Explorer understands it

| Column | Purpose |
|---|---|
| `signature` | `subject\|view_kind\|mode`. This is the dedup key, so many URLs map to one row. |
| `name`, `entity`, `view_kind`, `mode`, `purpose` | Meaning |
| `url`, `url_pattern` | A sample URL, and the pattern with ids replaced by `{id}` |
| `fields`, `actions`, `hidden_hints` (JSONB) | What the screen offers |
| `visits`, `reached_by`, `shot_id` | Bookkeeping |
| `condition` | Set when the screen only appears in a situation ("`Married` is chosen", "Simulated: …", "nothing links to it"). This is what makes it a **hidden screen**. |

### `explorer_transition`: App Map edges

`from_screen_id`, `to_screen_id`, `action` (the label pressed) and an optional `mission_id`. The Screens tab shows them as "Press {action} → {screen}".

### `explorer_health_issue`

- `kind`: crash, broken_link, server_error, background_error, slow, wording, looks_wrong, or accepted (set after you say "correct").
- `severity`: high, medium or low.
- Also `title`, `detail`, `url`, `occurrences` and `shot_id`.
- `looks_wrong` issues are the **possible bugs**.

### `explorer_mission`: Mission Board entries

| Column | Purpose |
|---|---|
| `kind` | task, branch, area, rule or custom (added by you) |
| `title`, `goal`, `why`, `priority` (1–5), `instructions`, `start_screen` | The plan |
| `condition` | The situation a branch mission tests. New screens it finds inherit this condition. |
| `expected` | What **should** happen, written before the mission runs |
| `status`, `outcome`, `matches_expected`, `steps`, `new_screens` | The result |
| `added_by`, `started_at`, `finished_at` | Bookkeeping |

### `explorer_recording`

Video bytes. `kind` is one of:

- `mission`: webm, linked by `mission_id`;
- `proof`: webm, linked by `test_case_id`;
- `reel`: the MP4 highlight video.

Also stores `started_at` and `duration_seconds`.

### `explorer_test_case`

| Column | Purpose |
|---|---|
| `kind` | navigation, validation, error_state, data_load, form_submission, or page_quality (the non-AI checks) |
| `title`, `purpose`, `technique`, `business_thing`, `start_screen`, `steps` | For people |
| `expected`, `trust` | What should happen and where that belief comes from (confirmed, standard or seen) |
| `observed` | What the app actually did |
| `script` (JSONB) | Exact replayable actions. `script[0]` also holds metadata (how to run, rule, signed_out). |
| `check` (JSONB) | The proof: `{kind: text_visible \| url_contains, value}` |
| `status`, `drop_reason` | planned, building, proven, known_bug or dropped |
| `proof_runs`, `proof_passes`, `catches_breakage` | Proof statistics |
| `evidence_shot_id`, `code` | Screenshot and Playwright TypeScript |

### `explorer_question`

- `kind`: data, risk, rule or clarify.
- Also `question`, `why`, `options` (≤ 6), `shot_id`, and `mission_id`.
- `issue_id` links a "bug or correct?" question to its health issue.
- `status` is open, answered or dismissed; the row also holds `answer` and `answered_at`.

### `explorer_knowledge`: per-application memory across runs

- `kind`:
  - `answer`: your answers;
  - `fact`: typed by you or taken from run notes;
  - `doc`: a document passage;
  - `record`: test data the app showed.
- Also `text` (≤ 4,000 characters) and `source`.

### `explorer_role` and `explorer_access`

- `explorer_role` is another kind of user. It holds a `name` and a `secret_ref` pointing at the login in Vault.
- `explorer_access` holds one row per run × role × screen, with `allowed` and a `note`.

## Migrations

Applied in this order (Alembic, `migrations/versions/`):

| Revision | File | Adds |
|---|---|---|
| `e7a1c3b5d9f2` | `add_explorer_tables` | run, event, shot, screen, health_issue (Stage 1) |
| `f3b5d7e9a1c4` | `add_explorer_missions_map_recordings` | mission, transition, recording; `run.branch_points`, `screen.condition`, `event.mission_id` (Stage 2) |
| `a4c6e8f0b2d5` | `add_explorer_test_cases` | test_case; `recording.test_case_id`, with `mission_id` made nullable (Stage 5) |
| `b5d7f9a1c3e6` | `add_explorer_questions_knowledge` | question, knowledge (Stage 4) |
| `c6e8a0b2d4f7` | `add_explorer_roles_insights_reel` | role, access; `run.insights`, `recording.kind` (Stages 6–7) |
| `d7f9b1c3e5a8` | `add_explorer_run_started_by` | `run.started_by_id` → `platform_user` |

The chain starts after `b8d4f6a0c2e3` (`add_scenario_grounding`), and `d7f9b1c3e5a8` is currently the head.

## What Explorer writes outside its own tables

Explorer reads `application` and the app's Vault login everywhere. It writes classic tables only in these places:

| Writer | Tables | What |
|---|---|---|
| API `begin_run` | `discovery_run` | Marks the crawler discovery run `running` / stage `explorer` |
| Worker `promote.py` | `journey`, `journey_step`, `page`, `scenario`, `test_suite`, `test_asset`, `application.next_test_case_number`, `discovery_run` | One journey per start screen and one scenario per proven or known-bug test. On re-runs, old rows are retired (`current=False`), never deleted. |
| API roles endpoints | Vault | Stores and deletes role logins |

The scenario's `grounding` JSON is the contract with the generation worker. It holds:

- `explorer_test` (external id) and `kind`;
- `proven`;
- `requires_auth`;
- `check`;
- `captured_flow`;
- `proven_code`;
- `one_at_a_time`.
