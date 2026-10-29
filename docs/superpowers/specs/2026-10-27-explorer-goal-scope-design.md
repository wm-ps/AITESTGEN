# Explorer: the run's Goal becomes a strict scope

Date: 2026-10-27 · Branch: `feature-crawl2.0` · Area: Vantage Explorer
(`apps/workers/explorer`, `apps/web/src/explorer`, `apps/api/src/api/explorer.py`)

## Why

A user often cares about one part of an application, not all of it ("only the
claim reporting flow, up to policy search", "leave out Check a claim").
Exploring everything costs hours and tokens and produces scenarios nobody
asked for. The App Summary already has an optional "Goal for this run" box,
but what is typed there is only a hint at the top of two planning prompts
(`brain.scope()` in mission and scenario planning). Missions, follow-up
missions, the hidden-screen hunt and scenario building can all go past it.

The user wants that one box to become a **strict rule** Explorer follows for
the rest of the run, with no new screens or controls.

## What the user decided

1. **Keep the existing box.** The App Summary's "Goal for this run (optional)"
   text area (`SummaryView.tsx`, `brief.focus`) stays where it is. The section
   heading **"What to cover" is renamed "Goal"**. No other UI change: no
   playback card, no extra approval step, no new fields. The screen-untick
   grid ("Left out", `brief.skip_screens`) stays as it is.
2. **Free text, any instruction.** The user writes in their own words: a
   module to cover fully, a module to leave out, a stop point, or another
   instruction. Explorer must understand the intent from the text.
3. **Strict.** Whatever the goal says, every stage after confirmation obeys
   it: mission planning, follow-up missions, the hidden-screen hunt (choices,
   faked server answers, page addresses from the code), scenario planning,
   journeys and scenario building. Nothing outside the goal is explored or
   tested.
4. **A stop point** ("up to policy search"): the stop screen itself is
   **tested fully** (required fields, wrong values, valid values, links,
   Back). The screen that comes right after it may be **looked at only as
   proof** that a test worked (e.g. pressing Find my policy with a valid
   number and seeing Policy selection appear). Explorer never fills in,
   presses or tests anything on that next screen, and explores nothing beyond
   it.
5. **Empty goal = the whole app**, exactly as today.
6. **Confirm needs every question answered.** Pressing the App Summary's
   confirm button ("Looks right — confirm") while any "Questions for you" item
   is unanswered must not confirm; it shows a message asking the user to
   answer the questions first. Today the button confirms anyway (only a hint
   in the questions header says "Pick an answer for N before you confirm").

## Goals

- The Goal text, when present, limits exploration and testing to what it
  describes, at every stage after the App Summary is confirmed.
- Generic: works for any application and any wording, never FNOL-specific.
- A scoped run is much shorter than a whole-app run.
- Confirming with unanswered questions is impossible, and the user is told
  why.

## Non-goals

- No change to the first look (Stage 1). It runs before the user can type a
  goal; it may have seen a few screens outside the goal. Those simply get no
  missions or scenarios. (User accepted this in conversation.)
- No new UI for showing Explorer's interpretation of the goal (the user
  explicitly rejected a playback / approval card).
- No goal field when adding an application; the goal is per run, on the App
  Summary.
- No editing the goal after confirmation (the brief is locked once confirmed,
  as today).

## Anti-goals (would be a failure even if it "works")

- Explorer goes past the stop point and fills in or tests anything there.
- Scenarios or missions appear for screens the goal leaves out.
- The proof screen after a stop point gets its own scenarios.
- Accuracy drops: in-scope scenarios must still pass the same proof gate
  (broken-on-purpose run + clean replay) as today.
- An empty goal behaves differently from today.

## Constraints

- Follow the repo's CLAUDE.md: Explorer UI simple, nothing invented; never
  answer or confirm on the user's behalf; button busy state uses the ring
  Spinner; no fake-example placeholder text.
- Do not change code while an Explorer run is active (workers restart on
  edits).
- Targeted tests only, never the full suite.
- Shared/Standard code is not modified for this; changes stay in Explorer's
  own modules (plus the App Summary screen and the Explorer API).

## How it should behave (decided)

