# 5. Trust, safety and proof

> **In short.** There are three rules:
> 1. Explorer decides what *should* happen before it looks at what the app *does*, so bugs are caught instead of copied.
> 2. A fixed word list in the code, not the AI, decides which buttons need your OK.
> 3. A test is kept only if it replays reliably without AI **and** fails when its key step is removed.

**Part 1 (sections 1–3) is plain language, for everyone. Part 2 (sections 4–7) is the exact rules in the code.**

---

# Part 1 — The ideas

## 1. The app is evidence, not the truth

![Trust](diagrams/img/p7-trust.png)

Explorer works out what is "correct" from four sources, in order of trust:

| Trust label | Source | How it gets into Explorer |
|---|---|---|
| **Confirmed** | You and your team | Your answers to questions, App Summary answers, facts you type, Start-card notes |
| **Confirmed** | Your documents | Uploaded PDF, Word or text files, split into passages of about 1,500 characters |
| **Standard** | Common sense | What the AI generally knows, for example "an email needs an @" |
| **Seen only** | What the app did | Screens and outcomes. These are facts about the app, **never proof that it is right**. |

## 2. What Explorer may press

![Safety](diagrams/img/p6-safety.png)

## 3. How a test earns its place

![Proving](diagrams/img/p11-proving.png)

---

# Part 2 — The exact rules

## 4. Where "should" enters the code

- **Every AI prompt** starts with the same instruction: *"the application is EVIDENCE, not the truth"* (`brain.STANCE`).
- **Every prompt** includes up to 60 remembered facts for the app, labelled as trusted (`session._with_memory`).
- **Every mission** saves its `expected` outcome *before* it runs. Afterwards, `judge_outcome` compares the final screen with it.
- **Every test** saves `expected` together with a `trust` label: `confirmed`, `standard` or `seen`.
- **Health below 60** sets `requirements_first` on the run, so Explorer leans harder on what you've told it.

### What happens when "should" and "did" differ

| Where | Result |
|---|---|
| A mission | It becomes a **possible bug**: a `looks_wrong` health issue, plus a non-blocking question, "It's a bug / It's correct". If you answer "correct", the issue is marked `accepted` and the rule is remembered. If you answer "bug", the issue becomes high severity. |
| A test | The test is kept as **`known_bug`**. Its code starts with `test.fixme(true, "Known bug — should: … The app currently: …")`. |
| The hunt | If a page goes blank when the server fails, that is recorded as a possible bug. |

Explorer **never answers a question or confirms the summary on your behalf**. Those actions are your consent.

## 5. The button rules (in `sense.py`)

| Rule | Words it matches | Effect |
|---|---|---|
| `is_risky_label` | delete, remove, cancel policy/order/account, deactivate, approve, reject, pay, purchase, checkout, submit, save, confirm, send, transfer, archive, reset, log/sign out | **Never clicked while looking around** (stage 1) |
| `needs_human_ok` | delete, remove, destroy, deactivate, terminate, pay, buy, sell, redeem, purchase, checkout, transfer, withdraw, password, approve, reject, decline, archive, reset, refund, place order, sign out, cancel policy/order/account/subscription/claim, plus the risky verb of the mission's own goal | **Always asks you**, on every app |
| `may_commit` | everything else that is final (Save, Submit, Send…) | Allowed only when the app is marked `non_production` (a test copy). On a live app it asks. |
| Same final button twice | — | Never pressed again in the same walk |

When Explorer must ask, `pursue.py` creates a "May I press …?" question with the options *Yes, press it* and *No, stop here*. Without a yes, it ends the mission just before the button.

Other safety rules:

- **Logins** are typed by code. A wrong password is never typed after the real username, which avoids account lockouts.
- **Upload fields** get built-in sample files. Explorer never asks you for files.
- **Simulated server problems** are intercepted inside Explorer's own browser (`page.route`) and never reach your server.

## 6. The exact proof steps

The proof steps live in `tests_stage.build_and_prove`.

```
plan → do it once (AI drives) → pick a proof → replay ×3 (no AI) → replay with key step removed → proven | known_bug
```

1. **Plan.** A test is dropped if its starting screen is one Explorer never saw ("Refers to a screen Explorer never saw"). Simulated screens are never used as starting points.
2. **Do it once.**
   - Explorer opens the starting screen. Signed-out tests use a separate signed-out browser. Apps that keep saved progress are fast-forwarded along the recorded path.
   - The AI walks the test, in up to 12 steps (24 for apps with saved progress), and stops as soon as the outcome is visible.
   - Every action is recorded as an exact script.
3. **Pick a proof.**
   - The AI chooses either text on screen (`text_visible`) or part of the web address (`url_contains`).
   - If that proof was **already** on the starting page, it is rejected and the AI is asked again, up to 3 times.
   - If the AI is unsure whether the test worked or was set up correctly, the test gets one retry with a written lesson. After that it is dropped.
4. **Replay 3 times with no AI** (`testkit.replay` + `testkit.holds`) in a fresh, recorded browser. All 3 replays must show the proof.
5. **Replay with the key step removed** (`without_decisive_step`). The proof must **not** show this time, which sets `catches_breakage = True`.
6. **Verdict.**
   - The test is `proven` if the app did what it should, otherwise `known_bug`.
   - The replay video is saved.
   - Playwright code is saved, tagged `@auth` or `@public`.

**Page-quality checks** are four browser measurements with no AI involved:

- the page loads cleanly;
- no images are broken;
- the page fits a phone screen;
- every field has a label.

Each check is measured 3 times, and the results must agree.

## 7. What the exported test looks like

`testkit.playwright_code` writes one self-contained TypeScript file per test:

- `test("<title>", { tag: '@auth' | '@public' }, async ({ page }) => { … })`
- Time limits: 30 s per page load, 15 s per check, 180 s per test.
- Each step is commented and finds elements the way a person would: by label (`getByLabel`), by button name (`getByRole`), and by waiting for the page text to change.
- Logins come from `CREDENTIALS` in `support/config`. They are never written into the test.
- The last line checks the proof: `toHaveURL(/…/)` or `getByText(value).toBeVisible()`.
- Known bugs start with `test.fixme(...)`, which states what should happen and what the app does today.

The **Download tests** endpoint packs these into the same project layout Vantage's suite download uses, as `tests/<kind>/<title>.spec.ts`.
