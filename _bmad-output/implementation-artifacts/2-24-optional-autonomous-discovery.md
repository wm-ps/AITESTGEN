---
last_updated: 2026-10-27
---

# Story 2.24: Optional Autonomous Discovery (Skip Discovery per Application)

Status: done

## Story

As a member or admin,
I want to add an application without running autonomous Discovery,
so that I can build its tests myself, by describing them in plain English or recording them, when crawling the app isn't wanted or practical.

## What it does today

- **The choice.** Add application has an **Autonomous discovery** checkbox, ticked by default, with the hint "Crawl the application to map journeys and scenarios automatically. Uncheck to only add the application and create test cases yourself." When ticked, the application is discovered by Explorer (Epic 8), or by the classic engine if operations have switched back to it.
- **When it is unticked:**
  - The submit button reads **Add application** instead of Start discovery.
  - The connection test is still required.
  - Credentials, if given, are stored encrypted but are not checked in advance (Story 2.23 only applies when Discovery is on).
  - No Discovery run (classic or Explorer) is ever started for the application.
- **Navigation for these applications:**
  - The **Journeys**, **Explorer** and **Scenarios** tabs are hidden.
  - Opening the application lands on **Test cases**.
  - Tests are added there with **Author a test case** (plain English, Story 4.4) or on the **Record and play** tab (Epic 5).
  - Running, scheduling and downloading work the same as for any other application.
- **Guard rails.** The server refuses discovery-type actions for these applications (pause/resume Discovery, generate scenarios), even if called directly.
- **Fixed at creation.** The choice can't be changed afterwards. Discovery can't be switched on later for an application added without it.

## Acceptance criteria

1. **Given** Add application, **then** an Autonomous discovery checkbox is shown, ticked by default, and the submit button label follows it ("Start discovery" / "Add application").
2. **Given** the box is unticked, **when** the form is submitted, **then** the application is created with no Discovery run and no credential check.
3. **Given** an application without Discovery, **then** the Journeys, Explorer and Scenarios tabs are hidden and opening it lands on Test cases.
4. **Given** an application without Discovery, **when** anyone tries to pause or resume Discovery or generate scenarios for it, **then** the server refuses.
5. **Given** an application without Discovery, **then** authored and recorded tests can be added, run, scheduled and downloaded like any others.

## Gaps / not built

- There is no way to turn Discovery on later for an application that was added without it.
- The server does not stop Explorer from being started for these applications if it is called directly (there is no screen for it); only classic Discovery actions are refused.
- The checkbox hint still says "Crawl", which describes the classic engine rather than Explorer.