- The goal is read once, at confirmation, and applied to everything after.
- **Screens found later.** Most screens are discovered during missions, after
  the goal is set, so Explorer must judge each **newly reached** screen
  against the goal as it goes. Reaching a screen outside the goal (or past the
  stop point) ends that walk there; that screen is not explored further and
  gets no follow-up missions or scenarios. The one exception is the screen
  right after a stop point, which a scenario may land on only to prove its
  result.
- **Scenarios** are planned only for screens inside the goal (the stop screen
  included). A scenario whose expected result is "the next screen opens" may
  use that next screen's appearance as its proof, and stops there.
- **Missions and follow-ups** are planned only toward screens and flows
  inside the goal; a follow-up is never created for a choice on a screen
  outside it.
- **Hidden-screen hunt**: choices, faked server answers and the code's page
  addresses are tried only on screens inside the goal.
- **Leave-out goals** ("everything except Check a claim"): the named part is
  never explored or tested; everything else is covered as for an empty goal.
- The existing screen-untick list (`skip_screens`) keeps working and is
  combined with the goal (both must allow a screen).
- **Confirm with unanswered questions**: the confirm button stays looking
  enabled (repo pattern: a blocked click shows a message rather than a
  disabled button). Clicking it shows a short message next to the button, for
  example "Answer the questions first — they change what Explorer tests", and
  brings the Questions section into view. The API's confirm endpoint also
  refuses to confirm while a question is unanswered (my call: so the rule
  can't be bypassed), returning a plain message.

## Calls made by Claude (user to check)

These were not discussed; each is a sensible default the user can overrule.

1. **Screens on the way in are passed through, not tested.** If reaching the
   goal's screens needs screens outside the goal (a home page, a menu, a
   landing step), Explorer may move through them the way a user would
   (press navigation, enter data that is needed to get through) but never
   tests them, plans nothing for them and explores nothing else from them.
   So the per-screen judgement has three answers: inside, outside, or "on
   the way in".
2. **The goal is read literally.**
   - "Only X up to Y" / "just X": nothing outside flow X is explored; X stops
     at Y.
   - A stop point with no "only" ("stop at policy search"): the rest of the
     app is covered as usual; only the path through Y is cut there.
   - Branches inside the named flow, before the stop, are inside the goal
     (for FNOL "claim reporting up to policy search": Find your policy
     another way is in; Check a claim, a separate flow, is out).
3. **The user's own explicit actions win.** A mission the user adds
   themselves after confirming (the API supports this; there is no UI for it
   today) is carried out even if it falls outside the goal, and the Live
   feed says it is outside the goal. Missions Explorer plans itself, and its
   follow-ups, always obey the goal.
4. **Only the App Summary's own questions block confirm**
   (`brief.questions_for_you`). Questions-tab items and "is this a bug?"
   questions never block (CLAUDE.md).
5. **Runs confirmed before this ships** turn their goal into the strict
   scope the first time a later stage needs it (for example, on resume), so
   old runs behave the same as new ones. A run with an empty goal is
   unchanged.

## Left to the builder

- How the free-text goal is turned into something Explorer can apply (for
  example: one model call at confirmation that turns the goal plus the known
  screens into an in/out/stop description, kept on the run; and/or adding an
  "inside the goal?" judgement to the existing per-screen reading in
  `brain.perceive`, which already runs once per new screen, so no extra model
  call per screen). Choose what is reliable and cheap.
- Where the check sits in the code (`pursue`, `missions.follow_ups`,
  `hunt`, `breadth`, `tests_stage`, the planners).
- Exact wording of the message and of the renamed heading's surroundings.
- Logging: a plain Live-feed line when a walk stops because it reached the
  edge of the goal (e.g. "Reached the edge of your goal: Policy selection").
- Tests: one targeted test per rule (stop point, leave-out, proof screen,
  empty goal unchanged, confirm refused with unanswered questions).

## Open risks

- The model may misjudge whether an unfamiliar screen is inside a loosely
  worded goal. Mitigation is the builder's choice; erring towards "outside"
  wastes coverage, erring towards "inside" wastes time.
- A stop point named by business words ("policy search") must be matched to
  the real screen (here "Find your policy"); naming varies by app.
