---
last updated: 2026-10-27
---

# Story 6.7: Run-completed email

Status: done

## Story

As the person who started a test run (or owns a schedule),
I want an email when the run finishes that tells me the outcome and what failed,
so that I don't have to keep checking Vantage to know whether my application is healthy.

## What it does today

- **Who gets it:**
  - **Manual runs:** the person who started the run.
  - **Scheduled runs**, including **Run now** on a schedule: the person who created the schedule.
- **Subject:** a mark (✓ passed, ✕ failed, ! couldn't run), the run number, the application name and a one-line headline. Examples: "All 12 tests passed", "3 of 12 tests didn't pass", "Run couldn't complete", "No tests ran".
- **Outcome rules:**
  - **Passed:** something ran and nothing failed, timed out or errored.
  - **Couldn't run:** nothing passed and nothing actually failed, meaning every test errored or nothing ran.
  - **Failed:** anything else.
  - The pass rate is rounded down, so 100% always means every test that ran passed.
- **Body:**
  - the outcome banner and pass rate;
  - the shared-cause line when most failures share one environment problem (see Story 6.5);
  - up to 10 failed tests, each with its plain-language explanation, plus a note of how many more there are;
  - **View report** (the HTML report, Story 6.6) and **Open in Vantage** buttons. The Vantage link opens the run directly after sign-in.
  - A plain-text version is included for mail clients that don't show HTML.
- **Sent at most once per run.** In rare failure cases it may be lost, but it is never sent twice.
- **Not sent:**
  - for cancelled runs;
  - for runs closed out by the background sweep after getting stuck or failing to finish normally;
  - after a manual self-heal retry.
- **No mail server configured:** the email is not sent; it is only noted in the server log.

## Acceptance criteria

1. **Given** a manual run finishes, **when** it completes normally, **then** the person who started it receives the run-completed email.
2. **Given** a scheduled run (or Run now) finishes, **when** it completes normally, **then** the schedule's creator receives the email.
3. **Given** a run, **when** the email is built, **then** the subject shows the outcome mark, run number, application name and headline, following the outcome rules above.
4. **Given** a run with failures, **when** the email is built, **then** up to 10 failures are listed with plain-language explanations, and a count of any others.
5. **Given** most failures share one environment-level cause, **when** the email is built, **then** that cause is called out above the failures.
6. **Given** the email, **when** the recipient clicks **Open in Vantage**, **then** they land on that run after signing in. **When** they click **View report**, **then** the HTML report opens.
7. **Given** a run was cancelled, or closed out by the stuck-run sweep, **when** it ends, **then** no email is sent.

## Gaps / not built

- Recipients can't be chosen or added (no team or distribution list), and there is no opt-out setting.
- No email is sent when a run fails to finish normally.
- If a self-heal fix was rejected, the email may show the rejection message instead of the original error for that test.
