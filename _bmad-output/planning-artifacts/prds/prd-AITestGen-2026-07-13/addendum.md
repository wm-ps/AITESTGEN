# Addendum: Vantage (AITestGen) PRD

*Last updated: 2026-10-27*

This addendum holds the broader product story that sits outside the PRD's description of what is built today. It is useful for sales enablement, positioning and future planning.

## Competitive Positioning

Autonomous, URL-only discovery that writes tests without source access is claimed by several vendors, among them **Virtuoso QA**, **QA.tech** and **Autonoma AI**. Playwright itself now ships free agents that explore an app, plan tests, write them and heal them. "We can explore your app from a URL" is therefore not a differentiator on its own.

Vantage's case rests on the complete loop, built so a QA team can trust it:
- **Three ways to create tests, one library.** Autonomous Discovery, plain-English authoring and record-and-play all produce tests that share the same locators, self-healing, results and reports.
- **Self-healing that cannot cheat.** Repairs may change how a test finds things on the page, never what it asserts. Failed assertions are never healed.
- **Results people can act on.**
  - Plain-language failure summaries, with AI-written ones clearly labelled.
  - Flaky flags based on each test's recent history.
  - A run-level banner when most failures share one cause.
  - A branded report and a run-completed email.
- **Low friction, no lock-in.** A URL and a test login get a team started, and the login is proven before Discovery begins. The whole project downloads as a runnable Playwright project.
- **Team-ready.** Organization workspaces, three roles (admin, member, viewer), schedules, an org-wide Overview and an admin Activity history.

## Vision Arc

The direction is **coverage intelligence → application intelligence → change intelligence.**

- **Today:** Vantage turns an application's journeys into running, self-maintaining regression coverage, whether the tests come from Discovery, authoring or recording.
- **Next:** connect each journey to the code that implements it, and add a business capability map with coverage and risk views across applications.
- **Later:** given a code change, tell a team which journeys are at risk and which tests to run before shipping.

The long-term goal is to be the place engineering leaders and QA teams go to understand what is built and what a release puts at risk. That goal has not been reached; it depends on the current product proving itself in real use.

## Confidence and Risk Scoring: Why It Isn't Built, and How to Revisit

Neither a per-journey confidence score nor a risk scorecard exists today. The original scorecard idea leaned on usage and error-rate data, which needs live production monitoring that Vantage does not collect.

Two cheaper signals do exist and could be surfaced without any monitoring feed:
- the application health tier (Healthy, Needs attention, Critical) together with the "% of journeys covered by scenarios" figure, and
- each test's pass and flaky history.

A lightweight per-journey risk view could be built from these and from Discovery's own coverage report, which the server produces but no screen shows yet. A full risk scorecard still needs usage data and is a later-phase item.

## Success Criteria: Reasoning

Numeric coverage or time-saved targets are deliberately not set. A percentage invented before there is real usage data would be a made-up claim, not a success criterion. The intended order is usage data first, thresholds second. This is why the PRD's success metrics are directional.
