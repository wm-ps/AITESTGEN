---
last_updated: 2026-10-27
---

# Story 2.13: Data Resolver — Choosing What to Type, and Learning from Rejections

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to use values I supplied, then values it has seen work, before making anything up, and to stop reusing a value the application rejected,
so that the coverage it builds rests on trustworthy inputs and it doesn't keep repeating the same failing guess.

## What it does today

- When an action needs input, Vantage picks a value in this order:
  1. A value saved for this application in its test data pool (Story 2.20).
  2. A value that already worked earlier in this run.
  3. Safe made-up data chosen by field type (a test email, a phone number, a date, "1" for numbers and quantities, "Test value" for text) for any field whose name does not look business-specific (policy, account, claim, invoice, order number and similar). File upload fields get a harmless placeholder image or PDF, created once and reused.
  4. Otherwise, the action is put aside as blocked (Story 2.15). Vantage never invents business-specific values such as a policy number.
- **Learning from rejections.** After using a value, Vantage checks whether the application accepted it. A rejection is spotted when a validation error appears or the expected next screen doesn't come. A rejected value is not reused for that field later in the run; Vantage moves on to the next option.
- Every value used is recorded: the field, the value, where it came from, whether it was a placeholder file, and whether it worked. Values marked sensitive are masked.
- Actions judged clearly destructive (Story 2.12) never reach this step at all.
- When a field is put aside, it is filed under the same normalised field name the test data pool uses. That way, a matching pool value added later satisfies it automatically.

## Acceptance criteria

1. **Given** an action needs input, **then** Vantage tries, in order: the test data pool, a value that already worked this run, safe made-up data for fields that don't look business-specific (or a placeholder file), and otherwise puts the action aside. It never invents a business-specific value.
2. **Given** a value was used, **then** whether it worked is recorded, judged by validation errors or a missing expected next screen.
3. **Given** a value was rejected, **then** it is not reused for the same field later in the run.
4. **Given** any value is used, **then** a record is kept of the field, the value (masked if sensitive), its source and the outcome.
5. **Given** a clearly destructive action, **then** no value is ever looked up for it.
6. **Given** a field is put aside, **then** it is filed under the same normalised name the test data pool uses.

## Gaps / not built

- The step "use a value already shown on the current page" was deliberately left out. It was judged the least reliable step.
- Spotting rejections uses two simple signals: a field marked invalid, or the expected next screen not appearing. A rejection the application signals some other way is missed.
