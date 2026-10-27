---
last_updated: 2026-10-27
---

# Story 2.12: Safety Engine — Risky Actions, Caution Level & Post-Action Checks

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage never to perform a clearly destructive action during Discovery, and to let me choose how cautious it is about everything else,
so that Discovery can't cause irreversible damage, without throwing away coverage I didn't ask to lose.

## What it does today

- Before clicking anything, Vantage reads the action's visible name and sorts it into one of three groups:
  - **Safe:** View, Open, Expand, Collapse, Navigate, Tab, Paginate, Search, Filter.
  - **Clearly destructive:** Delete, Remove, Terminate, Transfer, Payment and similar.
  - **Ambiguous:** anything that changes data, such as Submit, Approve, Reject, Save, Confirm or Proceed. Anything that matches no list also counts as ambiguous, never as safe by default.
- **Clearly destructive actions are never performed**, whatever the setting. They are skipped and listed under "skipped for safety".
- **Ambiguous actions** depend on the application's caution level:
  - "Non-production" (the default) performs them, to get the most coverage.
  - "Production" puts them aside as blocked items needing approval (Story 2.15).
- **Post-action checks.** After a safe action, Vantage compares the screen before and after. If it changed unexpectedly, this is noted as a safety anomaly in the diagnostics. It never stops the run and never tries to undo anything.
- Every safety decision is recorded: the action name, which list it matched, the caution level and the verdict.
- Separately, the admin's Interaction level setting (Passive / Normal / Aggressive) limits which kinds of action are tried at all (see Story 2.11).
- Test runs (Epic 6) don't apply these safety rules. Running tests is deliberately left unrestricted.

## Acceptance criteria

1. **Given** an action, **then** it is classed as safe, clearly destructive or ambiguous by its name, and an unmatched action is never treated as safe.
2. **Given** a clearly destructive action, **then** it is never performed, and the data check is not even asked.
3. **Given** an ambiguous action, **then** it is performed under "non-production" and put aside for approval under "production".
4. **Given** a safe action changed the screen unexpectedly, **then** an anomaly is recorded in diagnostics and the run continues.
5. **Given** any safety decision, **then** the action, matched list, caution level and verdict are recorded.

## Gaps / not built

- There is no screen or setting to choose an application's caution level. Every application runs as "non-production", so ambiguous actions (Submit, Save, Approve…) are always performed.
- The AI second opinion for wording the lists can't settle exists, but it is not switched on; classification is rule-based only.
- Actions put aside for approval can't be approved anywhere in the product (see Stories 2.15 and 2.16).
