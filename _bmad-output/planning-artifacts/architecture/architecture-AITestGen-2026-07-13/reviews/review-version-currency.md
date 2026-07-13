# Adversarial Review — Version Currency & Vendor-Compatibility Assumptions

**Lens:** Was every named technology decision in the Stack table (and the two port abstractions) actually reality-checked, or asserted from training data?
**Reviewed:** `ARCHITECTURE-SPINE.md` Stack table + Design Paradigm + AD-3/AD-4, cross-checked against `.memlog.md`.
**Review date:** 2026-07-13 (same day as spine creation).
**Method:** Independent web search per named technology, done fresh in this review (not reusing the spine's own claims).

## Verdict

Two of the ten Stack entries (Python, PostgreSQL) were genuinely verified with a cited method and are still accurate; the rest were asserted with either intentionally vague phrasing ("current stable") that dodges falsifiability, or a specific-sounding qualifier that is now measurably wrong — TypeScript "current 5.x" is stale by two major versions as of today, and Vite "current 6.x/7.x" is one major version behind a materially different (Rolldown/Oxc-based) 8.0 release. The `DeliveryAdapter` port additionally bakes in an unexamined assumption: Jenkins is not a Git host and has no native PR/commit API, so treating it as a peer of GitHub/GitLab/Azure DevOps under one uniform "create PR or direct commit" interface is a category error the spine never surfaces.

## Findings

### 1. [CRITICAL] TypeScript "current 5.x" is factually wrong as of the spine's own date
The spine (line 122) and memlog (`(version)` line 15) both cite "current 5.x." Independent search shows **TypeScript 7.0 went GA on 2026-07-08** — five days before this spine was written — following **TypeScript 6.0 on 2026-03-23**. As of today, 5.x is two major versions behind current. This isn't a rounding error; it's a specific, checkable claim ("5.x" is a major-version pin) that is simply false on the date the document was authored.
More importantly for AD-6 (OpenAPI-generated types are the *only* frontend/backend contract): TypeScript 7's Go-native compiler **does not ship a stable programmatic/compiler API until 7.1** — tools that depend on the TS compiler API (many OpenAPI-to-TS codegen tools, ts-morph-based generators, custom transformers) are explicitly told to stay on 6.0 via a compatibility package until 7.1 lands. If the intent was "pin to 5.x/6.x deliberately for codegen-tooling compatibility," that's a defensible engineering call — but the spine states it as "current," not "pinned for compatibility," so a reader can't tell whether this was a reasoned choice or an unexamined default. No source is cited either way.
**Action:** Either correct "current 5.x" to name the actual pin reason (tooling compatibility, not currency) or update it and verify AD-6's codegen toolchain against TS 7.

### 2. [HIGH] Vite "current 6.x/7.x" is one major version stale, and the gap isn't cosmetic
Independent search shows **Vite 8.1.4 is current** as of 2026-07-13, with Vite 8 having replaced esbuild/Rollup internals with Rolldown/Oxc — a real toolchain change, not just a version bump, that can affect plugin compatibility. The spine's "6.x/7.x" range was presumably accurate at some earlier point in 2026 but was not re-verified before being written into a document dated today. Given AD-6's reliance on the frontend build/codegen chain, this compounds Finding 1.

### 3. [MEDIUM] `DeliveryAdapter` (AD-4) treats Jenkins as a peer of GitHub/GitLab/Azure DevOps without checking whether that's structurally true
AD-4's rule is "GitHub Actions, GitLab CI, Jenkins, and Azure DevOps are adapter implementations" of one `DeliveryAdapter` interface whose job is "Test Asset -> customer repo (PR or direct commit)." Independent search confirms Jenkins is a CI **orchestrator**, not a Git host: it has no native repository or pull-request API of its own — it checks out and reports back to whatever external SCM (GitHub, Bitbucket, GitLab, etc.) the customer actually uses, via plugins. GitHub, GitLab, and Azure DevOps all bundle CI *and* repo hosting/PR APIs under one product; Jenkins does not. A "Jenkins Adapter" that creates a PR or direct commit therefore has no natural target unless the spine silently assumes every Jenkins customer's actual Git host is also one of the other three — an assumption that is never stated, let alone verified. This is exactly the kind of vendor-compatibility assumption AD-4 exists to make explicit, and it isn't.
**Action:** Either scope AD-4 to "Git-hosting + CI providers" and drop Jenkins as a peer category (replacing it with the actual SCM Jenkins customers use), or add a stated assumption that Jenkins delivery always targets a paired GitHub/GitLab/Bitbucket repo, with the adapter split accordingly.

### 4. [MEDIUM] SQLModel's bus-factor/maintenance risk is absent from the reasoning, despite being publicly documented
The memlog justifies SQLModel as "2026 consensus greenfield pick" with no mention of a well-documented, years-running community concern: SQLModel is maintained essentially by a single maintainer (also the FastAPI author), and has a track record of lagging behind current SQLAlchemy releases and slow PR review. Independent search confirms SQLModel is **not abandoned** (v0.0.39 shipped 2026-06-25, actively released), so the Stack entry itself is fine — but a spine-level architecture decision that names a single-maintainer dependency as load-bearing for the entire `packages/domain` layer should at least acknowledge the bus-factor risk rather than cite generic "consensus," especially when the same maintainer's other project (SQLModel) has previously fallen behind its own dependency (SQLAlchemy) for extended periods.

### 5. [LOW] "current stable" phrasing for FastAPI/SQLModel/Alembic/Temporal SDK is unfalsifiable by design
Four of ten Stack rows use "current stable" / "current GA" instead of a version number. This avoids the staleness trap of Findings 1–2, but it also means no verification actually happened against a specific claim — the memlog's `(version)` line lists these the same way, with no version number or source link recorded, only PostgreSQL and Python got an explicit "(version) Verified via web" note. Independently confirmed as of 2026-07-13: FastAPI (active, monthly releases, ~0.136.x line), SQLModel (v0.0.39, 2026-06-25), Alembic (v1.18.5, 2026-06-25), Temporal Python SDK (active, GA since 2022, release 2026-07-02) are all current and healthy — so the underlying claims hold, but only because this review went and checked; the spine itself gives the reader no way to distinguish "verified vague" from "asserted vague."

### 6. [LOW / informational] Temporal paradigm choice and AI-provider port pattern both hold up under scrutiny
- Temporal remains, per current (2026) industry comparisons, the most production-proven engine for exactly this shape of problem (long-running, retriable, multi-stage, human-gated pipeline) — the memlog's own reasoning (durable/resumable multi-step execution) matches how 2026 sources describe Temporal's differentiated niche versus Airflow/Prefect/Dagster (data-pipeline tools) and versus Inngest/Trigger.dev (lighter-weight, more TS-agentic-loop oriented). No materially better alternative surfaced for this use case.
- The `AIProvider` port pattern (AD-3) is validated by current industry practice — unified-interface LLM abstraction (LiteLLM, Vercel AI SDK Core, etc.) is a well-established 2026 pattern specifically because vendor SDK churn/deprecation is common. This is the one port abstraction where the "unverified vendor SDK compatibility" concern is *not* hiding an unexamined assumption — the pattern is sound and current practice backs it.

## Items Independently Re-Verified As Accurate (no issue)

| Stack entry | Spine claim | Independent check (2026-07-13) |
| --- | --- | --- |
| Python | 3.14.6 | Confirmed latest patch (released 2026-06-10); memlog shows this was actually verified, not asserted. |
| PostgreSQL | 18.4 | Confirmed latest point release (2026-05-14; 18.3 was an out-of-cycle fix on 2026-02-26); native `uuidv7()` claim in Consistency Conventions also confirmed correct — it is a genuine PG18 core function, no extension required. |
| React | 19.x | Confirmed current; latest is 19.2.7, no React 20 yet. |
| Playwright (Python) | 1.57+ | Phrased as a floor, not "current" — technically still satisfied (latest is 1.61.0, 2026-06-29), but the floor itself is now ~2 releases/several months stale, suggesting it wasn't re-checked at spine-authoring time either. Low-severity, not flagged as a separate finding since the "+" hedge makes the claim non-falsifiable. |

## Bottom Line

The spine's own memlog shows exactly two entries (Python, Postgres) with an explicit "(version) Verified via web" trace. Every other Stack row and the paradigm/port decisions were asserted without a recorded verification step. Independent verification in this review found most of them still hold, but two — TypeScript and Vite — are stated with a specific-sounding "current" qualifier that is now wrong, and one port abstraction (DeliveryAdapter/Jenkins) encodes a vendor-compatibility assumption that doesn't survive contact with how Jenkins actually works. The pattern here isn't "everything is wrong" — it's that the spine's confident phrasing doesn't track which claims were checked and which weren't, and the two places that weren't checked happen to be the two that changed most recently.
