---
last_updated: 2026-10-27
---

# Story 2.6: AI Journey/Capability Inference from the Application Model

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to turn the discovered application into named business journeys, each an ordered set of steps,
so that I review meaningful flows ("Place an order") instead of a raw list of pages.

## What it does today

- Once the application model is built (Story 2.5), Vantage groups pages that link to each other into related batches and asks the AI to name the business journeys in each batch. Journeys belong to broader business capabilities.
- Each journey gets:
  - a business-language name and a short description
  - an ordered list of steps, each with a stage label (for example "Login", "Checkout")
- A page can belong to more than one journey (for example a login page shared by two flows).
- Results are checked before they are saved:
  - A name that looks like a web address or route is rejected, never saved.
  - Steps that point at pages the AI was never shown are dropped. If no real steps remain, the whole journey is dropped.
- Each journey gets a stable identity based on the pages it covers, not its AI-written name. If the same journey is found again, it isn't saved twice. Reordering the same pages doesn't create a new journey.
- The admin's "Maximum journeys" setting caps how many journeys one run can create. Anything past the cap is dropped and logged.
- When grouping finishes, the Journeys tab shows each journey as a card (Epic 3, Story 3.1). Nothing else starts automatically: scenario generation only begins when the user clicks "Review scenarios".

## Acceptance criteria

1. **Given** a completed run with its model built, **when** journeys are worked out, **then** candidate journeys are saved with business-language names and descriptions, never raw page addresses.
2. **Given** a candidate journey, **then** its pages are saved as ordered steps with stage labels, and a page may appear in several journeys.
3. **Given** the AI returns a name that looks like a web address, or steps for pages it was never shown, **then** the name is rejected, or those steps are dropped (the whole journey if none remain), and this is logged.
4. **Given** the same set of pages is found again, **then** no duplicate journey is created, whatever the name or step order.
5. **Given** the Maximum journeys setting, **then** no single run creates more journeys than that.
6. **Given** journeys have been saved, **then** no scenario or test generation starts until the user clicks "Review scenarios".
