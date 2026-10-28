---
last_updated: 2026-10-27
---

# Story 2.20: Test Data Pool — Business Values Supplied Before Discovery

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want to give Vantage the business-specific values it will need before Discovery starts,
so that it explores straight through areas that would otherwise be blocked, instead of stopping and asking me afterwards.

## What it does today

- Each application can hold a pool of test data entries. Each entry has a label, a value, and a "sensitive" flag. Entries are kept across Discovery runs.
- Each entry is filed under a normalised name (lower-case, punctuation dropped, word order ignored). This is the same rule blocked items use (Story 2.15), so a pool entry and a blocked request for the same field match automatically.
- When Discovery needs a value, it checks the pool **first**, before reusing a value from earlier in the run or making one up (Story 2.13). Values taken from the pool are recorded like any other value used.
- Sensitive entries are stored in the encrypted secrets store, not alongside ordinary data. They are never shown back in plain form; they appear masked everywhere, including logs and recorded values.
- The pool can only be managed through the server today. Members and admins can list, add, edit and delete entries; viewers can't change them.

## Acceptance criteria

1. **Given** an application, **when** a test data entry is added, **then** its label, normalised name, value and sensitive flag are saved for that application and kept across runs.
2. **Given** Discovery needs a value, **then** the pool is checked before any other source.
3. **Given** a pool entry, **then** its normalised name uses the same rule as blocked items, so matching fields line up exactly.
4. **Given** a value comes from the pool, **then** it is recorded as coming from the pool.
5. **Given** a sensitive entry, **then** its value is held in the encrypted secrets store and masked wherever it would otherwise appear.

## Gaps / not built

- There is no screen for the test data pool. Users can't enter values in the product, so in practice Discovery runs with an empty pool.
- Supplying a value in answer to a blocked item, so that it fills every waiting path, is not wired up (Stories 2.15 and 2.16).
- This pool is separate from the per-scenario test data users edit on the Scenarios and Test cases tabs (Epic 4).
