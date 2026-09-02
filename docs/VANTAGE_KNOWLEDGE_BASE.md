# Vantage Knowledge Base — What / How / Why

A searchable FAQ-style reference for the Vantage platform (internal repo/code
name: **AITestGen** — see [Product naming history](#product-naming-history)).
Compiled from the current codebase, tests, git history, and in-code comments
as of 2026-09-02. Every claim below is grounded in actual source — file:line
references are given wherever practical so claims can be re-verified as the
code moves.

Deliberately **not** sourced from `_bmad-output/`/`_bmad/` — this repo's
`CLAUDE.md` flags those planning artifacts as stale, so nothing here cites
them, even where they might look authoritative. `docs/*.md` (a different,
actively-maintained directory) and `PRODUCT.md` were used, but cross-checked
against code; any drift found is called out explicitly.

**How to use this doc:** it's organized by product area, each with its own
`##`/`###` headers you can jump to or search. Every non-trivial claim carries
a **Why** (quoted reasoning from the code/docs/commit history where it
exists) and, where relevant, **Alternatives considered**, **What changed
historically**, and **Limitations**.

---

## Table of contents

1. [Product overview](#product-overview)
2. [Tech stack & cross-cutting architecture](#tech-stack--cross-cutting-architecture)
3. [Login / authentication](#login--authentication)
4. [Discovery — autonomous crawling](#discovery--autonomous-crawling)
5. [Generation — Scenarios → Playwright tests](#generation--scenarios--playwright-tests)
6. [Execution — Run All Tests](#execution--run-all-tests)
7. [Self-healing](#self-healing)
8. [Web UI / product workflow](#web-ui--product-workflow)
9. [Infrastructure & deployment](#infrastructure--deployment)
10. [CI/CD](#cicd)
11. [Object storage](#object-storage)
12. [Product naming history](#product-naming-history)
13. [Architecture Decision (AD) rule registry](#architecture-decision-ad-rule-registry)
14. [Known limitations / ponytail debt ledger](#known-limitations--ponytail-debt-ledger)

---

## Product overview

**What is Vantage?** Per `PRODUCT.md`: an "application intelligence
platform" — it autonomously discovers the real user journeys inside an
onboarded web application, generates test scenarios and Playwright test
assets from those journeys, and executes them, replacing manual test-case
authoring for web QA.

**Core workflow:** connect an application → **Discover Journeys** (autonomous
crawl) → **Review Scenarios** → **Generate Test Suite** → view/download
Playwright results → **Run All Tests** against the live app.

**Positioning (why build this instead of buying an existing tool like Testim,
mabl, or Rainforest):** PRODUCT.md — "an AI crawler that explores the target
application itself to discover real journeys (Discover Journeys), then
generates scenarios and Playwright suites from what it actually found — not
scripted/predefined crawl paths, and not record/replay from a human driving
session." Existing record/replay tools need a human to demonstrate every
flow first; Vantage's differentiator is finding journeys with no human
demonstration step at all — this is the stated moat, not an incidental
implementation detail. Note this rationale lives in product positioning, not
in a documented build-vs-buy evaluation — no repo evidence of specific
competitor tools being evaluated and rejected.

**Operating model:** invite-only, org-scoped accounts (no self-service
signup); an admin invites teammates. Backed by Temporal workflows
(`DiscoveryWorkflow`, `GenerationWorkflow`/`SuiteGenerationWorkflow`,
`ApplicationTestExecutionWorkflow`) run by three separate worker processes;
API is FastAPI, web is React 19 + Vite.

### Which branch is this doc grounded in, and why does that matter?

`main`'s HEAD is `5169a5e` "Story 4.3: Download a Generated Test Suite" and
hasn't advanced past that point. Everything after Story 4.3 — Discovery
Engine v2, invites/settings, self-healing, branding (AITestGen → WaveQA →
Vantage), and the recent execution-stabilization commits — lives only on
`feature-crawl2.0` (~70 commits ahead of `main`, diverging exactly at
`5169a5e`), never merged. Despite its name, that branch is not a narrow
crawler-only change — it's the entire post-4.3 development line, crawl
rework included. This doc describes `feature-crawl2.0` (the current branch)
throughout, i.e. the real current state of the product, not `main`.

---

## Tech stack & cross-cutting architecture

### What's the full stack, and where does each piece run?

| Layer | Tech | Deploys as |
|---|---|---|
| Web | React 19.2.7, Vite 8.1.1, TypeScript 5.9.3, oxlint, Vitest | Static assets behind nginx — **not** a Node server |
| API | FastAPI, SQLModel, Alembic, Python 3.14 (uv workspace) | `uvicorn` container |
| Orchestration | Temporal (Python SDK) | Dev: `temporalio/admin-tools` dev server. Real workers poll task queues, no HTTP port |
| DB | PostgreSQL 18.4 (native `uuidv7()` server default) | Externally hosted in prod (e.g. RDS) — not deployed in-cluster |
| Secrets | HashiCorp Vault 1.18, **dev-mode**, KV v2 | In-cluster even in production namespace (see [why](#why-is-vault-in-cluster-dev-mode-even-in-production)) |
| Object storage | Real AWS S3 | Not in-cluster; no local MinIO either (removed — see [Object storage](#object-storage)) |
| Browser automation | Playwright (`@playwright/test`, TypeScript) | Both for discovery's crawl and for generated/executed tests |
| AI | LiteLLM **proxy** (HTTP, OpenAI-compatible), model alias `anthropic/claude-sonnet-5` | See [AI provider](#what-llm-actually-powers-vantage) |

Three separate Temporal worker processes: `discovery-worker` (Playwright
crawler + AI inference activities, `discovery-task-queue`),
`generation-worker` (scenario/Playwright-code generation,
`generation-task-queue`), `execution-worker` (runs generated tests,
`execution-task-queue`).

### Why "Ports & Adapters"?

External concerns (LLM vendor, secrets store, delivery/CI integrations) sit
behind fixed Python `Protocol` interfaces in dedicated `packages/*` — core
code never imports a vendor SDK directly. Quoted:
`docs/DEVELOPER_GUIDE.md:54-55` — *"external concerns (AI vendors, secret
stores) live behind fixed `Protocol` interfaces. The core never imports a
vendor SDK directly."*

Ports found: `AIProvider` (`packages/ai_provider`, AD-3), `SecretsClient`
(`packages/secrets_client`, AD-5), `DeliveryAdapter` and
`CIInstructionsGenerator` (`packages/delivery_adapters`,
`packages/ci_instructions`, AD-4 — **scaffolded seams, never built out**:
`git log --follow` on both packages shows exactly one commit each, the
original `80b827f` "Story 1.1 Scaffolding" — no later commit touches or
removes either. Correcting README.md's own "feature removed" framing: there
is no evidence a CI/CD-delivery feature was ever built against these ports
and then torn out: they were scaffolded speculatively per the ports-&-
adapters pattern and simply never implemented).

### What LLM actually powers Vantage?

**Not a direct vendor SDK.** `HostedAIProvider`
(`packages/ai_provider/src/ai_provider/hosted.py`) talks to a **LiteLLM proxy
server** over plain HTTP (`/chat/completions`, OpenAI-compatible shape) — not
the `litellm` Python SDK, and no `anthropic`/`openai` package is imported.
`AI_MODEL` env var defaults to `"anthropic/claude-sonnet-5"` (Claude Sonnet
5), routed through the proxy.

**Why:** `hosted.py:1-8` — *"no AI vendor is named in the PRD or Architecture
Spine; the proxy owns provider routing/credentials entirely, so this file
only ever speaks one OpenAI-compatible `/chat/completions` shape. `AI_MODEL`
is the proxy's model alias, not a code change — this is what lets a future
vendor/model swap touch only proxy config, never this file (AD-3)."*

Temperature defaults to `0.2` (near-deterministic — "these calls extract
structured data or follow prescriptive rules, not creative writing"),
overridable/omittable via `AI_TEMPERATURE` for models that reject non-default
temperature.

**Alternative not built:** a `CustomerEndpointAIProvider` (on-prem/BYO-LLM)
is named in the port's own docstring as a future adapter but was never
implemented — the epic that would have owned it (Epic 7) was removed from
scope.

**Cost exposure:** controlled entirely through hard caps, not
budget-awareness — bounded Activity retries (3 attempts, called out in
`discovery_workflow.py` as "the first bounded retry policy in the codebase,"
because unbounded retries against a paid LLM is a cost risk), a per-run
`max_journeys` cap (default 50), and admin-tunable
`max_scenarios_per_journey`/`max_test_cases_per_application` ceilings (see
[Discovery settings](#what-discovery-settings-are-admin-tunable)). There's no
cost tracking, per-org spend metering, or budget alerting anywhere in the
repo — only these request-count caps as an indirect ceiling.

### Why UUIDv7 internal PKs but UUIDv4 `external_id`s?

Every entity's Postgres primary key (`id`) is UUIDv7 — sortable/index-local
because it embeds a creation timestamp. A second field, `external_id`
(UUIDv4, opaque), is the *only* id ever returned in an API response.

**Why, quoted** (`packages/domain/src/domain/application.py:1-8`, the entity
that establishes the convention): *"`id` is the internal PK (UUIDv7, index
locality) and never leaves the backend; `external_id` (UUIDv4, opaque) is the
only id ever returned in an API response, since a UUIDv7's embedded timestamp
would leak creation time."*

Exception: `Organization` and `PlatformUser` don't expose *any* id externally
at all, not even `external_id` — there's no client-facing reason to look
either up by id.

### Why is the OpenAPI spec "the only contract" between web and api (AD-6)?

`apps/web/src/api-types.gen.ts` is generated from the live API's
`/openapi.json` (`npm run generate:api-types`) — no request/response shape is
ever hand-typed in `apps/web`. CI's `api-types-drift` job fails the build if
the checked-in generated file drifts from what the running API actually
produces (`git diff --exit-code` on the generated file).

**Why:** avoids the classic "frontend types silently rot the first time
someone hand-edits them in a hurry" failure mode — the type generator is the
single source of truth, checked mechanically, not by convention.

**A soft exception in daily practice:** the rule holds absolutely for
`api-types.gen.ts` itself (CI enforces it mechanically), but the hand-written
wrapper `apps/web/src/api.ts` routinely front-runs backend changes with
manually-typed extensions (each marked `// Not in api-types.gen.ts yet ...
added by hand`) until someone next runs the generator against a live API —
e.g. `UserRead['role']`, extra `HomeApplicationRead` fields. So "never
hand-typed" is true of the generated file, not of every type the frontend
uses.

### Why Temporal, and what does "zero I/O in workflows" (AD-2) mean?

Long-running, multi-step work (a discovery crawl, generating a whole suite,
running every test) is modeled as a **Temporal workflow** — durable,
resumable, replayable. All real I/O (DB writes, browser automation, LLM
calls, S3 puts) happens in **Activities**, dispatched by the workflow and
executed by a **worker** process; the workflow class itself never touches the
DB/network/browser directly.

**Why:** *"Temporal replays workflow code to recover from failure; any I/O
inside a workflow breaks determinism"* (`docs/DEVELOPER_GUIDE.md:145`).
Verified true for the workflow files actually read for this doc
(`execution_workflow.py`, `discovery_workflow.py`,
`suite_generation_workflow.py`) — each is orchestration-only `asyncio.gather`
/ `workflow.execute_activity` calls, no direct DB/HTTP/browser calls.

---

## Login / authentication

*(This section covers signing into Vantage itself — the platform's own
login. For how discovery/execution authenticate against the **target**
application under test, see [Discovery → auth-aware
crawling](#is-discoverys-crawl-auth-aware).)*

### What auth mechanism does Vantage use, and why?

A server-signed, **httpOnly session cookie** — not JWT, not OAuth. Signed via
`itsdangerous.URLSafeTimedSerializer` (`apps/api/src/api/auth.py:37`).
Sign-in serializes `str(user_id)` into the cookie; every authenticated
request verifies the signature and age (`max_age`) and 401s on a bad/expired
signature.

**Why, quoted** (`auth.py:1-6`): *"Sign-in issues a signed, httpOnly session
cookie (itsdangerous) — no OAuth/JWT-library complexity needed for a
same-origin SPA+API; a 'boring technology' choice, consistent with the
architecture's general bias. This exact mechanism is not fixed by the PRD or
Architecture Spine."*

### Is a session a fixed 7-day cookie, or does it expire on inactivity?

**Sliding idle window**, 1 hour (`COOKIE_MAX_AGE = 60 * 60`). The shared
`current_user` FastAPI dependency re-issues the cookie with a fresh timestamp
on every authenticated request, so only true inactivity (tab closed, genuine
idle) past 1 hour logs the user out.

**Why, quoted** (`auth.py:28-34`): *"1 hour of inactivity logs the user out
(security requirement — a session used to live 7 fixed days regardless of
activity)... Only true silence... past this many seconds expires it."* —
i.e. this was an explicit rewrite from an earlier fixed-duration design.

Passwords are hashed with **bcrypt** (`bcrypt.hashpw`/`bcrypt.checkpw`), never
plaintext.

### How does org-scoping work, and what stops one customer seeing another's data?

**One central mechanism**, never re-implemented per endpoint: `current_org_id`
(`auth.py:90-96`), a FastAPI dependency every org-scoped router depends on.
This is **Architecture Decision AD-12**.

**Why, quoted** (`docs/DEVELOPER_GUIDE.md:149`): *"Every `apps/api` query is
scoped to the signed-in user's Organization through **one** central
mechanism..., never re-implemented per endpoint. — The only thing standing
between one customer's data and another's."*

### Why invite-only, no self-service signup?

The only ways a `PlatformUser` row is created: the dev seed script, or
accepting an admin-issued `Invite`. There is no public registration endpoint.

**Why, quoted** (`apps/api/src/api/invites.py:1-8`): *"No open self-service
signup... this is the only other way a `PlatformUser` row gets created. The
raw token is the sole secret and is never persisted: only its sha256... is
stored... Revocation/audit is the point of a DB-backed invite (over a signed
stateless token) — a pending invite is a row an admin can see and delete."*

Matches `PRODUCT.md`'s Operating Context exactly: *"Invite-only, org-scoped
accounts (no self-service signup) — an admin invites teammates; roles
include admin."*

**Flow:** admin sends invite (email + role) → 72-hour-expiry token emailed
(or logged, in dev, if SMTP isn't configured — flagged with its own
`ponytail:` comment) → invitee visits `/accept-invite?token=...` → sets
name+password → account created under the **inviting admin's existing org**
(there's no "create a new org" flow — single-tenant-per-deployment in
practice, though the schema itself is multi-tenant per AD-12) → session
cookie issued immediately (auto sign-in on accept).

An invalid/expired/used/unknown token deliberately collapses into one
generic error — *"deliberately not distinguishing the reasons (don't let a
caller probe which tokens exist vs. are merely expired)."*

### How does password reset work?

Same token design as invites (1-hour expiry). `POST /auth/forgot-password`
**never reveals whether the email exists** — *"Always a no-op-looking call
from the outside"* — and the frontend shows the same "check your email"
copy regardless of whether the account exists.

### What roles exist?

Two: `admin` and `member` (default). Admin-only actions: sending/revoking
invites, and the Workspace's Credentials tab (rotating a connected
application's stored login). No finer-grained per-resource permissions exist
beyond org-scoping + this one flag.

### What does the sign-in screen actually look like, and is the wizard vertical or horizontal?

(Resolves an earlier open question — this had genuinely flip-flopped across
redesigns.) Current `SignIn.tsx`: a **horizontal two-panel split** — a wide
left panel (`flex: 0 1 62%`) carrying the marketing pitch and a 4-step
"Scan → Discover → Generate → Run" wizard, a narrower right panel
(`flex: 0 1 38%`) carrying the actual sign-in form. *Within* the left panel,
the 4 wizard steps are stacked **vertically** (a timeline with a connecting
line), auto-advancing every 2.6s and independently clickable. So: horizontal
top-level split, vertical step list inside it.

Copy is sales-pitch register throughout — no occurrence of "crawl",
"workflow", "API", or "script" (headline: *"Point it at your app. Get a
production-ready test suite back."*). Background motion is a single 16-second
`ease-in-out` gradient drift (`aitg-drift`), no ring/pulse/sweep — a scan-
sweep animation exists only inside the small "Scan" step's preview card, not
the page background. Both match this project's previously-recorded design
taste.

### Is there a dev-login shortcut, and does it run in production too?

**Yes, and yes** — worth flagging explicitly since it's a real, if narrow,
security-relevant shortcut. `SignIn.tsx`'s `DEV_LOGIN_ENABLED = true` is a
hardcoded constant with **no environment gate** — clicking the logo or the
"Sign in" heading autofills the seeded dev credentials
(`dev@example.com`/`devpassword123`) in *every* build, including prod. Its
own `ponytail:` comment names this directly as a known shortcut with an
upgrade path ("reintroduce a `VITE_ENABLE_DEV_LOGIN` build-time env check
instead of this constant"). It only autofills the form fields — actually
signing in still goes through the real `/auth/login` endpoint and still
requires those credentials to be valid on the target deployment, so it's not
an auth bypass, just a convenience shortcut that happens to ship everywhere.
Git history: `eeb00c6 login dev credentials on logo click` adds it;
`0ab2053 [Not recommended] Committing for time being for Demo purposes`
(same era) suggests it was known internally to be dubious and shipped for
demo convenience anyway.

### What's the overall security/compliance posture — is multi-tenant isolation actually safe?

Target-app credentials: never a plaintext DB column, always via
`SecretsClient`/Vault (AD-5) — though see Vault's dev-mode caveat under
[Infrastructure](#why-is-postgress3-hosted-externally-but-vault-runs-in-cluster-dev-mode-even-in-production).
Platform passwords: bcrypt-hashed. Sessions: signed httpOnly cookies, 1-hour
sliding idle expiry. Org-scoping is centralized through one dependency
(AD-12) rather than re-implemented per endpoint, which is the right shape for
avoiding a leak — but it's still **one shared Postgres schema with a
row-level `organization_id` filter**, not per-tenant databases/schemas; a
single endpoint that forgets `CurrentOrgIdDep` is a real cross-tenant leak
vector, not one backed by a second layer of defense. No SOC2/GDPR/compliance
material of any kind exists in the repo — not addressed, not this doc's
place to guess whether it's needed.

---

## Discovery — autonomous crawling

### What is Discovery, in one paragraph?

An autonomous Playwright-driven crawler (`apps/workers/discovery`) explores
an onboarded application the way "a thorough tester would," capturing pages,
forms, buttons/links, and API calls as typed rows — not screenshots-and-guess,
real structural evidence. A separate step then clusters that raw evidence
into candidate **Journeys** (real user flows) using deterministic
graph-clustering plus a bounded number of LLM calls. Orchestrated by
`DiscoveryWorkflow` (`packages/workflows/src/workflows/discovery_workflow.py`)
— which itself does zero I/O per AD-2 — running on the discovery worker.

### What crawl strategy does it use, and why not something else?

**Breadth-first link traversal**, plain and unranked at the top level,
refined by a rule-based action-tiering "Planner" underneath (see next
question). Module docstring
(`apps/workers/discovery/src/discovery_worker/crawler.py:4-9`): *"Neither the
PRD nor the Architecture Spine specifies an exact traversal algorithm (FR-6:
'navigates the Application the way a thorough tester would'). This is a
sound, non-binding default: breadth-first link traversal, generic placeholder
values keyed by input type for form-filling, and Playwright response
interception for API calls — not a spec to match exactly."*

Per page: navigate → wait for a 3-signal readiness gate → screenshot +
structural capture → scrape links and enqueue same-origin new ones → fill and
submit every form → click every distinct-labeled standalone button → explore
ARIA tabs → recurse same-origin iframes (depth 3) → walk open shadow DOM
roots.

### What's the stop condition — does the crawl ever "run out of budget" mid-app?

**By design, no arbitrary iteration cap.** Architecture Decision **AD-10**:
exhaustive traversal is the *only* stop condition.

**Why, quoted** (`crawler.py:11-14`): *"the crawl runs until no new page is
found to visit — exhaustive traversal is the *only* stop condition. There is
deliberately no iteration/safety cap here... an Application with unbounded
pagination could run indefinitely) — an accepted risk."*

That said, there **are** admin-configurable backstops (see [Discovery
settings](#what-discovery-settings-are-admin-tunable)) that stop a run
*cleanly* (keeping everything already captured) rather than mid-crash:
`max_pages` (default 500), `max_discovery_duration_minutes` (default 30,
nullable = unlimited), plus a hard numeric action ceiling
(`DEFAULT_ACTION_CEILING = 5000` in `planner.py`) flagged in its own
`ponytail:` comment as *"set deliberately high so it never bites a real
crawl... this default has not had explicit PM sign-off"* — a real, tracked
process gap, not just a technical shortcut.

### How does the crawler decide what to click, and avoid clicking the same thing forever?

A deterministic **Planner** (`planner.py`) sits between "found a candidate
action" and "actually click it," with no ML/LLM involved. Two mechanisms:

- **Tiering** (`classify_tier`): in-page tabs → Tier 1; navigation
  landmarks/route-changing links → Tier 2. Every Tier-1 candidate on a page
  is exhausted before any Tier-2 candidate is attempted.
- **Loop guards** (`LoopGuardState`): action-history dedup, A→B→A→B
  transition-cycle detection, and a **route-family sampling cap** (default
  3) — e.g. the same "Edit" label repeated across 500 product-detail pages is
  sampled 3 times, the rest are treated as parameterized duplicates, not
  independently explored.

After a click navigates away, a 5-rung **State Return ladder** gets the
crawler back to a known page (no-op → `go_back()` → re-`goto()` → bounded
2-step replay → *"give up honestly"* — mark the rest of that page's
candidates `unreached` rather than silently dropping them). Every rung except
no-op is confirmed via a real re-fingerprint check before being trusted — "a
plausible-looking landing... is not good enough."

**What was tried and changed** (real bugs fixed live, per code comments):
- A per-page numeric click budget was **removed** 2026-07-22 for directly
  violating AD-10 — *"observed live: a left-nav sidebar with 13 distinct
  sections only ever got its first 3 tried, silently dropping the rest."*
- Clicking a real "Log out" button used to self-terminate crawls — now
  regex-matched and refused.
- Dropdown/menu items that only render into the DOM after a click (not just
  un-hide) used to be invisible to the crawler — link-scraping is now re-run
  after every non-navigating click, not just at page load.
- OAuth/OIDC callback params (`code`/`state`/`session_state`) are stripped
  from the page-dedup fingerprint — otherwise a Keycloak silent-SSO redirect
  produced a fresh single-use `code` every time and the crawler "re-queued
  and re-captured the same 'Home' page 3+ times."
- Non-empty URL fragments (`#/orders`) are **kept** in the fingerprint (only
  a bare empty fragment is stripped) — an earlier unconditional-strip version
  silently merged every hash-routed SPA page into one node, "the root cause
  of a real run covering only 4 of an application's ~10 pages."

### How does discovery handle destructive/risky actions?

A **Safety** specialist inside the Planner's fixed chain (`loop_guard` →
`interaction_level` → `safety` → `data_resolver`) classifies each candidate
action deterministically (regex verb-list matching, plus the Application's
declared `safety_posture`: `production`/`non_production`). An
AI-assisted safety opinion (`classify_action_safety`) exists in code
(`safety_engine.py`) but is **not wired into the live crawl loop** — its own
`ponytail:` comment: paying a network round-trip per unmatched action in the
hot crawl loop "buys nothing but latency until the product actually wants
that opinion recorded." So today, 100% of discovery-time safety
classification is deterministic, despite the AI capability existing in the
codebase.

An **Interaction Level** admin setting (Passive/Normal/Aggressive) separately
gates which *kinds* of action are attempted at all — only `click` is
currently wired through beyond `view`, so only Passive has an observable
effect today.

### How are pages/forms/buttons deduplicated?

Two tiers:
1. **Crawl-time (BFS-level):** a normalized URL fingerprint is the
   `visited_pages` key. Forms dedup by full signature (action + method +
   every field name/value pair, including hidden fields) specifically so a
   per-row "Add to Cart" form (differing only by a hidden `product-id`) still
   counts as distinct. Buttons dedup by distinct accessible label per
   body/chrome region — only the first DOM instance of a repeated row-action
   pattern is clicked.
2. **Cross-run canonical merge** (`ApplicationModelBuilderActivity`,
   `model_builder.py`): merges Pages/Forms/ApiEndpoints *within and across
   every prior Discovery Run* into one canonical row via self-referencing
   `merged_into_id`. Pages group by a URL template (numeric/UUID segments
   normalized to `{id}`). Idempotent under Temporal's at-least-once retry —
   "re-running never flips an already-resolved row back and forth."

A separate, finer classifier — **State Identity** (`state_identity.py`,
Story 2.10) — decides whether a newly captured page is the *same* UI state as
one already known, using a weighted composite score (heading match + action-
name Jaccard + form-field-name Jaccard + structural-token Jaccard, including
shadow-DOM tokens). Composite ≥0.75 → SAME; ≤0.35 → NEW; in between →
**VARIANT** — deliberately *not* auto-merged, because "getting this wrong
deletes real behaviour." AI (`infer_state_similarity`) is consulted only in
that ambiguous middle band as a logged, **non-authoritative** tiebreaker.

### How are Journeys inferred from raw crawl data?

A two-stage pipeline, mostly deterministic:
1. **Navigation-graph clustering** (`journey_clustering.py`), zero LLM cost:
   union-find over canonical `PageTransition` edges groups pages reachable
   from each other. Oversized clusters are split by URL path-prefix. Clusters
   are then bin-packed (first-fit-decreasing **by page count**) into batches
   ≤150 pages each.
2. **One `infer_journeys` AI call per batch.** Batching bounds per-call
   reasoning load (the "lost in the middle" problem), not total token count
   — quoted (`journey_clustering.py`): *"This does NOT reduce the total
   number of tokens describing an Application... It bounds how much any
   single call has to reason over at once, which is what actually controls
   per-call accuracy... latency... and fault isolation."*

Journeys are deduplicated by a **content-derived fingerprint**
(`identity_key.py`'s `compute_identity_key` — SHA-256 over canonical
URLs/component identities/endpoint signatures), **never** the AI-generated
name (which varies run to run) — this is Architecture Decision **AD-13**.

**No approval gate exists.** `Journey` has no `approved`/`rejected` status —
every non-deleted Journey is immediately part of the "Trusted Knowledge
Model." Docstring: *"UX-DR21 is a hard, repeatedly-reaffirmed product
constraint, not a style choice to 'helpfully' add to later."*

### Does discovery log in to explore behind auth?

**Yes.** Two auth shapes, matching `Application.auth_method`:
- `standard_login` — the crawler drives whatever login form it finds
  (heuristically: a page with a password input, or a "Log in"/"Sign in" link
  matched by text or href pattern for icon-only links).
- `sso_session_reuse` — the stored secret **is itself** a Playwright
  `storageState` JSON blob, applied directly to a new browser context — no
  login step at all.

**Mid-crawl session expiry is a real, documented design pivot**, not just a
bug fix. It originally treated any expiry as terminal ("re-authenticate to
continue") — this broke short-lived-OAuth-token apps in real testing
(Keycloak: crawl bounced back to login within a few requests, "for a token
this short-lived that just means the crawl can never finish"). Now: expiry is
detected **content-based** (landing on a page with a password field when a
different URL was requested — not URL-list matching, so it also covers
single-route apps), and the crawler silently re-authenticates and resumes the
same page, bounded to 3 consecutive attempts so a genuinely broken login
still terminates the run (`failure_reason="session_expired"`).

### What discovery settings are admin-tunable?

A singleton `DiscoverySettings` row (one row for the whole deployment, `id=1`
enforced by a `CheckConstraint`):

| Setting | Default | Notes |
|---|---|---|
| `max_pages` | 500 | Hard BFS stop |
| `max_discovery_duration_minutes` | 30 | `None` = unlimited |
| `navigation_timeout_seconds` | 15.0 | Per-page settle timeout |
| `interaction_level` | `"normal"` | passive / normal / aggressive |
| `max_journeys` | unlimited | Overrides the 50-Journey-per-run default cap |
| `max_scenarios_per_journey` | unlimited | Generation-side cost control |
| `max_test_cases_per_application` | unlimited | Generation-side cost control |
| `delete_project_after` | `"1_month"` | Soft-delete purge retention |
| `max_heal_attempts` | 3 | Shared self-healing budget — see [Self-healing](#self-healing) |

Admin-only `GET`/`PATCH /settings`. `PATCH` uses a `"__unset__"` sentinel for
the nullable "unlimited" fields, to distinguish "leave unchanged" from
"clear back to unlimited."

### How is discovery evidence (screenshots) stored?

A screenshot is taken on every settled page visit and uploaded to **real AWS
S3** via `packages/object_store` — never inlined into Postgres (this is
Architecture Decision **AD-8**: binary artifacts referenced by object-storage
key, metadata only in the DB). Key layout: `discovery-runs/{discovery_run_id}
/{uuid4}`. A screenshot/upload failure just skips that one page's screenshot
rather than failing the whole run (this was previously fatal — fixed).

There's no separate DOM-snapshot blob — structural evidence (`heading`,
`structural_tokens`) is captured as text, inline on the `Page` row itself,
which is exactly what State Identity scores against.

### What's the DiscoveryRun status lifecycle?

`status`: `running` → `complete` | `failed` (with a `failure_reason` — a
generic crash message, or the literal `"session_expired"` /
`"worker_unavailable"` — kept as its own value per **AD-11**, so a session
expiry is never silently folded into a generic failure) — also `paused`
(resumable).

`stage` (while `status="running"`): `initializing` → `authenticating` →
`discovering` → `analyzing` → `analyzed`. `"analyzed"` is the frontend's real
stop signal — distinct from `"analyzing"` — because Journeys land one at a
time and a naive `journeys.length > 0` check under-counted multi-Journey
runs.

A documented gap-fix: if the post-crawl steps (model-building, inference)
crash after the crawl itself already wrote `status="complete"`, a dedicated
`MarkDiscoveryRunFailedActivity` **overwrites** that status with the real
failure — previously this had nowhere to write to (workflows have no DB
access per AD-2), leaving the frontend spinner stuck on "Analyzing..."
forever.

### Has the discovery engine been rewritten before?

**Yes, once** — a real architecture pivot, not incremental tweaks. Commit
`55835a7` "Land Discovery Engine v2: Stories 2.9-2.22" (2026-08-04, 60 files
changed) added the Planner/specialist-chain architecture, State Identity,
Safety Engine, Data Resolver, Blocked-Task frontier, mid-exploration
persistence/resume, locator-durability capture, and coverage-report
diagnostics — on top of the original Story 2.1-2.6 crawl (plain BFS + generic
settle waits, no planner/safety layer). `docs/DISCOVERY_ENGINE_V2.md`
documents this and self-describes as superseding "the crawl-mechanics half"
of the older `docs/EPIC_2_DISCOVERY_PIPELINE.md` (the Journey-inference half
of that older doc is still described as accurate).

### What happens when the crawler gets stuck (needs data it doesn't have, or a destructive action needs approval)?

A `BlockedTask` row is created/reused, keyed by `(application_id,
aggregation_key)` — a property of the **Application**, not one run, so the
same missing thing found on a later run re-attaches to the same open row
instead of duplicating. Crucially: **this never blocks the crawl** — *"there
is no wait/sleep/user-input call anywhere on this path... a blocked area
never stops the crawl."*

A resume mechanism (`resume.py`) exists to let an admin supply the missing
value and re-crawl forward from the nearest confirmed entry point — but it's
currently **dead code**, unreachable from any UI: *"No caller wires this up
yet... answering a `BlockedTask` has no screen in the current 6-screen IA."*

**Rejected alternative:** an earlier design stored literal replay steps
(`ExploinsurationStep`) to let a blocked point be re-reached by replaying
recorded inputs. This was abandoned for 4 concrete reasons found during
development: irreversibility isn't knowable from the DOM alone, deep-linking
past a skipped step usually fails, stored inputs go stale, and the target app
may have changed by replay time. Current design instead **re-crawls forward
under normal rules** from the nearest still-canonical confirmed entry point —
`ExplorationStep` today is purely a retroactively-reconstructed diagnostic
trail (human-readable "how did the crawler get here"), explicitly *not* a
replay script.

### What are discovery's known limitations?

- No iteration/action cap is a **deliberate accepted risk** (AD-10) — an app
  with unbounded pagination can, in principle, run long; `max_pages`/duration
  settings are the practical backstop, not a true fix.
- The `DEFAULT_ACTION_CEILING = 5000` backstop lacks explicit product
  sign-off per its own `ponytail:` note.
- Journey-inference batches run **sequentially**, not concurrently, within
  one Activity attempt — a very-large Application could approach the
  5-minute Activity timeout; concurrent dispatch is the noted (not yet built)
  upgrade path.
- The AI-assisted safety classifier (`consult_ai`) is built and tested but
  not wired into the live crawl — safety classification is 100%
  deterministic today.
- Form-submit success/failure attribution uses 2 bounded heuristics
  (navigation vs. validation-markup checks), not a fuller 3-signal design —
  can't isolate which of several co-submitted fields caused a rejection.
- Story 4.3/FR-18-style Journey **regeneration** is fully cut from scope —
  the domain model still carries the machinery for it (`Journey.attempt`),
  but nothing in the live product exercises it.

---

## Generation — Scenarios → Playwright tests

### What's the pipeline from Journey to a runnable Playwright test?

`GenerationWorkflow` (per-Journey) turns a candidate Journey into `Scenario`
rows (plain-language test cases). A separate, explicit user action
("Generate Test Suite") then fans out `SuiteGenerationWorkflow`, which turns
each current `Scenario` into a `TestAsset` (real generated Playwright
TypeScript code) grouped into a `TestSuite`. Both workflows do zero I/O
themselves (AD-2) — all DB/AI/subprocess work happens in Activities on the
generation worker.

### How does a Journey become Scenarios, and why three separate AI calls?

`ScenarioGenerationActivity` calls `generate_scenarios` **three times per
Journey**, once per `ScenarioType` ("happy"/"negative"/"edge"), rather than
one "generate everything" call.

**Why:** *"A single 'generate everything for this Journey' call let the
model's own output budget silently cap the whole response (observed: a
large 'digital banking' Journey stopped at 40 Scenarios with no error)."*

Idempotency: guarded by `(journey_id, generation_run_id)` — Scenarios already
generated for the Journey's current attempt are returned unchanged on a
Temporal retry, never duplicated.

`Scenario.test_data` is a **schema only** at this point (`{name, mandatory,
value: None}`) — the AI never fills in a real value; that happens later,
deterministically (see [test data](#how-is-synthetic-test-data-generated-and-why-not-let-the-ai-invent-it)).

### What context does the LLM get when generating Playwright code, and why so prescriptive?

`HostedAIProvider.generate_playwright` assembles, per call: every distinct
Page the Journey visits (`known_pages`), every captured `Component` +
locator on those pages ranked by durability (`known_locators`), Discovery-
captured field input types/required flags (`field_input_types`), a
deterministic `requires_auth` flag (never trusted from the LLM), and fully
pre-resolved test-data literals (the model is told these are already correct
— "use these exact values").

The system prompt is roughly 400 lines of explicit rules — timeout
constants, matcher-existence rules ("never invent a Playwright matcher"), a
"known-locators-only structural rule" (never invent a table/toast/modal
selector Discovery never captured), and a "no-fabricated-assertion rule."
Many rules carry inline `[FIXED]` notes tracing exactly which observed
failure mode they now prevent — e.g. `requires_auth` used to tell the model
to call `fillCredentials` as a *precondition*, which contradicted the
exported project's real `storageState` architecture; every generated spec
under the old prompt called `fillCredentials(page)` against the base URL and
timed out hunting a login field that only exists on the real login page.

**Why so prescriptive rather than a shorter, more "trust the model" prompt:**
the dominant limitation driving this isn't the LLM's coding ability — it's
that **Discovery never captures visual layout/presentation mechanism**
(tables vs. lists vs. toasts/modals). Roughly half the prompt's rules exist
specifically to stop the model from guessing at UI structure Discovery didn't
actually observe.

### Is there a deterministic quality gate before code ships, and why not trust the AI's own review?

Two gates, both deterministic (no AI judgment):
1. **Spec-linter** (`spec_linter.py`) — nine regex-based checks (locator
   provenance vs. Discovery's captured names, missing required fields, an
   `@auth` spec still calling the raw login helper instead of the shared
   session, sibling-spec consistency, tautological assertions, ungrounded
   "toast/modal" assertions, etc.). **Flag-only** — never blocks a spec from
   shipping; findings become `TestAsset.warnings` and flip status to
   `needs_review`. Why not block: *"an imperfect regex-over-code heuristic
   isn't trustworthy enough to reject on."*
2. **TypeScript typecheck-before-promote** (`typecheck.py`) — real `tsc
   --noEmit` against actual `@playwright/test` types, in a temp directory
   mirroring the exported project's structure. Why: *"catches
   undefined-variable/hallucinated-matcher bugs in LLM-generated code at
   compile time, before it's ever persisted as a TestAsset or run as a real
   test."* This one **does** block — code that fails typecheck is never
   promoted to `current`.

### What happens when generated code fails typecheck — does it just fail?

No — a bounded, in-Activity **repair loop**: up to 3 attempts within one
`PlaywrightGenerationActivity` call. On a typecheck failure, the failed code
and its exact `tsc` errors are carried forward as a `repair` tuple and fed
back to the model as a real multi-turn conversation ("that code failed
TypeScript compilation: `{errors}`. Fix only what's needed..."), not a blind
re-roll.

**Why:** *"A blind Temporal-level retry re-runs this whole activity with
zero memory of the previous tsc error, and was observed live repeating the
exact same string/number mistake across all 3 attempts — so self-correct
with the real compiler feedback here first."*

Only after 3 failed attempts does the Activity raise, falling through to
Temporal's own outer retry (genuine infra failures) and, at the workflow
level, a separate **wave-based retry** (see next question).

**This is a narrower loop than execution-time self-healing** — typecheck-
error-only, no live-browser/screenshot involvement (that machinery exists in
the same `generate_playwright` function but is only ever populated by the
execution-time healer, confirmed by checking `PlaywrightGenerationActivity`
never passes `failure_screenshot_png`/`live_inspection_locators`).

### What's the "wave" retry, and how is it different from the typecheck-repair loop?

`SuiteGenerationWorkflow` fans out `PlaywrightGenerationActivity` calls
concurrently across every Scenario in a suite. Under real fan-out
concurrency, some calls can exhaust their own Temporal-level retries purely
on transient timeouts (not a code defect) — the workflow retries the whole
still-pending set in up to 3 "waves," 30 seconds apart.

```python
# ponytail: fixed wave count/cooldown, not configurable — revisit if timeouts
# still exhaust 3 waves at higher real concurrency than observed live.
MAX_SCENARIO_WAVES = 3
WAVE_COOLDOWN_SECONDS = 30
```

**Why:** *"observed live — that's exactly what got stuck at 107/159"* (a
real suite that got stuck partway through generation under concurrency,
before this mechanism existed). If anything is still pending after 3 waves,
`TestSuite.status` becomes `"incomplete"` rather than silently missing tests.

### How is synthetic test data generated, and why not let the AI invent it?

**Entirely deterministic, non-AI**, in two layers:
1. **Name/type defaults** — regex-matches a field's name (password/card/
   email patterns) or falls back to its captured HTML `input_type`
   (number/tel/date/email), mirroring the same generic-value convention
   `discovery_worker/crawler.py` already uses for form-filling during the
   crawl itself.
2. **Scenario-intent-aware defaults** — if a Scenario's own name/steps call
   for a specific data property (Unicode, a length boundary, emoji, markup/
   special characters, a numeric boundary), a fixed, deliberately crafted
   literal is used instead (e.g. a password containing `ä`/`ö`/`$`, a
   128-character string, an emoji string).

**Why not AI-generated values:** *"a field's reviewer-provided value always
wins; a still-blank field gets a sensible placeholder matching its own name,
never a value the AI invents"* — this is a deliberate, repeatedly-cited
product rule (Story 4.1 AC 5), not an oversight. A backstop also strips any
AI-proposed test-data field that would submit the account's own existing
login credential, before the Scenario is even persisted.

### Does `Scenario.safety_classification` still gate anything?

**No — it's computed but no longer read anywhere for gating.** It's still
computed at generation time (a deterministic verb/pattern classifier, most-
severe-wins, `UNKNOWN` as the fail-closed default) and persisted on every
Scenario. But:
- Execution's own `PrepareTestRunActivity` states explicitly (see
  [Execution](#execution--run-all-tests)) that nothing reads it — every
  current TestAsset executes unconditionally.
- It's not surfaced in the Scenario curation UI (no badge, no filter).

It's a **vestigial field** — a leftover from "Run All Tests"'s original
(now-removed) execution-gating design, kept computed/persisted in case
policy-gated execution is reintroduced, per an explicit `ponytail:` comment
in the execution worker (see [Execution](#why-was-executionpolicysafety-gating-removed)).

### When does a human review/curate Scenarios, and what can they actually do?

**Strictly between** scenario-generation and code-generation — never after.
The flow is Discover Journeys → **Review Scenarios** → Generate Suite (code)
→ results. There's **no approve/reject status** on `Scenario` — curation is
limited to rename, hard-delete, and fill-in-a-test-data-value. The "Generate
Test Suite" button is enabled as soon as there's at least one Scenario
(previously gated on test-data completeness — relaxed once the deterministic
default-value generator existed as a backstop).

---

## Execution — Run All Tests

### What is "Run All Tests," and what's the unit of execution?

**The whole Application**, not one suite/test at a time — one click (or the
"Run Suite" button) runs every current `TestAsset` across every current
`TestSuite`/Journey for the Application.

**Why:** *"per the grill-me design review"* — a design decision explicitly
attributed to that review process, quoted from
`packages/workflows/src/workflows/execution_workflow.py:1-4`.

Orchestrated by `ApplicationTestExecutionWorkflow`: `PrepareTestRunActivity`
→ fan-out `ExecuteTestActivity` (bounded by an `asyncio.Semaphore`, default
concurrency 5) → `HealTestActivity` (unconditionally, after every execute —
see [Self-healing](#self-healing)) → `FinalizeTestRunActivity`. Every "Run
All Tests" click starts a **brand-new** `TestRun` — there's no rerun-scoped/
failed-only mode.

### Why was ExecutionPolicy/safety gating removed?

`PrepareTestRunActivity` runs every current `TestAsset` unconditionally
against `Application.url`, regardless of `Scenario.safety_classification`.
Quoted (`apps/workers/execution/src/execution_worker/activities.py:254-264`):

> `ponytail:` no ExecutionPolicy/allowlist/destructive-action gating here —
> deliberately removed per explicit request, to let "Run All Tests" work
> with zero setup. The `ExecutionPolicy` model/table and its `GET`/`PUT`
> endpoints still exist but nothing reads them on this path anymore... To
> restore the original "deny by default" design: re-add a
> `select(ExecutionPolicy)...` lookup here, short-circuit to
> `TestRun.status="blocked"` when disabled/off-allowlist, and re-gate the
> per-asset loop below on `classification == "SAFE" or
> policy.destructive_actions_permitted`.

This is a **product decision**, documented with its exact reversal path, not
an oversight — `execution_policy_id`/`execution_policy_version` on `TestRun`
are kept nullable rather than dropped in case the gating comes back.

### How does concurrency work — within one run, and across runs?

Two separate, deliberately distinct knobs:
- **Within one TestRun:** `asyncio.Semaphore(max_concurrency)` inside the
  workflow, default 5 — bounds how many `ExecuteTestActivity` calls run
  concurrently for *this* run.
- **Across concurrent runs on one worker process:** the execution worker's
  own `Worker(max_concurrent_activities=...)` (k8s manifest:
  `EXECUTION_WORKER_MAX_CONCURRENT_ACTIVITIES=6`).

Because several `ExecuteTestActivity` calls run against the **same assembled
project directory** at once, Playwright's `--output` is set to a per-
`test_result_id` subdirectory — otherwise one test's screenshot/trace scan
could pick up another concurrently-running test's artifacts.

### How is a shared login session handled when tests run concurrently?

**Logged in exactly once per TestRun**, in `PrepareTestRunActivity` (which
always runs alone, before any `ExecuteTestActivity` starts — no race to
guard). Every subsequent `npx playwright test` invocation passes `--no-deps`
to *reuse* the resulting `.auth/state.json` read-only rather than each test
independently re-logging-in.

**Why:** without this, several concurrently-running tests each re-running
`auth.setup.ts` would all overwrite the shared session file — "a same-account
app that only allows one active session (routine for a banking-style app)
boots out whichever concurrent test was mid-run."

If a concurrent test detects its restored session went invalid mid-run
(another test logged out / changed the password / etc. — a support fixture
raises a clearly-marked `AUTH_SESSION_INVALID` error for this),
`ExecuteTestActivity` refreshes the shared session once and retries that one
test exactly once against the fresh session, rather than reporting it as a
generic flaky failure. A dedup lock (5-second window) stops several
concurrent failures from all independently triggering their own refresh —
whoever loses the race just reuses what the winner produced.

### How is a test run's status/progress tracked, and how does the UI poll it?

`TestRun.status`: `pending` → `running` → `completed` (or `blocked`, now
effectively dead — see above). Per-`TestResult` counts (`passed_count`,
`failed_count`, `timed_out_count`, `errored_count`, `blocked_count`) are
re-tallied and committed after **every individual** test result, not just at
the end — "without this, StatTiles sit at 0 for the whole run since
FinalizeTestRunActivity only tallies once, at the very end."

If `FinalizeTestRunActivity` itself exhausts its retries, a last-resort
`ForceCompleteTestRunActivity` force-closes the run (re-raising afterward so
the workflow still shows Failed in Temporal for observability) — "every
TestResult may already be terminal, but TestRun.status would otherwise stay
'running' forever (no reconciliation job exists to catch this later)."

### What was the "run number" feature, and what problem did it solve?

**Commit `1c788e5`, "add run number changes"** (2026-09-01). Before this,
`TestRun` had no stable, human-friendly sequence number — the UI could only
show a timestamp. This added `TestRun.run_number` (per-Application sequential
integer, restarting at 1 for each Application) and a `#{run_number}` display
in the Runs tab list/detail view.

**How, mechanically:** `Application.next_test_run_number` is claimed
atomically inside the same transaction that creates the `TestRun` row:

```python
run_number = session.execute(
    update(Application)
    .where(Application.id == application.id)
    .values(next_test_run_number=Application.next_test_run_number + 1)
    .returning(Application.next_test_run_number - 1)
).scalar_one()
```

**Why atomic, and why not a `COUNT(*)` at read time:** Postgres's row lock on
this `UPDATE` (held until commit) is what makes two concurrent "Run All
Tests" clicks for the same Application race-safe — the same
`update(...).where(...).values(...)` idiom the self-heal claim/release logic
already used elsewhere in the codebase, extended with `.returning()`. A
`COUNT(*)`-based approach would race under concurrent inserts.

### What was the "status of the test run is not getting updated" bug, and what fixed it?

**Commit `c88d4f2`** (2026-08-31). Before the fix, `PrepareTestRunActivity`
only wrapped the *assembly/install/auth-setup* step in a `try/except` that
force-closed the `TestRun` on failure — a crash **earlier**, in
`_load_assembly_inputs_sync` itself (a bad query, before any `TestResult` row
existed), had no such safety net and left `TestRun.status` stuck at
`"running"` forever with zero `TestResult`s.

**Fix:** widened the `try/except` to wrap the *entire* Prepare body (loading
assembly inputs → creating TestResult rows → project assembly), so any
failure at any point still force-closes the run with an accurate
`errored_count`. The same commit also introduced `ForceCompleteTestRunActivity`
(see above) as the workflow-level safety net for when even
`FinalizeTestRunActivity` itself fails. A new regression test
(`test_prepare_force_closes_run_when_assembly_inputs_crash_before_any_test_result`)
locks in the earlier-crash case specifically.

### Why was the execution-worker CPU limit changed from 4 to 2 cores?

**Commit `6e8c803`, "updated cpu limit to 2 core"** (2026-08-28) — a single-
line change to `ops/k8s/10-execution-worker.yaml`, `resources.limits.cpu:
"4"` → `"2"`. No commit message beyond the title and no code-level comment
explaining the motivation exists in the repo — likely a cluster-capacity/cost
tuning decision made outside the codebase (e.g. observed real usage never
approaching 4 cores, or freeing headroom for other pods on the same node).
This is the one instance, across all the resource-limit history checked, of
a **decrease** rather than an increase — every other worker's limits (e.g.
generation-worker's memory, which climbed `512Mi → 1024Mi → 4096Mi → 6Gi`
across several commits in one day, 2026-08-14) only ever went up.

### How does execution differ from discovery's own browser automation?

Both use Playwright, but for different purposes and via a different
mechanism: discovery drives a **live, in-process Playwright browser** to
explore and capture evidence (`discovery_worker/crawler.py`, Python-side
`playwright` API calls). Execution instead **assembles a real, standalone
Playwright *project*** (via `packages/test_suite_assembler` — the same code
path that produces the downloadable ZIP) and shells out to `npx playwright
test <spec> --reporter=json` as a subprocess per test, parsing the JSON
report for pass/fail/timeout/error and artifact paths. Execution never
imports discovery's crawler code — they only share the underlying
`Application`/credential-resolution and Vault mechanism.

### What happens to a failing test's output — screenshots, traces?

`--output=test-results/{test_result_id}` isolates each concurrent test's
artifact directory. On any non-`passed` outcome, `.png`/`.zip` files under
that directory are read, uploaded to S3
(`ObjectStore.put_test_artifact`, keyed `test-runs/{test_run_id}/{uuid4}`),
and recorded as `TestResultArtifact` rows. A **heal attempt rerunning the
same TestResult** deletes the prior artifact set first — "only the latest
run's artifacts are ever meaningful... the whole heal history" isn't kept.

### What are execution's known limitations?

- Every "Run All Tests" click executes **unconditionally** — no destructive-
  action gating today (deliberate, reversible, see above).
- A `TestResult` whose `ExecuteTestActivity` exhausts its own Temporal retry
  policy is folded into a generic `"errored"` status rather than getting its
  own distinct status (e.g. `"infra_failed"`) — Temporal's own
  retry-exhaustion detail isn't threaded back to the row today, flagged as a
  known simplification.
- `_run_playwright_test`'s JSON-report parser only reads the fields this
  activity actually needs (final outcome, duration, first/concatenated
  error) rather than the reporter's full schema (per-test retries, richer
  attachment metadata) — flagged with its own `ponytail:` note, "revisit if
  a real run surfaces a shape this doesn't handle."
- Project rebuild after a worker restart mid-run (assembled project dir lives
  on local disk, not persisted) is serialized behind one **global** lock, not
  per-TestRun — an accepted trade-off since rebuilding is an exceptional
  recovery path, not the hot path.

---

## Self-healing

### What is self-healing, and is it the same thing at generation time and execution time?

**No — these are two distinct mechanisms that share only a config value.**

- **Generation-time repair** (see
  [Generation](#what-happens-when-generated-code-fails-typecheck--does-it-just-fail)):
  a narrow, typecheck-error-only loop, capped at 3 attempts inside one
  Activity call, no live browser/vision fallback.
- **Execution-time healing** (`HealTestActivity`, in
  `apps/workers/execution`): a much richer, real-execution-driven loop —
  real execution → failure evidence → AI diagnosis (with the failure's error
  message, stack trace, console output, and a screenshot) → targeted code
  edit → typecheck → promote → **real re-execution** → repeat, bounded by
  `DiscoverySettings.max_heal_attempts` (shared budget, see below).

Both call the same underlying `generate_playwright` function in
`packages/ai_provider`, but only the execution-time path ever populates its
richer failure-context parameters (`failure_screenshot_png`,
`live_inspection_locators`, etc.) — confirmed by checking that
`PlaywrightGenerationActivity` (generation-time) never passes them.

### Is `max_heal_attempts` one shared budget, or separate per pipeline?

**One shared, single admin-configurable budget** — `DiscoverySettings.
max_heal_attempts` (singleton row, default 3; `0` disables healing entirely).
There is no separate generation-time-vs-execution-time budget field anywhere
in the codebase (verified by grepping every reader of the field: the
execution worker's `HealTestActivity`, the API's manual-retry `/heal`
endpoint, and the web UI's `Settings.tsx` all read the same column). What
looks like "generation healing" during an execution-time heal is actually
`HealTestActivity` **calling back into** the generation worker's existing
`generate_playwright` activity — a callee, not an independent budget.

### How does execution-time healing decide it's a "code" problem vs. an "infrastructure" problem?

A deterministic classifier, checked **before** any AI call or attempt is
spent: `_is_infra_failure` matches known infra-error signatures (a JSON
report that failed to parse, a setup/login dependency failure, a config
mismatch, the whole-process timeout). An infra failure gets **one same-code,
no-AI rerun**, and never consumes a heal attempt — "bounds a persistently-
down target application to one extra rerun per check rather than spinning
this activity forever." Only a failure that survives that check is treated
as a real code defect worth an AI-diagnosed fix.

### Does healing use a live browser to double-check a fix's locators?

**Yes, but narrowly and deterministically gated.** A separate classifier,
`_is_locator_failure` (four fixed regex patterns — a locator Playwright
waited for and never found, a locator now matching multiple elements, an
element removed from the DOM, or unrendered dynamic content), decides
whether to launch a **targeted live Playwright inspection** of one specific
page (the scenario's own last-known page, or the bare application URL as a
fallback) before asking the AI for a fix — never a full re-crawl, and reusing
the same auth session, never a fresh login. The AI can also request this
inspection itself for the *next* attempt via a response flag, but that
request only ever carries forward one iteration, never accumulates.

### What stops healing from looping forever on an unfixable test?

A "no-progress" guard: each attempt's failure is fingerprinted (error message
with digits stripped, so incidental timestamp/line-number noise doesn't
count as "different"); if the new failure's fingerprint matches the previous
attempt's, the loop stops immediately rather than burning the remaining
budget on an unproductive retry.

### How does the UI show that a passing test only passed after healing?

A dedicated "auto-healed" indicator (a lightning-bolt icon,
`AutoHealedIcon` in `RunsTab.tsx`) marks a `TestResult` whose
`healed_test_asset_id` is set — "healed and now passing" vs. "healed but
still failing" is distinguished with no extra field, purely by combining
`status` with whether `healed_test_asset_id` is set. During an in-progress
heal, the run detail view shows live progress copy like "Self-healing in
progress — remediation attempt {n} of {max_heal_attempts}."

---

## Web UI / product workflow

### What's the end-to-end onboarding flow?

A 4-step wizard (`apps/web/src/App.tsx`), each step tracked against a
`furthestCount` so Previous/Next can revisit an already-completed step
without losing its checkmark:

1. **Connect Application** — name, URL, optional login URL, environment
   (staging/qa/other), auth method (only `standard_login` is backend-live
   today; API-key and OAuth-client-credentials options are shown per
   confirmed design but disabled, "coming soon"). Explicit warning to use a
   dedicated test account, never a real end-user identity. Once connected,
   the form becomes a read-only receipt — not editable inline again; credential
   rotation happens later, in the Workspace's Credentials tab.
2. **Discover Journeys** — live crawl progress, then a renameable,
   collapsible list of discovered Journeys (consecutive same-stage steps
   collapsed into one "flow node" — "the reviewer wants the business flow
   (Login → Cart → Checkout), not one row per captured step").
3. **Review Scenarios** — AI-generated Scenarios per Journey, tagged Ready
   vs. "Needs data," filterable, renameable.
4. **Generate Suite → Test Suite Results** — triggers suite generation, then
   shows the generated test cases with a preview of the exported Playwright
   project's file layout. "Run Tests" from here hands off into the Workspace
   on the Runs tab.

**Dead-code note:** `apps/web/src/components/GenerateSuite.tsx` still exists
in the repo but is unreferenced by `App.tsx` — the UI flow was simplified so
"Generate Test Suite" on Review Scenarios triggers generation directly, no
separate config screen. A real example of code outliving the UX flow it was
built for.

### What's the Workspace, and what are its tabs?

The persistent per-Application dashboard, entered from Home once onboarding
is complete. A fixed left icon rail with five tabs:

| Tab | Purpose |
|---|---|
| **Overview** | Health-tier summary (healthy/needs_attention/critical), pass-rate headline, journey/scenario/suite counts |
| **Suite** | Browse generated test assets and their code |
| **Runs** | List of TestRuns, drill into results, artifacts (screenshots/traces), auto-heal indicators, and the global "Run Suite"/"Run All Tests" trigger |
| **Author** | **Not yet built** — a "Coming soon" placeholder for chat-based/record-based manual test authoring |
| **Credentials** | **Admin-only**, hidden entirely for non-admins — rotate a connected application's stored login (standard_login apps only; SSO-session-reuse apps aren't supported here yet) |

The Runs tab continuously polls every 2 seconds to reflect whether *any* run
is active, regardless of which browser tab/user started it — "not just this
browser tab's own click."

### Is there a project/application limit?

Yes — `MAX_ACTIVE_PROJECTS = 4`, enforced both client-side (to avoid inviting
a 409) and for real, server-side.

---

## Infrastructure & deployment

### Where do the Kubernetes manifests live, and what does each service look like?

`ops/k8s/` (README.md's stated path, `k8s/`, doesn't actually exist — this is
one documented drift; see limitations). Per service:

| Service | Resources (req/limit) | Service type | Notes |
|---|---|---|---|
| `api` | 100m/500m CPU, 256Mi/512Mi mem | **ClusterIP**, fronted by a separate ALB Ingress | |
| `web` | 50m/200m CPU, 64Mi/128Mi mem | **ClusterIP**, fronted by a separate ALB Ingress | `VITE_API_BASE` baked at build time |
| `discovery-worker` | 500m/4 CPU, 1Gi/4Gi mem | none (outbound only) | real headless Chromium per crawl justifies the request |
| `generation-worker` | 250m/2 CPU, 512Mi/6Gi mem | none | memory climbed steadily across several 2026-08-14 tuning commits |
| `execution-worker` | 500m/**2** CPU (cut from 4), 1Gi/4Gi mem | none | see the [cpu-limit commit](#why-was-the-execution-worker-cpu-limit-changed-from-4-to-2-cores) |
| `vault` | none set | ClusterIP | dev-mode, in-cluster, even in production |
| `temporal` | none set | ClusterIP | dev-mode, no persistence/HA |

**Documented drift found:** README.md's own service-type table lists `api`
and `web` as type `LoadBalancer` — the actual manifests define both as
`ClusterIP` fronted by ALB `Ingress` resources instead. No commit was found
reconciling the README with this change; flagged as stale documentation, not
a deliberate discrepancy.

### Why is Postgres/S3 hosted externally but Vault runs in-cluster, dev-mode, even in production?

**This asymmetry is explained in-repo, not an oversight.** Postgres and S3
are genuinely stateful, customer data — hosted externally (e.g. RDS) for
durability/backup/ops reasons standard to any production deployment.

Vault, by contrast, only stores **onboarded Applications' target-app
credentials** — re-creatable, low-stakes data, not the platform's own primary
data. Quoted (`ops/k8s/03-vault.yaml:1-5`): *"Dev-mode Vault, in-cluster, no
persistence (matches local docker-compose parity) — its data is scoped to
storing onboarded Applications' target-app credentials..., not deployment
secrets. The root token itself comes from the `aitestgen-secrets` k8s Secret,
not a hardcoded value."* A restart-wipe just means those credentials need
re-entering, not real data loss. No comment anywhere states a plan to move
Vault off dev-mode.

**Production-readiness note:** judged by blast radius if it goes wrong, this
is the single biggest operational risk in the deployment — a pod restart
silently wipes every onboarded Application's stored credentials with no
alert, no backup (this session's own history already includes a real local
outage from exactly this). It sits ahead of the explicit,
reversible-with-documented-rollback-steps decision to skip destructive-action
gating (see [Execution](#why-was-executionpolicysafety-gating-removed)), and
ahead of the missing-observability gap below. Two smaller, related gaps:
`ops/k8s/` has no `HorizontalPodAutoscaler`, `PodDisruptionBudget`, or
backup/restore config for anything (checked directly — none exist), and no
reconciliation job sweeps a `TestRun` that gets stuck outside the *known*
failure paths `ForceCompleteTestRunActivity` already guards.

### Why did local dev and production both move off MinIO to real S3?

**Two companion commits, 2026-07-27/28:**
- `d32d80e` "cle" (2026-07-27) — the in-cluster/production side: deletes
  `ops/k8s/04-minio.yaml` entirely, swaps the ConfigMap's `MINIO_*` keys for
  `AWS_S3_BUCKET`/`AWS_REGION`, swaps worker env from `MINIO_ACCESS_KEY`/
  `MINIO_SECRET_KEY` to `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (with a
  new comment recommending IRSA/Pod Identity over static keys), and rewrites
  `object_store.py`'s dual-backend branch (`if AWS_S3_BUCKET: ... else:
  minio`) down to S3-only.
- `785dea9` (2026-07-28, same day the README's `[UPDATED]` marker moved)
  — the local-dev side: removes the `minio` service from
  `docker-compose.yml` entirely, so local dev now also points at real S3.

**Why:** no explicit rationale beyond the commit titles is recorded, but the
effect is unambiguous — one fewer backend to keep in parity, no
dev/prod-divergent object-storage code path to maintain (the dual-backend
branch itself was flagged in its own docstring as "the local/CI MinIO
backend... was removed once local dev also moved to pointing at real S3").

### Is there a deploy pipeline, and how does it relate to GitHub Actions CI?

**They're fully separate.** GitHub Actions (`.github/workflows/ci.yml`) is a
**quality gate only** — `workflow_dispatch`-triggered (manual dispatch, no
automatic push/PR trigger configured), running three jobs: `python`
(lint/typecheck/test against Postgres+Vault+Temporal services), `web`
(lint/typecheck/test/build), and `api-types-drift` (the AD-6 enforcement job).

**Actual build-and-deploy runs through Jenkins** —
`ops/jenkins/Jenkinsfile-{api,web,discovery-worker,generation-worker,
execution-worker}`, triggered automatically on push (`githubPush()`). Each
builds a Docker image, pushes to ECR, renders the target manifest's image
placeholder, `kubectl apply`s it, and (for the API pipeline specifically) runs
a "Run Database Migrations" stage that `kubectl exec`s into a pod to run
`alembic upgrade head`. A dedicated RBAC manifest
(`ops/k8s/02-jenkins-rbac.yaml`) grants Jenkins's service account
`pods/exec` specifically for this — applied manually, since Jenkins's own
service account can't self-escalate that permission via K8s RBAC rules.

### How does this scale, and what breaks first under load?

Each pipeline stage has its own bounded concurrency knob (crawl is one
browser per DiscoveryRun; suite generation fans out per-Scenario, capped by
Temporal's own worker concurrency; execution defaults to 5 concurrent tests
per run, 6 concurrent activities per worker pod — see
[Execution](#how-does-concurrency-work--within-one-run-and-across-runs)). The
first real ceiling is the **LLM proxy**: no client-side rate-limiting or
backoff logic exists anywhere in `packages/ai_provider` beyond Temporal's own
bounded 3-attempt retry policy, so many concurrent Applications
generating/healing at once would contend on the same proxy with no
queueing/backpressure in-code. The second is the **execution worker's global
rebuild lock** (see [Execution limitations](#what-are-executions-known-limitations)).
No load testing or capacity numbers exist in the repo to say where either
ceiling actually bites in practice.

### Is there production observability — logs, metrics, tracing, alerting?

No metrics/tracing stack exists in the codebase — grepped for
Prometheus/Grafana/OpenTelemetry/Sentry/Datadog/structured-metrics libraries
across every Python package: none found. Debuggability today is Temporal's
own Web UI (workflow/activity history, replayable), each `TestRun`/
`DiscoveryRun`'s own status/failure_reason columns, and whatever k8s/
container logs capture — a real gap for diagnosing a production incident
faster than reading the Temporal UI and container logs by hand.

---

## CI/CD

See [Is there a deploy pipeline](#is-there-a-deploy-pipeline-and-how-does-it-relate-to-github-actions-ci)
above for the CI/deploy split. Within `ci.yml` itself:

- **`python` job** — Postgres 18.4 and Vault 1.18 run as real GitHub Actions
  `services:`; Temporal is started via a plain background `docker run`
  instead, because its dev-server image needs a command override
  (`server start-dev`) that the declarative `services:` block can't express.
  Vault is included specifically so the AD-5 "credentials never touch
  Postgres/logs in plaintext" test enforces for real rather than silently
  skipping when Vault is unreachable.
- **`web` job** — Node 22.18, `oxlint` → `tsc -b` → `vitest run` → `vite
  build`.
- **`api-types-drift` job** — starts the API (no Postgres needed, only
  `/openapi.json`), regenerates the frontend types, `git diff --exit-code`s
  the result.

### How much should we trust a green CI run?

CI is **`workflow_dispatch`-only, not triggered automatically on push/PR**
(verified directly in the workflow file) — a green run reflects whoever last
manually triggered it, not necessarily the latest commit. Internally, the
team has at least once tracked a concrete quality KPI in a commit message —
`d6f38e7 "pass percentage has been increased to 52%"` (2026-08-21) — implying
generated-test pass rate is/was watched as a number, though no dashboard or
current figure exists in-repo; treat that 52% as a dated historical
snapshot, not a current SLA.

---

## Object storage

### What is `ObjectStore`, and who uses it?

`packages/object_store/src/object_store/client.py` — a thin wrapper around
`boto3`'s S3 client (real AWS S3 only, see above), with explicit
`connect_timeout=5s, read_timeout=30s` (boto3's own default has *no* read
timeout at all, "which would otherwise block indefinitely"). Originally lived
inside `apps/workers/discovery` and was extracted into this shared package
once `apps/api` became a second consumer.

Three producers, one client, distinguished only by key prefix:
- **Discovery** — screenshots, `discovery-runs/{discovery_run_id}/{uuid4}`.
- **API** — reads them back via `presigned_get_url()` for the journey-steps
  screenshot lightbox.
- **Execution** — failure artifacts (screenshots/traces),
  `test-runs/{test_run_id}/{uuid4}`, via `put_test_artifact()`.

`presigned_get_url()` supports overriding the response `Content-Type`/
`Content-Disposition` per-request — this also repairs objects stored *before*
that fix, which S3's default `binary/octet-stream` content-type made browsers
refuse to preview.

`delete_prefix()` (paginated `list_objects_v2`/`delete_objects`) backs the
deleted-project purge job — noted to handle a single run exceeding S3's
1000-key `delete_objects` batch limit.

---

## Product naming history

### Was Vantage always called "Vantage"?

**No — three names, in order**, traceable through frontend branding commits
and `PRODUCT.md` (not through PRODUCT.md's own edit history, since the file
was created already saying "Vantage" — see below):

1. **AITestGen** (generic internal name) — repo name, package names, a
   generic `Logo` component, a `aitg-drift` CSS keyframe.
2. **WaveQA** (briefly, ~Aug 17–20, 2026) — commit `aede8f5` "Branding
   changes" introduced a WaveMaker-co-branded identity
   (`WaveQaMark`/`WaveQaWordmark`, "wave[magnifying-glass]A" next to the
   WaveMaker logo, a "For Web Apps" tagline). Propagated into transactional
   emails the next day (`855f9bf`).
3. **Vantage** (current, Aug 20 2026 onward) — commit `0e14412` "Branding
   changes" is the actual rename: deletes the WaveQA/WaveMaker assets, adds
   `vantage-mark.png`, rewrites `Brand.tsx` to a standalone gradient-text
   "Vantage" wordmark (dropping the WaveMaker co-brand entirely). **This same
   commit also creates `PRODUCT.md` from scratch**, already stating "Vantage
   (formerly internally called AITestGen)" — the WaveQA interlude is
   real (dated, in the commit history) but isn't mentioned in PRODUCT.md's
   text, which jumps straight from AITestGen to Vantage.

The domain/DNS rename lagged the in-app rebrand by about a day: `c81ecee`
"updated dns entry" (Aug 21) flipped hostnames from `*.onwavemaker.com` to
`*.omnewave.com`/`vantage*.omnewave.com`.

**Why the repo/package names still say AITestGen:** PRODUCT.md itself
addresses this directly — *"the repo, package names, and some internal docs
still say AITestGen — cosmetic drift only, not a product-truth conflict."*

---

## Architecture Decision (AD) rule registry

Numbered rules cited throughout the codebase (grep-collected across `docs/`,
`packages/`, and `apps/` — `docs/DEVELOPER_GUIDE.md`'s own table only lists a
partial set and is stale in multiple, specific ways, verified line-by-line
against current code:
- Says "Current state: Stories 1.1–1.3" and calls `DiscoveryWorkflow`/
  `GenerationWorkflow` no-ops — both are fully implemented, and the
  workflows package now exports **five** real workflows total
  (`CleanupWorkflow`, `DiscoveryWorkflow`, `ApplicationTestExecutionWorkflow`,
  `HealTestExecutionWorkflow`, `GenerationWorkflow`, plus
  `SuiteGenerationWorkflow`) — three the guide never mentions at all.
- Its package table omits `test_suite_assembler`, `safety_classifier`, and
  `locator_capture` — all real members of the `uv` workspace today.
- Its AD table omits AD-8 (object-storage-key-not-inline-Postgres), which
  the code cites explicitly (`packages/object_store`).
- It claims only 4 DB tables exist (`organization`, `platform_user`,
  `application`, `discovery_run`) — the domain package actually has roughly
  30 entity files (journeys, scenarios, test assets/runs/results, invites,
  password resets, blocked tasks, capabilities, forms, API endpoints, etc.).

The fuller AD list below was reconstructed from in-code comments, not from
that one doc):

| AD | Rule |
|---|---|
| AD-2 | Temporal workflows contain **zero I/O** — orchestration only, all real work in Activities. Reason: Temporal replays workflow code to recover from failure; I/O inside a workflow breaks determinism. |
| AD-3 | Every LLM call goes through the `AIProvider` port — no Activity imports a vendor SDK directly. Reason: swap hosted ↔ on-prem AI without touching business logic. |
| AD-4 | `DeliveryAdapter`/`CIInstructionsGenerator` are scaffolded ports with no live implementation and no history of ever having one — speculative seams from the initial scaffolding commit, not a built-then-removed feature. |
| AD-5 | Secrets only via `SecretsClient`, never a plaintext DB column. |
| AD-6 | The OpenAPI spec is the only web/api contract — generated types, drift-checked in CI. |
| AD-8 | Binary artifacts referenced by object-storage key, never inlined into Postgres. |
| AD-9 | Idempotency under Temporal's at-least-once Activity retry — never duplicate rows on replay. |
| AD-10 | Exhaustive traversal is the crawler's only stop condition — no arbitrary safety cap (accepted risk). |
| AD-11 | `failed` vs. `session_expired` is a distinct status, never collapsed into a generic failure. |
| AD-12 | Central org-scoping via `api.auth.current_org_id`, never re-implemented per endpoint. |
| AD-13 | `Journey.identity_key` is a deterministic fingerprint of underlying evidence — never derived from the AI-generated name or step order. |
| AD-14 | Canonical vs. superseded/merged rows (`merged_into_id`) — always query canonical only. |
| AD-15 | Soft-delete only (`Application.deleted_at`) — child rows/secrets/S3 objects deliberately left behind until a separate purge job runs. |
| AD-16 | In-process, per-Activity-execution cache only — no Redis. |
| AD-19 | The Safety specialist runs before the Data Resolver — resolving inputs for an action that will never execute is wasted work. |
| AD-20 | `ExplorationStep` is deliberately distinct from `JourneyStep` — records a crawl-time path that may never become a Journey. |
| AD-22 | Discovery pause/resume durability comes from already-durable typed-row writes, not a new persistence mechanism. |
| AD-23 | The already-committed typed-row writes ARE the checkpoint — no separate checkpoint store. |

(AD-1, AD-7, AD-17, AD-18, AD-21 were not found referenced anywhere in the
current codebase — likely reserved/unused numbers, or their rules were
folded elsewhere; not asserted as gaps, just unconfirmed.)

---

## Known limitations / ponytail debt ledger

This project uses an in-repo convention (`ponytail:` comments) to mark
deliberate scope cuts — "the simplest thing that satisfies the current
scope, not the fully general solution" — with their reasoning and upgrade
path inline. Collected here as a single limitations list, by area.

**Explicitly cut from scope (not simplifications — whole features removed or
never built):**
- **On-prem/BYO-LLM support** (`CustomerEndpointAIProvider`) — named as a
  future adapter in the `AIProvider` port's own docstring, never built; the
  epic that owned it (Epic 7) was removed from scope entirely.
- **CI/CD delivery integration** (`DeliveryAdapter`/`CIInstructionsGenerator`
  ports) — scaffolded on day one (AD-4), never implemented, no evidence a
  feature was ever built and then torn out; corrects an over-claim in this
  repo's own README, which frames it as "feature removed" — `git log
  --follow` shows no such removal ever happened.
- **Destructive-action gating on "Run All Tests"** — deliberately removed
  "to let 'Run All Tests' work with zero setup"; the `ExecutionPolicy`
  model/endpoints still exist, unread, with the exact re-wiring steps left
  in a code comment (see [Execution](#why-was-executionpolicysafety-gating-removed)).
- **Scenario/Journey regeneration** — cut from Story 4.3/FR-18; the domain
  model still carries `Journey.attempt` for it, but nothing in the live
  product exercises it.
- **"Author" tab** (chat/record-based manual test authoring) — a "Coming
  soon" placeholder in the Workspace UI today, not wired to anything.

**Discovery:**
- No hard action/iteration cap (AD-10, accepted risk); the numeric backstop
  (`DEFAULT_ACTION_CEILING = 5000`) lacks explicit product sign-off.
- Journey-inference batches run sequentially, not concurrently, within one
  Activity attempt.
- AI-assisted safety classification (`consult_ai`) is built but not wired
  into the live crawl — safety classification is 100% deterministic today.
- Form-submit success/failure attribution can't isolate which of several
  co-submitted fields caused a rejection.
- Blocked-task resume exists in code but has no UI to trigger it — dead
  code today.
- Journey regeneration (content-based re-attempt) is fully cut from scope.

**Generation:**
- Generation-time repair is narrower than execution-time healing —
  typecheck-only, no live-browser/vision fallback.
- Spec-linter is regex-over-code, not an AST — deliberately non-blocking.
- No maxlength constraint is captured by Discovery, so long-value test data
  is best-effort, not a verified app-specific boundary.
- The wave-retry count/cooldown (3 waves, 30s) is a fixed constant, not
  configurable.
- `Scenario.safety_classification` is computed and persisted but unread by
  both execution and the curation UI — pure vestige of a removed feature.

**Execution:**
- No destructive-action gating on "Run All Tests" — deliberate, reversible.
- A `TestResult` whose Activity exhausts Temporal's own retries is folded
  into generic `"errored"` rather than a distinct status.
- The Playwright JSON-report parser reads only the fields this activity
  needs, not the full reporter schema.
- Project-directory rebuild after a worker restart is serialized behind one
  global lock, not per-TestRun.

**Infra/docs:**
- README.md's Kubernetes service-type table (LoadBalancer) is stale relative
  to the actual manifests (ClusterIP + ALB Ingress).
- `execution-worker`'s CPU limit was cut from 4 to 2 cores with no recorded
  rationale beyond the commit title.
- No CHANGELOG.md exists anywhere in the repo.
