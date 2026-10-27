---
title: "Change record — Discovery engine redesign (2026-07-29)"
status: approved
created: 2026-07-29
last updated: 2026-10-27
---

# Change record: Discovery engine redesign (2026-07-29)

## What was proposed and why

A design paper proposed redesigning how Discovery decides what to do while it explores an application. The early engine:

- crawled breadth-first with a few shortcuts;
- waited a fixed time for pages;
- had no proper idea of when a page was "the same" as one already seen;
- clicked anything not obviously excluded;
- had no plan for fields it couldn't fill;
- couldn't pause and continue later;
- had no consistent error codes.

The proposal added eleven new Discovery stories (2.9 to 2.19), plus small changes to existing ones, without changing the order of the epics:

- Wait until a page is genuinely ready (with a configurable timeout), and sample infinite scroll and "load more" a few times instead of endlessly.
- Classify each screen as the same, a variant, or new, so near-identical records aren't explored twice.
- Finish a page's own buttons, tabs and forms before following navigation links.
- **Safety:** never click clearly destructive actions (delete, pay, transfer), set aside ambiguous ones (submit, approve), and flag unexpected changes after "safe" clicks. This deliberately reversed an earlier decision to have no safety guard.
- Fill inputs in a set order: values the user supplied, values already seen, then safe made-up data. Anything that needs real business data is set aside, never guessed.
- Handle tabs, dialogs, pop-up windows and file uploads properly.
- Collect set-aside items into one combined request for the user, without stopping the run.
- Remember the exact path to a blocked step so it can be replayed once the missing data is supplied.
- Pause a whole Discovery effort and resume it later without redoing confirmed work.
- Recover automatically from crashes, and give every error a plain code.
- Loop-prevention backstops.
- Carry test data used during Discovery forward as the default in generated scenarios.

## What was decided

- Approved.
- The crawl-time path to a blocked step was given its own name, so it wouldn't be confused with business journeys.
- Applications stand in for "projects", so no new concept was added.
- Pause support was added to Discovery runs.
- The safety reversal and two screens with no design yet were flagged for sign-off before building.

## Where it stands today (2026-10-27)

**Largely shipped (Discovery engine v2, August 2026).**

| Proposed | Today |
|---|---|
| Page readiness and scroll sampling | Built. Waits for the network and screen to settle, with a per-application timeout; scroll and "load more" are sampled. |
| Same / variant / new screens | Built. |
| In-page actions before navigation | Built. Tabs inside a page are explored before navigation links. |
| Safety rules | Built, rule-based only. Destructive actions are refused; ambiguous ones are refused depending on the application's safety setting; unexpected changes after a safe click are recorded. The AI second opinion exists but is not switched on. |
| Ordered input filling | Built, except reading values off the current page. |
| Tabs, dialogs, windows, uploads | Built. |
| Combined requests for missing data | In the classic engine, collected behind the scenes; **no screen lets a user answer them**. Explorer, now the default discovery engine, does this: it asks questions when it needs data, is unsure or is about to do something risky, takes answers in its Questions panel and keeps every answer as knowledge for the application. |
| Replay a blocked path after data is supplied | **Not connected.** The groundwork exists, but nothing uses it. |
| Pause and resume | Built as **Pause Discovery / Resume Discovery** on the Journeys tab; resume continues from where it stopped. The planned Confirmed / Blocked / Remaining summary was never built. |
| Crash recovery and error codes | Built. A worker restart resumes the run and shows a "recovered" banner. Errors use a short fixed list of codes (restart, session expired, unreachable page, page didn't settle, lost track after a form, form field timed out). |
| Loop prevention | Built. |
| Carry Discovery test data into scenarios | Not found in the current product. Scenario test data is filled by the user or by Auto-generate. |

Related since then:

- Admins can set Discovery limits in Settings (time, pages, journeys, navigation timeout, interaction level).
- Discovery can be skipped entirely for an application.
- Applications that need sign-in have their login checked before Discovery starts.
- Explorer replaced this engine as the default for new applications. The engine described here is now "classic discovery" and runs only for applications discovered before the switch, or when operations switch Explorer off.
