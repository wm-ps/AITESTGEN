# Sprint Change Proposal — Import Experience & Progress UX Improvements

**Date:** 2026-07-21
**Prepared by:** bmad-correct-course workflow, with Harsha
**Mode:** Incremental (each proposal reviewed and approved individually before compilation)

---

## 1. Issue Summary

Three related improvements to the Application onboarding/import experience were raised as a change request:

- **CR-1 — Dynamic Browser Branding:** the browser tab should show the imported Application's name and favicon instead of a generic "Web" title and placeholder icon, staying in sync with whichever Application the user is currently working in.
- **CR-2 — Business-Oriented Import Progress:** the import (Discovery Run) lifecycle should stream progress as plain business-language stages (Initialization → Authentication → Discovery → Analysis, each with a fixed percentage), replacing any technical crawling terminology or raw live-feed detail in the user-facing progress view.
- **CR-3 — Application Reachability Validation:** the platform should validate that a submitted Application URL is actually reachable and deployed before starting import, failing fast with a clear message if it isn't.

None of these originated from a defect surfaced during implementation — they are new stakeholder-driven UX requirements, discovered and confirmed collaboratively during this workflow. All three were clarified and scoped interactively:

- CR-1's favicon is **auto-fetched from the target URL** (no new manual field on Connect App).
- CR-2's progress reaches the browser via **polling** (no new streaming infrastructure), and its **"Analysis" stage covers AI inference only** — the Application Model Builder step folds into the "Discovery" stage.
- CR-3 reuses the same reachability tolerance (2xx/3xx = reachable) already established by FR-6(f) for discovery-time destination handling.

## 2. Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| **Epic 1** (Foundation, Auth & Onboarding) | Story 1.3 gains two new ACs (CR-3 reachability check, CR-1 favicon capture). New Story 1.6 added (browser tab branding). No epic redefinition — scope extends within the existing epic. |
| **Epic 2** (Runtime Discovery & AI Inference) | Stories 2.1, 2.2, 2.6 — all currently in `review` — gain new ACs and must revert to `in-progress` for rework. Story 2.2's AC3 is walked back (raw live-feed no longer user-facing). New Story 2.7 added (progress display). Story 2.3 unaffected in substance (one clarifying note only). |
| Epics 3, 4 | Not affected. |

### Story Impact

- **Story 1.3** (`review`) — gains reachability-validation AC (CR-3) and favicon-auto-fetch AC (CR-1). Stays in `review`/reverts to `in-progress` for this addition — see Implementation Handoff.
- **Story 1.6** (new) — Dynamic Browser Tab Branding. Added to Epic 1 as `backlog`.
- **Story 2.1** (`review` → `in-progress`) — gains an AC setting `DiscoveryRun.stage=initializing` at workflow start.
- **Story 2.2** (`review` → `in-progress`) — AC3 rewritten: raw live-feed requirement removed from user-facing scope (data capture itself is unchanged); gains stage-transition ACs (`authenticating`, `discovering`).
- **Story 2.3** (`review`) — unaffected; clarifying note only.
- **Story 2.6** (`review` → `in-progress`) — gains ACs setting `DiscoveryRun.stage=analyzing` at start and completion semantics.
- **Story 2.7** (new) — Business-Oriented Import Progress Display. Added to Epic 2 as `backlog`.

### Artifact Conflicts

- **PRD:** three new FRs — FR-31 (reachability validation), FR-32 (browser tab branding), FR-33 (business-oriented import progress). One-line addition to §6.1 MVP Scope. Epic 2's description in `epics.md` gets a note that the live-feed is no longer user-facing.
- **Architecture:** AD-10 extended with a `DiscoveryRun.stage` field (four values, mapped to fixed percentages client-side — no new stored percentage, no streaming infrastructure). Domain model gains `Application.favicon_url` (nullable, not secrets-managed). Onboarding module gains a synchronous reachability pre-check. No new port, no paradigm change.
- **UX (`EXPERIENCE.md`):** resolves the long-standing `[GAP]` on the "Discovery running" state (open since 2026-07-15) with a confirmed four-stage business-progress design. One-line addition alongside the existing breadcrumb rule (UX-DR16) for tab branding.

### Technical Impact

- No new infrastructure (polling reuses the existing REST read pattern; favicon fetch and reachability check reuse the existing HTTP-tolerance precedent from FR-6(f)).
- Three `review`-status stories (2.1, 2.2, 2.6) require actual rework, not just documentation changes, since they're already implemented — code changes are needed before they can go back through code review.

## 3. Recommended Approach

**Selected: Direct Adjustment** (Option 1 from the Path Forward evaluation) for all three CRs.

- **Rollback (Option 2):** not viable/not needed — no completed work needs reverting; Epic 1's `done` stories (1.1–1.3) are untouched in substance, and Epic 2's `review` stories need extension, not reversal.
- **MVP Review (Option 3):** not needed — none of these CRs change the PRD's MVP boundary or core goals; they're additive/refining.
- **Direct Adjustment:** viable for all three. CR-1 and CR-3 are low effort, low risk, fully contained to Onboarding (Epic 1). CR-2 is medium effort (three `review` stories need rework, one new story), low-to-medium risk (no new architecture pattern, but touches already-implemented code) — still squarely a within-plan adjustment, not a replan.

**Rationale:** All three CRs are refinements to an already-scoped feature area (Application onboarding/import), not new epics or a scope pivot. The only real complexity is that CR-2 asks to walk back a detail (the raw live-feed) that was already built and reviewed — this is called out explicitly in Story 2.2's edit above rather than silently overwritten.

