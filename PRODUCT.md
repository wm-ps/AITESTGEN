# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

QA and engineering teams at enterprises who need automated test coverage for
their web applications without hand-writing test scripts. They onboard an
application (auth method, base URL) and use Vantage to find out what the app
actually does and get running Playwright test suites out of it.

## Product Purpose

Vantage (formerly internally called AITestGen) is an application intelligence
platform: it autonomously discovers the real user journeys inside an
onboarded web app, generates test scenarios and Playwright test assets from
those journeys, and executes them — replacing manual test-case authoring for
web QA.

## Positioning

The mechanism a competitor can't just copy: an AI crawler that explores the
target application itself to discover real journeys (Discover Journeys), then
generates scenarios and Playwright suites from what it actually found — not
scripted/predefined crawl paths, and not record/replay from a human driving
session.

## Operating Context

- Invite-only, org-scoped accounts (no self-service signup) — an admin invites
  teammates; roles include admin.
- Core workflow: connect an application → Discover Journeys (autonomous
  crawl) → Review Scenarios → Generate Test Suite → view/download Playwright
  results.
- Backed by Temporal workflows (DiscoveryWorkflow, GenerationWorkflow,
  ApplicationTestExecutionWorkflow) run by separate workers; API is FastAPI,
  web is React 19 + Vite.
- Environments per application: staging / qa / production.

## Capabilities and Constraints

- Confirmed: journey discovery via real browser crawling (Playwright-based),
  AI-driven scenario inference, generated Playwright test assets, test
  execution and results reporting, invite/reset-password email flows.
- Terminology: "Journey" (a discovered user flow), "Scenario" (a test case
  derived from a journey), "Discovery Run", "Application" (the onboarded
  target).

## Brand Commitments

- Name: **Vantage** (renamed from the internal/repo name "AITestGen"; the
  repo, package names, and some internal docs still say AITestGen — cosmetic
  drift only, not a product-truth conflict).
- Existing accent color: teal `#0f766e` (`--accent` in
  `apps/web/src/tokens.css`) — carried forward, not yet renegotiated.
- No other locked-in visual/verbal commitments; logo and broader identity are
  open to (re)design.

## Evidence on Hand

- `README.md` (top-level) describes the platform and module layout.
- `apps/web/src/components/` (DiscoverJourneys, GenerateSuite, ReviewScenarios,
  TestSuiteResults) shows the actual product workflow and UI language.
- No customer testimonials, case studies, press, or benchmark data on hand —
  future work must not invent any.

## Product Principles

- Autonomy over configuration: the product's edge is discovering journeys
  itself, not requiring teams to define them.
- Enterprise-grade trust: invite-only access, org scoping, audit-friendly
  invite/reset flows — the brand should read as credible/serious, not
  playful.
- Traceability: every generated test should trace back to a real discovered
  journey, not a black box.

## Accessibility & Inclusion

No product-specific accessibility requirement has been established beyond
standard web practice.
