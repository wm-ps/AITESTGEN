# 8. Operations and configuration

> **In short.** Explorer needs four things running:
> - the usual Vantage stack (Postgres, Temporal, Vault, the API and the web app);
> - **one Explorer worker** (`scripts/dev-start` starts it for you);
> - access to the **LiteLLM** gateway;
> - Playwright's **Chromium**.
>
> Most problems come down to one of three causes: no worker running, a missing saved login, or old worker processes still running after a reload.

## Running it locally

Explorer needs the same infrastructure as the rest of Vantage: Postgres, Temporal and Vault (via Docker), the migrations at head, the API and the web app. It also needs:

1. **The Explorer worker.** `scripts/dev-start.sh` and `scripts\dev-start.cmd` start it automatically:
   - Windows: opens a window titled "AITestGen Explorer Worker" running `scripts\run-explorer-worker.cmd`;
   - macOS/Linux: runs `scripts/run-explorer-worker.sh` in the background, logging to `$LOG_DIR/explorer-worker.log`.

   Both wrap the worker in `watchfiles`, so it reloads on changes under `apps/workers/explorer/src` and `packages/explorer_core`. `scripts/dev-stop.sh` stops it.

   To run it by hand:

   ```bash
   uv run --env-file .env --package explorer-worker python -m explorer_worker.worker
   ```

   It prints `Explorer worker polling task queue 'explorer-task-queue' at localhost:7233`.
2. **Playwright Chromium** installed for the worker's environment.
3. **LiteLLM access**: `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env`. Without them every model call fails with `LITELLM_BASE_URL is not set`.
4. Optional: **ffmpeg** on `PATH` and a bold system font (Segoe UI Bold, Arial Bold or DejaVu Sans Bold) for the highlight video.
5. Optional: **SMTP** settings for the "needs you" emails. Without `SMTP_HOST` they are logged instead of sent.

Then open an application, go to **Explorer**, and press **Start exploring**. Test data can go in the notes, for example "use policy number POL-10001". The notes are remembered as a fact.

## Settings

