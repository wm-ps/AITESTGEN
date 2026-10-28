---
last_updated: 2026-10-27
---

# Story 2.22: Coverage Report & Run Diagnostics

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want an honest account of what Discovery reached, what it couldn't reach, and why it decided what it did,
so that I can trust the result, act on the gaps and tune Discovery for my application instead of guessing.

## What it does today

- For any Discovery run, Vantage can produce a coverage report with five sections:
  - **Reached:** screens recorded, actions performed, forms captured.
  - **Blocked:** each missing value or approval, with how many paths are waiting on it (Story 2.15).
  - **Skipped for safety:** what was refused and why (Story 2.12).
  - **Unreached:** actions given up on when Vantage couldn't get back to a screen (Story 2.11), frames from other sites, and closed embedded components (Story 2.14).
  - **Errored:** failures, each with its discovery error code (Story 2.18).
- The report also includes the engine's own reasoning, grouped by topic:
  - same/variant/new decisions and scores, and whether content-based comparison was switched on (Story 2.10)
  - the share of saved locators that are fragile (Story 2.21)
  - values the application rejected (Story 2.13)
  - safety decisions and anomalies (Story 2.12)
  - which loop check fired where (Story 2.19)
- Each section is filled independently. A missing section shows as unavailable instead of breaking the report.
- The report is available as structured data from the server only.

## Acceptance criteria

1. **Given** a finished run, **when** its report is requested, **then** it contains the Reached, Blocked, Skipped for safety, Unreached and Errored sections.
2. **Given** the engine made decisions during the run, **then** the report includes the diagnostics listed above.
3. **Given** a section's data isn't available, **then** the rest of the report is still produced.
4. **Given** a finished run, **then** the report can be fetched as structured data, independent of any screen.

## Gaps / not built

- **No screen shows the report.** Users only see "Discovery completed" and the journey cards. That lets a run cut short by a limit, or full of blocked and skipped areas, look as if the whole application was covered.
- The report doesn't say why the run stopped (everything explored, page limit or time limit), even though Vantage records it (Story 2.3).
- There is no option to export or download the report.
