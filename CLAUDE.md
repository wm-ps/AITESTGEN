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

## Button loading state — always the ring spinner, never bouncing dots

Any button's busy/submitting state uses the ring `Spinner` from
`components/LoadingDots.tsx` (same `currentColor` + `aitg-spin` look
StatusPill's dot already uses), never a bespoke bouncing-dots or other
spinner. `LoadingDots({ label })` already renders `<Spinner size={12} />` +
label internally, so existing call sites don't need to change — just don't
reintroduce dot-bounce-style loading indicators for new buttons.

## Input placeholder copy — instructional, never a fake example

A field's `placeholder` must tell the user what to do (`"Enter the
application name"`, `"Enter your email"`), never hand them a fabricated
example value/domain (`"e.g. Apex Insurance Portal"`, `"you@company.com"`,
`"Checkout Regression"`). Invented example data reads as AI slop. The one
exception is a field whose valid syntax genuinely isn't guessable from an
instruction alone (e.g. a cron expression) — there, a real-format example
is the actually-helpful placeholder.
