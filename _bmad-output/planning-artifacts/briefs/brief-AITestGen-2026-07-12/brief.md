---
title: "Product Brief: Application Intelligence Platform"
status: approved
created: 2026-07-12
updated: 2026-07-13
---

# Product Brief: Application Intelligence Platform

## Executive Summary

The Application Intelligence Platform is an AI-powered enterprise product that discovers, understands, and documents the business journeys inside a running web application — and generates Playwright-based automated tests as one output of that understanding, not the point of it. Where testing tools execute journeys someone has already told them about, this platform answers the question that comes before: what does this application actually do, right now, as built? It turns runtime signals — pages, actions, APIs, workflows, state transitions — into a business-language map of capabilities and journeys that an organization can trust, review, and act on.

The problem it solves is a knowledge problem more than a testing problem. In complex, long-lived enterprise applications, shared logic and cross-team dependencies accumulate faster than documentation keeps up; a change to one workflow can quietly break another that nobody knew was connected. The result isn't flaky tests; it's production incidents — claims stuck in a queue, a workflow silently broken, an engineering leader who can't say with confidence what a release will affect. Existing test-automation tools, even the newer autonomous ones, don't close this gap because they still depend on someone already knowing a journey exists before they can test it.

V1 targets exactly this gap and nothing more: given only a URL and credentials, it discovers an application's journeys, puts them in front of a human for review and approval, and turns approved journeys into running regression coverage wired into the customer's own CI/CD pipeline — within hours, not weeks. What it offers is a different shape of product — business understanding as the deliverable, tests as a byproduct — not a unique discovery algorithm (see **What Makes This Different**). Built as an internal enterprise initiative aimed at an external market, the platform's long-term ambition is to become the system of record for application intelligence — a destination earned through V1 proving itself in real pilots, not a claim made in advance of it.

## The Problem

At a large insurance company, a small change to a policy approval component quietly breaks the claims approval workflow — the two share underlying logic that isn't visible from either team's vantage point. QA tests the intended feature. The release passes. Days later, hundreds of claims are stuck in production, and the retro lands on a question asked at nearly every enterprise running complex, long-lived applications: **nobody knew this change touched that journey, because nobody had a map of which business journeys exist or how they connect.**

This is not primarily a testing-coverage problem — it's a knowledge problem. Enterprise applications accumulate years of shared logic and cross-team dependencies. The engineers who built a given journey move on; documentation goes stale within a release or two; the only living record of what an application actually does is the application itself, and nobody has time to read it end-to-end before every release.

Existing testing tools don't close this gap — they execute journeys someone has already told them about. Test-automation platforms are built to run and maintain tests once a journey is defined, but they depend on a human already knowing that journey exists. None of them answer the prior question: *what are all the business journeys this application actually supports, right now, as built?* That gap is what leaves teams exposed to exactly the kind of blind-side break described above — and it's why the cost shows up not as "flaky tests" but as production incidents, stuck workflows, and engineering leaders who cannot say with confidence what would break if a given release shipped.

## The Solution

An Engineering Leader or QA Director points the platform at a running application: a URL and a set of credentials. Nothing else to integrate, no repository access, no agents to install — that's the entire setup for V1. The target is a first map within hours, not days or weeks.

From there, the platform explores the application the way a very thorough tester would — navigating pages, exercising actions, calling APIs, following state transitions — and turns what it observes into a structured map of business journeys and capabilities: not "43 pages crawled," but "Claims Approval," "Policy Issuance," "Agent Onboarding," each with the screens, actions, and API calls that make it up.

That map is never presented as finished truth. A human — the QA Director, an architect, whoever owns the domain — reviews it: confirms journeys, renames what the AI labeled awkwardly, merges duplicates, marks what matters most to the business. This review step is not a nice-to-have bolted on for trust; it is the mechanism by which an AI-inferred map becomes an organization's accepted source of truth. Once confirmed, the platform generates integration test scenarios for each journey and compiles them into executable Playwright tests — so the day-one output isn't just a diagram; it's a running regression suite covering journeys nobody had to remember to write tests for.

