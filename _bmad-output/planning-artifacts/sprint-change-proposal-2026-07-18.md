---
title: "Change record — Application model and smarter crawling (2026-07-18)"
status: approved
created: 2026-07-18
approved: 2026-07-18
last updated: 2026-10-27
---

# Change record: Application model and smarter crawling (2026-07-18)

## What was proposed and why

The first Discovery build saved what it saw as loose, unstructured notes for each page, and the AI read those notes directly to find journeys. The proposal added a middle step: turn what Discovery observes into a structured model of the application, made of pages, forms, buttons and actions, API calls, expected outcomes and page-to-page links, each with stable ways to locate it on screen. The AI would then find journeys from that model, and test writing would draw on it too.

The proposal also made crawling smarter:

- Treat the same page reached by different routes as one page.
- Click one representative of a repeated button (for example, one "Edit" in a grid) rather than every copy.

Discovery work already built was revised before acceptance. Tests would still be written by AI, with the richer model given to it as context.

## What was decided

- Approved as drafted.
- In a same-day follow-up, the loose "notes" layer was dropped entirely. Discovery now records directly into the structured model, which is kept per application so a later Discovery run recognises pages it has already seen.
- Application areas are grouped using the existing "capability" idea rather than a new "module" concept.
- The pipeline order became: Discovery, then build the application model, then infer journeys.

## Where it stands today (2026-10-27)

**Shipped, and still how the product works.**

- Discovery builds a structured application model per application, merges duplicates across runs, and works out stable locators and expected outcomes.
- Journeys are inferred from that model, and test writing uses its locators.
- Representative-action sampling is in place.
- Treating the same page as one page was later deepened by the August Discovery engine rework (see the 2026-07-29 record).
