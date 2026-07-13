---
title: Architecture Spine Rubric Review — Application Intelligence Platform
reviewed_document: ../ARCHITECTURE-SPINE.md
reviewed_against: ../../../prds/prd-AITestGen-2026-07-13/prd.md
date: 2026-07-13
verdict: Conditional pass — strong port/boundary discipline, but the operational/environmental envelope and the tenant/user data model are silent gaps that will let independently-built units diverge in ways that matter for V1.
---

# Architecture Spine Review — Rubric Findings

## Summary Verdict

The spine is a well-formed *domain/pipeline* architecture — its eight ADs correctly identify and enforceably close the discovery→review→generation→delivery divergence points, and every PRD feature area (§4.1–4.8) has an explicit home or deferral. However, it is **silent** (not deferred — silent) on two structural dimensions this altitude owns: (a) the operational/environmental envelope (how the platform itself is built, deployed, and observed, even for a single dev/demo/pilot environment), and (b) a tenant/user/organization data model, despite the PRD requiring multi-application, multi-customer dashboards and a platform-user auth boundary. Both are the kind of gap where two independently-built slices would diverge in ways that surface as production incidents or rework, not stylistic differences.

---

## 1. Real divergence points for the level below — fixed vs. missed

**Covered well:** workflow/activity I/O split (AD-2), AI vendor abstraction (AD-3), delivery provider abstraction (AD-4), credential handling (AD-5), frontend/backend contract (AD-6), single-writer trust model (AD-7), evidence traceability (AD-8), and the workflow-boundedness/review-in-DB split (AD-1) — this last one in particular is the single highest-value call in the document; it heads off a genuinely nasty design mistake (modeling human review latency inside Temporal workflow history).

**Missed / not fixed (see §8 below for detail):**
- No entity or convention for **raw discovery signal storage** (screenshots, DOM snapshots, captured API traffic). The sequence diagram shows `DW->>DB: Persist raw discovery signal`, but the Core-Entity ERD has no such entity and no pointer from `EVIDENCE` to it. Two teams could easily diverge here — one storing large binary/blob artifacts directly in Postgres rows, another routing them to object storage — with materially different scaling and cost characteristics, and this directly touches AD-8 (evidence traceability), which depends on there being a well-defined place evidence points *to*.
- No **tenant/user/organization** entity anywhere in the Core-Entity ERD, despite Consistency Conventions referencing "Platform user auth" as a first-class concern and the PRD (FR-25) requiring a multi-application executive dashboard intended to work "even where a given customer initially onboards only one Application" — language that only makes sense if the platform is built to host multiple customer organizations, each scoped to their own Applications. Without a decided data-isolation primitive (e.g., an `Organization`/`Tenant` entity, a `tenant_id` convention applied uniformly), one team could build every query app-instance-scoped (implicitly single-tenant) while another adds tenant scoping only where they remember to — a classic silent-divergence bug class (cross-tenant data leakage).

## 2. AD Rule enforceability

All eight ADs pass the enforceability bar reasonably well — most are checkable by import-linting or a lightweight static rule ("no vendor SDK import outside `packages/ai_provider`", "no network/DB call inside `packages/workflows`", "no hand-written duplicate of a generated API type"), and the DB-level rules (AD-7, AD-8) are enforceable via schema constraints (NOT NULL `discovery_run_id`, a state-machine-limited status column). No AD is vague window-dressing.

**One partial weakness:** AD-5's Rule says the secrets store is "Vault **or** cloud KMS-backed envelope encryption" — that's fine as a *port* definition (the point of a port is swappable backends), but it leaves V1's actual first implementation undecided. Unlike AD-3/AD-4, where the Structural Seed and Component diagram explicitly show a hosted vs. on-prem/multi-provider split that *justifies* deferring the concrete choice, there's no such multi-implementation need for V1's secrets backend — V1 needs exactly one working implementation to ship, and the spine doesn't say which. This is a minor, low-risk instance of the same "silent operational choice" pattern flagged in §8.

## 3. Deferred section — does it defer anything that actually matters for V1?

No. All six Deferred items are legitimately post-V1 or PRD-level non-goals, and — notably better than boilerplate — three of the six (SSO/MFA session-state mechanism, direct-commit conflict handling, on-prem topology) are flagged with an explicit trigger condition for when they must be resolved, not just parked. This section is a genuine strength of the document.

The issue is not that the Deferred section defers something it shouldn't — it's that the gaps identified in §1 and §8 (raw-signal storage, tenant model, operational envelope) are **absent from the Deferred section entirely**, i.e., not flagged as open at all, silent rather than deferred-with-a-trigger.

## 4. Named tech currency

Most stack entries deliberately avoid false precision ("current stable," "current GA," "current 6.x/7.x," "current 5.x") — good practice for a spine that will outlive any single package version. Two entries buck that pattern with specific patch-level pins as of the document's 2026-07-13 date:
- **Python 3.14.6** — Python 3.14.0 shipped ~Oct 2025; a `.6` patch by July 2026 implies roughly one patch release every 6 weeks, which is faster than CPython's typical early-release cadence (usually monthly-ish for the first year, but not guaranteed). Plausible, not obviously wrong, but worth a currency check before this is treated as a real constraint.
- **PostgreSQL 18.4** — PG major releases land ~September/October, with quarterly minor releases (roughly Nov/Feb/May/Aug pattern). `18.4` by mid-July 2026 is slightly ahead of that typical cadence (would suggest a minor release lands in this timeframe that may not have shipped yet).