Above the map and the tests sits a set of views built for how each audience actually works: a **Journey Explorer** for anyone who needs to see how a specific workflow behaves end to end, a **Capability Map** for the business-language view of what the application does, **coverage analytics** showing which journeys are and aren't backed by automated tests, a **risk/confidence scorecard** ranking journeys by runtime signals — complexity, usage, error rates, coverage gaps — and an **executive dashboard** that rolls all of it into the view an Engineering Leader brings to a release-readiness conversation.

## What Makes This Different

**V1 does not win on a unique technical edge.** Autonomous, URL-only discovery that generates tests without source code access is already claimed by several players in this market — Virtuoso QA, QA.tech, and Autonoma AI among them. Any V1 pitch that leans on "we can discover your app from just a URL" as the differentiator is making a claim the market has already heard, and enterprise buyers evaluating this category will have heard it too.

What V1 actually offers instead is a different *shape* of product. Competitors that discover autonomously still frame themselves as test-automation tools — the discovery serves the tests. This platform inverts that: the business capability map and journey understanding are the product, and generated Playwright tests are one output of many. No competitor identified in market research combines business-capability language, journey-level understanding, coverage analytics, and risk scoring into a single intelligence layer the way this platform intends to. That framing, plus a human-in-the-loop review step that treats AI-discovered journeys as a draft rather than ground truth, is what V1 has to sell on — not a proprietary discovery algorithm.

The real technical moat arrives later. V2's source-code correlation gives the platform something autonomous-discovery competitors don't have: the ability to trace a journey back to the code and structure that implements it. V3's predictive release-impact analysis — telling a team which journeys and tests a specific code change puts at risk — is, as far as this brief's research found, entirely unclaimed territory in the market. That is the capability the team wants in front of customers as the platform matures, and it is the strongest, most defensible part of the vision.

The implication for V1 is worth stating plainly rather than glossing over: V1 has to earn early customers on execution quality, the strength of the business-journey framing, and buyer conviction in the roadmap — not on a moat that doesn't yet exist. Pilots and early design partners are likely to be sold on where this is going (the V3 promise) as much as what V1 delivers today, which makes an honest, credible roadmap story part of the V1 sales motion itself.

## Who This Serves

**Engineering Leaders** are the economic buyer. They own release risk without owning full visibility into what their applications actually do — especially in organizations where systems have accreted shared logic and cross-team dependencies over years, and where a change in one place can quietly break something in another. What they need is not more tests; it's the ability to walk into a release conversation and say, with evidence, what could break and what's covered. Success for them looks like fewer blind-side production incidents, less time spent firefighting after release, and a faster answer to "what does this application actually do" when a new engineer, auditor, or executive asks.

**QA Directors** are the primary daily user and champion. Today they carry the burden of discovering journeys manually, through tribal knowledge and exploratory testing, then writing and maintaining tests for what they find — always one step behind an application that keeps changing underneath them. What they need is a trustworthy, living map of the application's journeys and a running test suite they didn't have to author from scratch, with the authority to review, correct, and approve what the platform discovers rather than take it on faith. Success for them looks like spending less time on manual discovery and test-writing, and more credible data to bring to a release-readiness decision.

Secondary audiences — **CTOs** (portfolio-level visibility and reporting), **Product Owners** (a factual inventory of what the application does versus what was specified), **Architects** (structural and dependency understanding, more relevant once V2 adds source-code correlation), and **Test Teams** (the people who live with the generated suite day to day) — are real future users of the platform, but V1 is built and sold around the Engineering Leader and QA Director relationship first.

## Success Criteria

Business success for V1 is not a customer-count or revenue target — it's proving the core thesis (runtime discovery → journey mapping → generated tests) holds up well enough in real pilots to justify building V2. (What threshold counts as "proven enough" is not yet defined — see **Open Questions**.)