| Variable | Default | Read by | What it controls |
|---|---|---|---|
| `EXPLORER_REPLACES_DISCOVERY` | `1` | API `discovery.py` | `0` brings back the classic crawler for new apps |
| `TEMPORAL_ADDRESS` | `localhost:7233` | worker | Temporal endpoint |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen` | worker | Database |
| `LITELLM_BASE_URL` / `LITELLM_API_KEY` | none | worker | Model gateway (required) |
| `EXPLORER_THINKING_MODEL` | `gpt-5.6-sol` | worker | Reading, stepping, planning, judging, proofs |
| `EXPLORER_FAST_MODEL` | `gpt-5.6-luna` | worker | Choosing where to look next |
| `EXPLORER_FIRST_LOOK_SCREENS` | `24` | worker | New screens to understand in Stage 1 |
| `EXPLORER_REVISIT_SCREENS` | `10` | worker | New-screen budget when re-running on a seeded map |
| `EXPLORER_FIRST_LOOK_MINUTES` | `25` | worker | Time limit for Stage 1 |
| `EXPLORER_MISSION_STEPS` | `20` | worker | Most steps per mission |
| `EXPLORER_TASK_PASSES` | `1` | worker | How many times each key-task mission is walked, to find conditional screens |
| `EXPLORER_WAIT_MINUTES` | `10` | worker | How long a mission waits for an answer. `0` means it never waits. |
| `EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES` | `8` | worker | Browser jobs in parallel per worker process |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | worker (email) | The link in "needs you" emails |
| `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_FROM_NAME` | – | worker (email) | Mail delivery |

These limits are in code, not env:

| Limit | Value |
|---|---|
| Parallel missions or tests per run | 3 (`workflow.MAX_PARALLEL`) |
| Missions per run | `max(6, min(15, screens/3 + 4))` |
| Tests per run | `max(10, min(60, 5 × screens))` |
| Hunt time | 25 min |
| Wait for confirmation | 14 days |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Explorer is not available" / 503 `EXPLORER_UNAVAILABLE` on Start; onboarding shows discovery failed with `worker_unavailable` | No worker is polling `explorer-task-queue` | Start the worker and check that it printed the "polling" line |
| Run fails at once: "The saved login is missing" | The Vault secret is gone. Dev-mode Vault loses secrets on restart. | Re-enter the app's login in its settings, then press Resume |
| "Couldn't sign in" with a screenshot of the login page | Wrong credentials, or a sign-in form Explorer can't recognise | Check the login. SSO apps need `sso_session_reuse` with a saved session. |
| Run fails with "I couldn't get into the app" | Fewer than 2 screens seen and none had fields or actions | Usually a blank or broken app, or a login that lands on an empty page. Check the app in a normal browser. |
| Behaviour doesn't match code you just changed (Windows) | `watchfiles` reloads can leave **old worker processes still polling**, and Temporal hands work to them | Kill every `explorer_worker` Python process, then start one plain worker |
| A run stays on "Exploring" with one mission "waiting" | It is waiting for an answer for up to `EXPLORER_WAIT_MINUTES` | Answer or skip it in **Questions**. Other missions are not blocked. |
| A mission or test says "Stopped unexpectedly: …" | The activity crashed; the reason is the first line of the error | Read the worker log. One crash never stops the other missions or tests. |
| No highlight video; the feed says it was skipped | ffmpeg or a bold font is missing on the worker machine | Install them, or ignore it: nothing else depends on the video |
| A run was interrupted by a restart | The activity died mid-way | The pool retries each item once automatically. Otherwise press **Resume**; finished work is kept. |
| A run is stuck after code changes to the workflow's steps | An in-flight Temporal history no longer matches the new code (dev only) | Stop, then Resume. Resume terminates the old workflow and starts a fresh one in `resume` mode. |

Useful places to look:

- the **activity log** in the Live tab: every action, error and phase;
- `explorer_event` rows for the run;
- the worker console or `explorer-worker.log`;
- the Temporal UI for workflow `explorer-run-<run external_id>`.

## Testing changes

Run only the narrow tests for what you touched (project rule). Do not run the full suite unless asked.

```bash
uv run --package explorer-worker pytest apps/workers/explorer/tests/test_sense.py -q
uv run --package explorer-worker pytest apps/workers/explorer/tests/test_testkit.py -q -k known_bug
```

The worker tests are pure-logic tests. Unlike the classic discovery-worker suite, they don't launch browsers.

## Known gaps and inconsistencies

These were found while writing these docs. They are worth knowing, and none of them is critical:

1. **Unused client calls.** The web tab doesn't call `addMission`, `regenerateTests`, `report`, or the ZIP, report, video or mission-recording URLs. The endpoints work, but they are unreachable from the UI.
2. **Status lists differ.** The web's `WORKING_STATUSES` includes `confirmed` but not `awaiting_confirmation`. The backend's `ACTIVE_RUN_STATUSES` does the opposite. Polling stops while the run awaits confirmation, which is intended, but the two lists are not the same concept.
3. **Journey grouping.** `promote.py`'s docstring says "one journey per business area", but the code groups by **start screen**.
4. **Plan event wording.** The test-planning event says "up to 6 per screen", but `test_cap` uses 5 per screen.
5. **Document picker.** The upload picker accepts `.pdf,.docx,.txt,.md`. The server also accepts `.csv`.
6. **Same-screen hunt on wizards.** The hidden-field hunt finds nothing when a wizard's branches appear on the *next* step (for example FNOL). Missions cover those instead.
7. **Auto-heal.** The existing Vantage auto-heal may rewrite Explorer's proven code after a failed run.
8. **Storage.** Screenshots and videos live in Postgres, marked with a `ponytail:` comment. Move them to the object store if runs grow large.
9. **Memory recall** is keyword-based, also marked `ponytail:`. Move to vector search if an app's knowledge grows past a few hundred items.
