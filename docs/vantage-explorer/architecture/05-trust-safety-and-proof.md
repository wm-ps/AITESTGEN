# 5. Trust, safety and proof

> Diagram: [Trust model: where "correct" comes from](diagrams/explorer-trust.html)

Sections 1 and 2 are for everyone. Sections 3 and 4 are the exact rules in the code.

## 1. The app is evidence, not the truth

If Explorer wrote down whatever the app does and called it correct, it would turn bugs into "expected behaviour" and write tests that protect them. So Explorer decides **what should happen before it looks at what does happen**.

Where "should" comes from, most trusted first:

| Trust | Source | How it enters Explorer |
|---|---|---|
| **Confirmed** | You and your team | Answers to questions, App Summary answers, facts you type, run notes → `explorer_knowledge` |
| **Confirmed** | Your documents | Uploaded PDF/Word/text, split into passages of about 1,500 characters → `explorer_knowledge` (kind `doc`) |
| **Standard** | Common sense and industry rules | The model's general knowledge, for example "an email needs an @" or "an end date can't be before the start date" |
| **Seen only** | What the app did | Screens, maps, observed outcomes. These are only *facts about the app*. |

How the code applies it:

- Every prompt starts with the stance "the application is EVIDENCE, not the truth" (`brain.STANCE`).
- Every prompt carries up to 60 remembered facts as **trusted** knowledge (`session._with_memory`).
- Each mission stores its `expected` outcome **before** it runs, and `judge_outcome` compares against it afterwards.
- Each test stores `expected` and a `trust` label (`confirmed`, `standard` or `seen`).
- When the app's health score is below 60, the run is flagged `requirements_first`, so Explorer leans more on your knowledge.

### What happens on a mismatch

| Where | Result |
|---|---|
| Mission outcome differs from expected | A **possible bug**: a `looks_wrong` health issue, plus a non-blocking "It's a bug / It's correct" question. Your answer becomes knowledge. "Correct" marks the issue `accepted`; "bug" raises it to high severity. |
| Test: the app does something other than it should | The test is kept as **`known_bug`**. Its code starts with `test.fixme(true, "Known bug — should: … The app currently: …")`. |
| Hunt: the page goes blank when the server fails | A possible bug: "<screen> goes blank when the server has a problem". |

Explorer **never answers or confirms on the user's behalf**. Confirming the App Summary and answering questions is the user's consent.

## 2. What Explorer will and won't click

| Situation | Behaviour |
|---|---|
| While learning the app (Stage 1) | Never clicks anything risky: delete, remove, cancel policy/order/account, deactivate, approve, reject, pay, purchase, checkout, submit, save, confirm, send, transfer, archive, reset, log/sign out. |
| Links and buttons that **always** need your OK (any environment) | delete, remove, destroy, deactivate, terminate, pay, buy, sell, redeem, purchase, checkout, transfer, withdraw, password changes, approve, reject, decline, archive, reset, refund, place order, sign out, and "cancel" of a policy/order/account/subscription/claim. Also any button whose verb matches the mission's own risky goal. |
| A final Save/Submit/Send on a **test environment** (`safety_posture = non_production`) | Allowed, so missions can create their own test data, as long as the button isn't on the list above. |
| A final Save/Submit/Send on **production** | Always asks "May I press …?". Without a yes, it stops before the button. |
| The same final button twice | Never. It is pressed at most once per walk. |
| Logins | Typed by code, never by the model. A wrong password is never typed after the real username, to avoid lockouts. |
| Simulated server answers (hunt) | Intercepted inside Explorer's own browser only. The real server never sees them. |
| Upload fields | Uses built-in sample files. It never asks you for files. |

Code: `sense.is_risky_label`, `is_risky_link`, `looks_final`, `needs_human_ok`, `may_commit`, and the safety gate in `pursue.py`.

## 3. Grounding: no invented content

- A test is dropped if its start screen is not one Explorer actually saw: "Refers to a screen Explorer never saw".
- Screens whose condition starts with "Simulated" are never used as test start points.
- A test whose proof was already on screen before it acted is rejected (see below).
- The UI hides the model's guesses about the business: who uses it, business objects and statuses, expected rules, and "parts that may appear sometimes". The App Summary view shows only the app name, the one-liner, the questions, the key tasks, focus, and screens to leave out.

## 4. How a test is proven

`tests_stage.build_and_prove` works through the following steps. A test that fails any step is **dropped** with a reason. Dropped tests are hidden in the UI.

```
plan ─▶ build once (AI drives) ─▶ pick a proof ─▶ replay ×3 (no AI) ─▶ replay broken copy ─▶ proven | known_bug
```

1. **Build once.**
   - Opens a browser at the start screen. Signed-out tests use a separate signed-out browser; stateful apps fast-forward along the recorded path.
   - Walks the test with `pursue` (12 steps, or 24 for stateful apps), using a quiet `Mind` that doesn't re-read screens.
   - The instruction ends with "Stop as soon as the outcome of the test is visible on screen."
   - The result is an exact action script.
2. **Pick a proof.**
   - `decide_check` looks at the final screen and returns a proof: on-screen text (`text_visible`) or a URL fragment (`url_contains`).
   - A proof whose value was already in the starting page text or URL is **rejected**, and the model is asked again, up to 3 times. If every proof was already on screen, the test is dropped.
   - The model also returns `matches_expected` and `set_up_ok`. If either is unclear, the test gets **one** retry with a written "lesson". After that it is dropped, and it never reports a bug the test caused itself.
3. **Replay 3 times with no AI** (`testkit.replay` + `testkit.holds`) in a fresh, recorded browser. All 3 must hold, or the test is dropped with "Gave different results on repeat runs (p/3 passed)".
4. **Replay the broken copy.** `without_decisive_step` removes the last real action. The proof must now **not** hold (`catches_breakage = True`), or the test is dropped with "Still passed with its key step removed".
5. **Verdict.**
   - The test becomes `proven` if the app matched what should happen, otherwise `known_bug`.
   - The proof video is saved as `explorer_recording` (`test_case_id`).
   - The Playwright code is saved in `code`, tagged `@auth` or `@public`.

**Page-quality checks** (`quality.py`) are measured 3 times. The results must agree. Failing results make the check `known_bug`.

### The exported Playwright test

`testkit.playwright_code` produces a self-contained TypeScript spec:

- `test("<title>", { tag: '@auth' | '@public' }, async ({ page }) => { ... })`
- timeouts: navigation 30 s, assertion 15 s, test 180 s
- each step is a commented, resilient locator chain: `getByLabel(...).or(field after caption)`, role-based clicks, and waits for the page text to change
- credentials come from `CREDENTIALS` in `support/config`, never as literals
- the final assertion is `toHaveURL(/…/)` or `getByText(value).toBeVisible()`
- known bugs start with `test.fixme(...)`, carrying the expected vs actual text

The download (`GET /explorer/runs/{id}/tests/download`) wraps these specs in the same project scaffold the classic suite assembler writes. The files are laid out as `tests/<kind>/<title>.spec.ts`.
