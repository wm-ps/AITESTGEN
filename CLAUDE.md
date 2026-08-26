# AITestGen — project instructions

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