For the Engineering Leader and QA Director using it, two directional signals matter most: **coverage** (how many discovered business journeys end up backed by automated tests) and **time saved** (versus manual journey discovery and test authoring). No numeric target is set for either, deliberately — a percentage invented now would be a fabricated claim, not a real success criterion. The honest position: if the product performs as envisioned, meaningful time and cost savings for the client are the expected outcome, and real pilot data should set concrete thresholds once it exists — not before.

In the meantime, the qualitative signals worth watching are: an Engineering Leader or QA Director who, having tried V1, keeps using it into a second and third release cycle without being asked to; discovered journeys that need light correction rather than heavy rework during human review (a proxy for discovery accuracy); and generated tests a QA team trusts enough to fold into their real regression process rather than treat as a novelty.

## Scope

**In V1:**
- Runtime discovery of a running web application from a URL and credentials alone — no source code or repository access *for discovery purposes*.
- Automatic mapping of pages, actions, APIs, workflows, state transitions, and business journeys into a Capability Map and Journey Explorer.
- Human-in-the-loop review, correction, and approval of discovered journeys and capabilities before they're treated as trustworthy.
- Generation of integration test scenarios and executable Playwright tests from approved journeys.
- Packaging and exporting generated tests to the customer's repository, with integration into their existing CI/CD system (GitHub Actions, GitLab CI, Jenkins, Azure DevOps) so tests run automatically as part of standard regression. This is repository *write* access for test delivery — a different thing from the *read* access explicitly excluded below.
- Coverage analytics and a risk/confidence scorecard based on runtime signals only — journey complexity, usage, error rates, and test-coverage gaps. Not code-change risk.
- An executive dashboard rolling up capability, coverage, and risk views — across multiple applications from day one, not limited to a single application.
- Two deployment models: hosted SaaS and on-prem/VPN-based deployment for clients who need their application to stay inside their own network.

**Explicitly out of V1:**
- Reading or analyzing source code for discovery purposes, and anything that depends on it — route/component/permission/feature-flag structure, dependency mapping, code-to-journey traceability. That's V2.
- Change intelligence: predicting which journeys or tests a specific code change affects, or recommending a targeted test subset for a release. That's V3.
- Any claim of technical discovery superiority over competitors, per **What Makes This Different**.
- Non-web applications — mobile and native apps are not addressed by V1's discovery approach as currently defined.
- Test frameworks other than Playwright.
- Numeric coverage or time-saved targets — deliberately undefined until real pilot data exists, per **Success Criteria**.

## Open Questions

- **Time-to-first-map validation.** Hours, not days or weeks, is the internal target (see **The Solution**) — not yet validated against real-world application complexity. Confirm before this appears in any external-facing claim.
- **V2 greenlight threshold.** What counts as V1 having "proven the thesis enough" to justify building V2 — a number of design partners, retention through a full release cycle, something else? Not yet defined (see **Success Criteria**); worth pinning down before V1 pilots begin.

## Vision

The platform grows along the same arc it was designed with: **coverage intelligence → application intelligence → change intelligence.** V1 proves that an application's business journeys can be discovered and turned into working regression coverage without anyone having to remember they exist. V2 adds source-code correlation, so every journey traces back to the routes, components, and dependencies that implement it — turning the map from a picture of behavior into a picture of structure and behavior together. V3 closes the loop: given a code change, the platform tells a team which business journeys are at risk and which tests to run before shipping — the release-readiness answer no one else in the market currently gives (see **What Makes This Different**).

If that arc plays out, the platform becomes what an enterprise reaches for before it reaches for a wiki, a runbook, or a Slack thread to answer "what does this application do, and what happens if we change it." Not a testing tool that happens to know about the business, but the system of record for application intelligence — the place engineering leaders, QA directors, architects, and product owners go to understand what's built, what's changed, and what's at risk before every release.

That is the destination, not a V1 promise. Getting there depends on V1 actually holding up in real pilots and V2's technical differentiation proving out — this vision is worth building toward, not worth overselling before either is true.