## 4. Detailed Change Proposals

### PRD (`prd.md`)

**New FR-31 — Application reachability validation** (§4.1):
> Platform validates that the submitted Base URL is reachable before creating an Application record or starting discovery. An unreachable URL fails fast with a clear message rather than proceeding.

**New FR-32 — Dynamic browser tab branding** (§4.1):
> Platform auto-fetches the target Application's favicon during onboarding (best-effort, non-blocking) and reflects the Application's name and favicon in the browser tab throughout the pipeline screens.

**New FR-33 — Business-oriented import progress** (§4.2):
> Platform surfaces Discovery Run progress via four business-language stages (Initialization, Authentication, Discovery, Analysis) with fixed percentages. No crawl-specific or otherwise technical terminology is exposed in this view.

**§6.1 MVP Scope** — add one line noting reachability validation, browser tab branding, and staged business-language import progress as in-scope additions.

### Architecture (`ARCHITECTURE-SPINE.md`)

**AD-10 extension — Discovery Run stage tracking:**
> `DiscoveryRun` additionally carries a `stage` field — `initializing | authenticating | discovering | analyzing` — meaningful only while `status=running`:
> - `initializing`: set at `DiscoveryWorkflow` start (Story 2.1)
> - `authenticating`: set once `DiscoveryActivity` begins session establishment (FR-3)
> - `discovering`: set once crawl begins; remains through `ApplicationModelBuilderActivity` (Story 2.5) — Model Builder folds into this stage, not Analysis
> - `analyzing`: set once `InferenceActivity` begins (Story 2.6); `status` flips to `complete` when `InferenceActivity` finishes
>
> `apps/api` exposes `stage` on the existing `DiscoveryRun` read endpoint. The frontend polls this endpoint and maps `stage` to a fixed business-language label + percentage client-side (Initialization 10%, Authentication 25%, Discovery 75%, Analysis 100%) — no new percentage-tracking column; the mapping is presentation-only. No new port, no streaming infrastructure.

**Domain model addition:** `Application.favicon_url` (nullable string — public asset reference, not a credential; does not go through `packages/secrets_client`/AD-5).

**Module Map — Onboarding row:** add note — "gains a synchronous reachability pre-check (HTTP request to Base URL) before Application creation, and a best-effort favicon fetch on success — no new port, no workflow change."

### UX (`EXPERIENCE.md`)

- **Resolves `[GAP]`** in the State Patterns table ("Discovery running / completing") — replace the unconfirmed note with the four-stage business-progress spec (Initialization/Authentication/Discovery/Analysis, fixed percentages, no technical terminology).
- **Information Architecture** — add tab-branding rule alongside the existing breadcrumb rule (UX-DR16): tab title/favicon reflect the current Application on all four pipeline screens, suppressed on Home/Sign In.
- **Voice and Tone** — reachability-failure copy follows the existing fact+why convention (e.g., "Base URL did not respond — confirm it's deployed and accessible before connecting.").

### Stories (`implementation-artifacts/`)

**Story 1.3** — add AC for CR-3 (reachability check gates Application creation) and AC for CR-1 (best-effort favicon fetch on success, non-blocking, stored as `Application.favicon_url`).

**Story 1.6 (new)** — Dynamic Browser Tab Branding: tab title/favicon reflect the current Application across all four pipeline screens; reverts to platform default on Home/Sign In.

**Story 2.1** — add AC: `DiscoveryRun.stage=initializing` set at workflow start.

**Story 2.2** — rewrite AC3: underlying typed-row capture is unchanged; the raw live-feed is no longer user-facing (ownership moves to Story 2.7). Add ACs: `DiscoveryActivity` transitions `stage` to `authenticating` then `discovering` at its natural checkpoints.

**Story 2.3** — no AC change; clarifying note only (completion is what lets `stage` progress out of `discovering`).

**Story 2.6** — add ACs: `stage=analyzing` set at `InferenceActivity` start; `status=complete` at finish (existing AD-10 behavior), understood by the frontend as 100%.

**Story 2.7 (new)** — Business-Oriented Import Progress Display: polls `DiscoveryRun`, maps `stage` to one of four business-language labels with fixed percentages, shows zero technical terminology, defers to the existing re-authentication prompt on `status=failed`/`session_expired`.

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization needed (three `review` stories revert to `in-progress`, two new stories added), but no PRD MVP redefinition, no architecture paradigm change, and no rollback of `done` work.

**Route to: Product Owner / Developer agents**

**Responsibilities:**
- **Product Owner (sprint-status.yaml owner):** revert 2-1, 2-2, 2-6 from `review` to `in-progress`; add 1-6 and 2-7 as `ready-for-dev` (or `backlog`, per your usual convention) in the correct epics.
- **Developer agent (`bmad-dev-story`):** implement the story edits above — Story 1.3's two new ACs, Story 1.6, Story 2.1/2.2/2.6's stage-tracking ACs, Story 2.7 — then route each back through `bmad-code-review`.

**Success criteria:** Connect App fails fast with a clear message on an unreachable URL (CR-3); the browser tab reflects the connected Application's name/favicon across all pipeline screens (CR-1); Discover Journeys' in-progress view shows only Initialization/Authentication/Discovery/Analysis with percentages and zero crawl-specific terminology (CR-2).

**Note:** This proposal, once approved, does **not** by itself edit the PRD/epics.md/architecture/UX files or story files — that happens as a separate, deliberate implementation step (see the routing above), on your timeline.