Neither is a hard red flag, but both are the kind of overly-precise version pin that goes stale or turns out aspirational — recommend verifying against actual release notes before implementation starts, or loosening to "18.x current" / "3.14.x current" like the rest of the table.

## 5. Brownfield ratification

N/A — greenfield, correctly out of scope per instructions.

## 6. PRD capability coverage

Full coverage. Every Feature area §4.1–4.8 appears in the Capability → Architecture Map with a "Lives in" and "Governed by" entry, including §4.8 Deployment, which is honestly mapped to "Deployment topology itself... Deferred" rather than forced into a fake architectural home. No silent capability gaps at this level.

## 7. Parent spine inheritance

N/A — no parent spine, correctly out of scope per instructions.

## 8. Structural dimensions this altitude owns — decided / deferred / open vs. silently missing

This is where the spine's biggest weakness lives. Walking the standard set of dimensions an initiative-altitude spine should touch:

| Dimension | Status in spine |
| --- | --- |
| Service/module boundaries | Decided (Layer → namespace map, Structural Seed) |
| Orchestration/I-O split | Decided (AD-2) |
| Vendor abstraction (AI, delivery, secrets) | Decided (AD-3, AD-4, AD-5) |
| API contract strategy | Decided (AD-6) |
| Data ownership / write authority | Decided (AD-7) |
| Traceability/evidence | Decided (AD-8) |
| Naming, id format, date format, error envelope | Decided (Consistency Conventions) |
| Logging format & correlation | Decided ("Structured JSON logs, correlated by `workflow_id`") |
| **Deployment/hosting for V1 itself** (containerization, where Temporal server + Postgres + Secrets store actually run even for a single dev/demo/pilot instance) | **Silent.** Not decided, not in Deferred. The only deployment-shaped statement in the whole document is the *product-facing* "SaaS vs on-prem" toggle, which is explicitly deferred — but that is a different question from "how do we stand this system up at all right now." Nothing says whether Temporal is self-hosted or Temporal Cloud, whether services run as containers/on what platform, or what a "dev/demo" environment even consists of. |
| **CI/CD for the platform's own codebase** (as distinct from AD-4's customer-facing delivery adapters) | **Silent.** No mention of how `apps/api`, `apps/web`, or the workers are built, tested, or deployed. |
| **Migration application strategy** | Partially decided — Alembic is named as the tool (Structural Seed), but *how/when* migrations run (auto-applied on deploy vs. manual, single-writer coordination across worker replicas) is not addressed. |
| **Observability beyond logs** (metrics, alerting, error tracking/tracing, log aggregation destination) | **Silent.** Structured logs are specified but nothing says where they go, whether Temporal's own Web UI/metrics are relied on for workflow visibility, or how a stuck/failed `DiscoveryWorkflow` gets noticed operationally. |
| **Tenant/user/organization data model** | **Silent** — see §1. No entity, no convention, not in Deferred, despite platform-user auth and multi-application dashboards being explicit PRD/spine concerns. |

Per the rubric's explicit instruction: the spine's Deferred section defers "SaaS vs on-prem deployment topology," but that defers only the *product* deployment-mode decision (and correctly so, per the user's request noted in the doc). It does not defer, and does not decide, the more basic question of how this thing is actually run and observed even in one environment today — that is a silent gap, not a deferred one, and it's the kind of gap that lets a dev environment get built ad hoc by whoever touches it first, with no shared assumption for a second engineer to build against.

---

## Findings Ranked by Severity

1. **[High]** Operational/environmental envelope is silent, not deferred. No decision on how the platform is deployed/run/observed even for a single dev or pilot environment — no containerization approach, no stated Temporal hosting model (self-hosted vs. Temporal Cloud — notably relevant since Temporal Cloud would itself need rework for the already-anticipated on-prem case, the same class of risk AD-3 was written to avoid for the AI provider), no CI/CD for the platform's own code, no metrics/alerting/tracing baseline beyond log format. This is exactly the kind of gap where two engineers stand up divergent environments with no shared floor.

2. **[High]** No tenant/user/organization entity or data-isolation convention anywhere in the domain model or ERD, despite "Platform user auth" being called out as a distinct namespace in Consistency Conventions and FR-25 implying multiple customer organizations share the platform. Absent an explicit decision, independently-built slices (API auth, review endpoints, dashboard queries) can easily diverge on whether/how data is scoped per customer — a correctness and security-relevant gap, not a stylistic one.

3. **[Medium]** Raw discovery signal (screenshots, DOM captures, API traces) has no modeled home. The sequence diagram references persisting it; the ERD doesn't show it, and AD-8's evidence-pointer guarantee is only as good as there being a well-defined artifact store for evidence to point at. Storage-location choice (Postgres blob vs. object storage) is a real scale/cost divergence point left to whoever implements `DiscoveryActivity` first.

4. **[Low-Medium]** AD-5 defines the secrets port correctly but leaves V1's actual first backend undecided ("Vault or cloud KMS-backed") with no resolution target — unlike the AI/delivery ports, there's no multi-implementation need for V1 that justifies leaving this open; it should be a Decided line item, not an implicit either/or.

5. **[Low]** Two stack entries pin a specific patch version (Python 3.14.6, PostgreSQL 18.4) against a stated 2026-07-13 date; both are plausible but slightly ahead of/tight against typical release cadences for their respective projects and are worth a currency check, especially since every other stack entry deliberately uses "current stable" to avoid this exact staleness risk.
