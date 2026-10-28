---
last_updated: 2026-10-27
---

# Story 2.10: Recognising Same, Variant and New Screens

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to tell a genuinely new screen apart from the same screen showing different data, and to record why it decided,
so that Discovery doesn't miss real variations or waste time re-exploring duplicates, and a poorly tuned run can be diagnosed.

## What it does today

- Every time Vantage reaches a screen, it decides whether it is:
  - **the same** as one it has already seen, just with different data (for example claim 1001 and claim 1002). It is not explored or recorded again.
  - **a variant** of a known screen: same kind of page, but the actions on offer differ (for example a claim showing Edit/Submit versus one showing Approve/Reject). It is recorded as its own related screen, and each version can belong to different journeys.
  - **new**: it is fully explored and recorded.
- **How it decides.**
  - First, the shape of the address. Two addresses that differ only by an ID count as the same kind of page. If no known screen has the same address shape, the screen is new straight away.
  - Otherwise it compares the heading, the actions on offer, the form fields and the overall page layout, and gives a similarity score. Content inside embedded components (shadow DOM) is included, so screens that differ only there are told apart.
  - High scores mean "same", low scores mean "new", and the middle band means "variant". The cut-off points can be set per application; there is no screen for changing them.
- **Borderline cases.** When the score falls in the uncertain middle, Vantage also asks the AI for a second opinion. The AI's view is only recorded alongside; Vantage's own rule makes the decision. If the AI is slow or fails, nothing changes.
- **Apps whose address never changes.** Some single-page apps keep the same address on every screen. When Vantage detects this, it relies on page content instead of addresses, and notes once per run that it has done so.
- Every decision is written to the run's diagnostics (Story 2.22): what was compared, the scores, the cut-offs and the verdict. No decision is silent.
- Comparisons are only made within the current run, against screens already confirmed. Merging duplicates across separate runs is handled afterwards by Story 2.5.

## Acceptance criteria

1. **Given** a screen whose address shape matches no known screen, **then** it is classed as new without further comparison.
2. **Given** a known screen with the same address shape, **then** heading, actions, form fields and layout are scored, and the result is same, variant or new according to the application's cut-offs.
3. **Given** two claim screens that differ only by record, **then** they are the same; **given** two with different available actions, **then** they are variants and both can belong to journeys.
4. **Given** a borderline score, **then** the AI's opinion is recorded as supporting information only, and a failed AI call doesn't change the outcome.
5. **Given** an app whose address never changes, **then** Vantage switches to content-based comparison and logs this once per run.
6. **Given** any decision, **then** its inputs, scores, cut-offs and verdict are written to the run diagnostics.
