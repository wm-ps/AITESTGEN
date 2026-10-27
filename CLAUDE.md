# AITestGen — project instructions

## Kebab menus are vertical, not horizontal

Any "more options" row/card menu trigger uses FontAwesome's vertical kebab
(`faEllipsisVertical`, ⋮), never the horizontal one (`faEllipsis`, ⋯) —
matches the Vantage v2 prototype. Applies anywhere a `...` menu trigger is
added (Team members, Applications list, etc.).

## bmad docs are stale — never read them

`_bmad-output/` and `_bmad/` (planning artifacts, implementation-artifact story
files, `project-flow-vs-status.html`) are stale. Do NOT read, reference, cite,
or ground answers in them for any question, in any skill (including the
`bmad-*` skills themselves, `project-progress-visualizer`, or plain code
questions) — even if the user's phrasing points at them. Answer from the
actual current code/tests/git history instead. If the user explicitly asks to
open or work from a specific bmad doc, only then read that one file.

## Never run the full test suite on your own initiative

After any code change, run only the narrow/targeted test(s) for what you
touched (a single file, a single `-k` pattern). Do NOT run a full suite
(`pytest tests/` with no filter, `pytest -q` repo/app-wide, `vitest run` with
no file arg, etc.) unless the user explicitly asks for a full run. This
applies to every app (`apps/api`, `apps/web`, `apps/workers/*`) — the
discovery-worker one especially (see the
`discovery-worker-test-safety` skill: it spins up many real Chromium
instances and can hang for 20-30+ minutes).

## Busy / in-progress indicators — always trailing bouncing dots, never a spinner

Every "this is working" indicator uses `BouncingDots` from
`components/LoadingDots.tsx`, placed *after* the label, never a ring
spinner or a static "…" alone:

- Busy buttons: `<LoadingDots label="Saving" />` (label + trailing dots;
  no "…" in the label).
- A running operation's status (Discovery, Scenario/Test Generation, Test
  Execution/Running, Self-healing): `StatusPill` with `pulsing` already
  renders the trailing dots; elsewhere append `<BouncingDots />`.

## Explorer UI — simple, self-explanatory, nothing invented

The user has had to repeat these many times. Apply them to every Explorer
screen (`apps/web/src/explorer/`) without being asked:

- **Never information-heavy.** Show only what the user needs to act on or
  watch. Everything else is folded (accordion, "Show all") or not shown.
  If a screen needs a paragraph to explain itself, redesign it.
- **Self-explanatory.** Every item that asks something of the user says what
  it is, what the answer changes, and what to do — in the UI, not in chat.
  The user should never need to be taught where or how to answer.
- **Questions live in their own Questions tab.** Anything waiting on the user
  pulses (`explorer-attention`) — the tab dot, the "Waiting for you" box, the
  confirm button — and the Live box links straight to it ("Answer now").
  "Is this a bug?" questions never block Explorer and never appear as
  "Waiting for you"; they sit with the finding they are about.
- **An answer must visibly change the UI** (finding confirmed/removed,
  question gone). Reload whatever the answer affects.
- **No hallucination-prone content.** Don't show the model's guesses about
  the business (who uses it, business objects and statuses, expected rules,
  "parts that may appear sometimes"). Showing something wrong puts the
  product in the back seat. When unsure whether data is grounded, leave it out.
- **Live first.** The Explorer tab opens on the live view with its activity
  log visible; side-by-side panels end at the same height.
- **Explorer's output is the scenarios.** An Explorer app
  (`discovery_engine === 'explorer'`) has no Journeys / Scenarios pages in
  the sidebar; Explorer's own Scenarios tab is where tests are generated.
  The journey/scenario rows still exist underneath for test generation.
- **No map/graph views.** Screens are a screenshot grid; clicking one shows
  its actions and where each leads.
- **Findings stay quiet.** "Things that look wrong" go last and folded; on a
  screenshot they are a small count, never a big label over the image.
- **Never confirm or answer on the user's behalf** (App Summary, questions)
  while testing — that is the user's consent.

## Input placeholder copy — instructional, never a fake example

A field's `placeholder` must tell the user what to do (`"Enter the
application name"`, `"Enter your email"`), never hand them a fabricated
example value/domain (`"e.g. Apex Insurance Portal"`, `"you@company.com"`,
`"Checkout Regression"`). Invented example data reads as AI slop. The one
exception is a field whose valid syntax genuinely isn't guessable from an
instruction alone (e.g. a cron expression) — there, a real-format example
is the actually-helpful placeholder.
