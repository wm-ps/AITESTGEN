# Sprint Change Proposal — Production Object Storage: MinIO → AWS S3

**Date:** 2026-07-24
**Prepared by:** bmad-correct-course workflow, with Harsha
**Mode:** Batch (single-pass proposal, applied directly per explicit instruction)

---

## 1. Issue Summary

Decide the production object-storage backend provider for discovery-evidence binaries (screenshots, DOM snapshots) as **AWS S3**, replacing the assumption that MinIO — Story 2.2's local-dev/CI adapter — would also serve production.

This is not a defect or a reversal of a firm decision. The architecture always treated the *provider* as an open question:

- AD-8 fixes the *shape* (binary artifacts live in object storage, referenced by `Page.object_storage_key`; structured metadata stays in Postgres) but explicitly defers *which* provider backs it.
- The Operational Envelope's "Deferred" list named "the object-storage backend for raw discovery-evidence blobs" outright, coupling it to the still-open SaaS/on-prem topology question.
- `object_store.py`'s own docstring (Story 2.2) frames MinIO as "this build's default adapter; swapping to real S3/GCS/Azure Blob later only touches this module."

This proposal exercises that deferred decision: **AWS S3 for production**, **MinIO unchanged for local dev/CI** (it's explicitly dev-ergonomics-only per `docker-compose.yml`'s own header comment, and is S3-wire-compatible either way).

## 2. Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| **Epic 2** (Runtime Discovery & AI Inference) | Gains new Story 2.8 (Production Object Storage on AWS S3, `backlog`). No existing Epic 2 story (2.1–2.7, all `review`) is reopened — the provider was never part of their acceptance criteria, only the object-storage-key *shape* was (AD-8), which doesn't change. |
| Epics 1, 3, 4 | Not affected. |

### Story Impact

- **Story 2.2** (`review`) — unaffected. Its shipped ACs reference `Page.object_storage_key` and the `put`/`get` contract, never MinIO by name in the acceptance criteria itself; the historical build record (Completion Notes, `docs/EPIC_2_DISCOVERY_PIPELINE.md`) accurately documents what was built at the time (MinIO) and is left as-is — rewriting shipped history to claim S3 was used would misrepresent it.
- **Story 2.8** (new) — Production Object Storage on AWS S3. Added to Epic 2 as `backlog`. Scoped narrowly: swap the production backend behind the existing `object_store.py` contract, retire the in-cluster `minio` k8s manifests, update k8s ConfigMap/Secret wiring for S3 — no change to `crawler.py`/`activities.py` callers, no change to local dev/CI.

### Artifact Conflicts

- **Architecture (`ARCHITECTURE-SPINE.md`):** AD-8's object-storage note and the Operational Envelope's "Deferred" list both updated to mark the provider decision `[RESOLVED 2026-07-24]` — AWS S3 in production, MinIO unchanged locally. No paradigm change, no new port; this is filling in a previously-open blank, not altering a made decision.
- **Epics (`epics.md`):** "Additional Requirements" section's two matching bullets (object-storage split, Deferred list) updated in parallel with the architecture doc; new Story 2.8 added after Story 2.7.
- **PRD:** No change. This is an infrastructure/provider decision below the PRD's requirement level — no FR/NFR references MinIO or S3 by name.
- **UX:** No change. Object storage is entirely backend-internal; nothing user-facing depends on the provider.
- **`sprint-status.yaml`:** New `2-8-production-object-storage-on-aws-s3: backlog` entry added under `epic-2`.
- **`README.md`:** K8s Deployment section updated — the in-cluster `minio` Service/table row is replaced with an external "AWS S3" row (matching the existing Postgres "external, not deployed in-cluster" convention); the secrets list swaps `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` for `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (called out as an IRSA fallback, not the preferred path).
- **Historical build logs left untouched (by design):** `docs/EPIC_2_DISCOVERY_PIPELINE.md` and story files `2-2`, `2-3`, `2-6` under `_bmad-output/implementation-artifacts/` document what was actually built and verified for V1 (against MinIO) — these are point-in-time records, not living specs (the same convention already left `docs/EPIC_2_DISCOVERY_PIPELINE.md`'s superseded `Evidence`-entity references unedited after AD-8's 2026-07-18 rewrite). The resolved decision lives in the architecture spine and epics.md, which *are* living documents.

### Technical Impact (not applied in this pass — see Implementation Handoff)

- `apps/workers/discovery/src/discovery_worker/object_store.py` needs a production code path (boto3 against AWS S3) alongside — or replacing — the current `minio` Python client, selected by configuration, not a branch callers see.
- `ops/k8s/04-minio.yaml` (PVC, Deployment, Service) is retired for production; `ops/k8s/01-configmap.yaml` and `ops/k8s/08-discovery-worker.yaml` need an S3 bucket/region in place of the MinIO endpoint, and IAM (IRSA) wiring in place of — or alongside — the `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` secret pair.
- `docker-compose.yml` is unchanged — local dev/CI keeps the `minio` service.

## 3. Recommended Approach

**Selected: Direct Adjustment** (Option 1 from the Path Forward evaluation) — add one new backlog story within the existing Epic 2 structure; no rollback, no MVP re-scoping.

- **Rollback (Option 2):** not applicable — nothing shipped needs reverting; MinIO in local dev/CI is correct and stays.
- **MVP Review (Option 3):** not needed — this doesn't touch PRD scope, goals, or any FR/NFR.
- **Direct Adjustment:** viable and low-risk. The architecture explicitly anticipated and isolated this exact swap to one module (`object_store.py`) plus its deployment config — effort is low-to-medium (real engineering: IAM/bucket setup, boto3 integration, manifest changes, verification against a real bucket), risk is low (no shape/contract change, no caller changes, local dev unaffected).

**Effort estimate:** Low–Medium. **Risk level:** Low.

## 4. Detailed Change Proposals

### Architecture — `ARCHITECTURE-SPINE.md`

**AD-8 note (object-storage rule bullet):**

- OLD: "...the object-storage backend itself is deferred (Operational Envelope), but the split between structured-columns-in-Postgres and blobs-in-object-storage is decided now."
- NEW: "...`[RESOLVED 2026-07-24]` the object-storage backend is AWS S3 in production (Operational Envelope) — MinIO remains the docker-compose local-dev/CI substitute, unchanged, since both speak the same S3 API and `object_store.py`'s `put`/`get` contract doesn't vary by backend."
- *Rationale: resolves a previously-open blank; doesn't change the AD-8 shape decision itself.*

**Operational Envelope — Deferred list:**

- OLD: "...where Temporal itself runs..., the object-storage backend for raw discovery-evidence blobs (see AD-8 note below), and the production infra/provider choice."
- NEW: object-storage backend removed from the deferred list; a `[RESOLVED 2026-07-24]` note added pointing to this proposal.
- *Rationale: the item is no longer open — leaving it in the Deferred list would contradict the AD-8 update above.*

**Summary list (Key Decisions section):**

- Added a `[RESOLVED 2026-07-24]` clause to the existing "Large binary artifacts... never stored inline in Postgres" bullet, naming AWS S3 (prod) / MinIO (local, unchanged).

*(All three applied — see `ARCHITECTURE-SPINE.md`.)*

### Epics — `epics.md`

- "Additional Requirements" section: the object-storage-split bullet and the Deferred-list bullet both updated in parallel with the architecture doc (same before/after as above).
- New **Story 2.8: Production Object Storage on AWS S3** added after Story 2.7, `[ADDED 2026-07-24]`, `backlog` status — full AC text in `epics.md`.

*(Applied — see `epics.md`.)*

### Backlog tracking — `sprint-status.yaml`

- Added `2-8-production-object-storage-on-aws-s3: backlog` under `epic-2`, with a comment pointing to this proposal.
- `last_updated` bumped to 2026-07-24 with a summary comment; prior 2026-07-21 entry preserved beneath it.

*(Applied — see `sprint-status.yaml`.)*

### Operational documentation — `README.md`

- K8s secrets list: `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` replaced with `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, flagged as the fallback when IRSA isn't used.
- K8s service table: in-cluster `minio` row replaced with an external `s3` (AWS) row, mirroring the existing Postgres "external" convention.
- A short `[UPDATED 2026-07-24]` callout added noting local dev is unaffected.

*(Applied — see `README.md`.)*

### Not changed in this pass (flagged for implementation — see below)

- `apps/workers/discovery/src/discovery_worker/object_store.py`
- `ops/k8s/04-minio.yaml`, `ops/k8s/01-configmap.yaml`, `ops/k8s/08-discovery-worker.yaml`
- `docker-compose.yml` (intentionally unchanged)
- `docs/EPIC_2_DISCOVERY_PIPELINE.md`, and implementation-artifact story files 2-2/2-3/2-6 (intentionally unchanged — historical record)

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization is complete (this proposal), but the actual code/infrastructure swap is real engineering work, not a direct one-shot edit.

- **Product Owner / Developer:** Story 2.8 is ready in the backlog (`epics.md`, `sprint-status.yaml`). Prioritize it whenever production deployment of the object-storage change is needed; no dependency on Epic 2's remaining `review` stories.
- **Developer agent (when Story 2.8 is picked up):**
  1. Add a boto3-backed path to `object_store.py` (or a config-selected client), preserving the existing `put(bytes) -> key` / `get(key) -> bytes` signature — no caller changes.
  2. Provision the production S3 bucket + IAM (prefer IRSA; access-key Secret as fallback).
  3. Update `ops/k8s/01-configmap.yaml` (bucket/region) and `ops/k8s/08-discovery-worker.yaml` (env vars / IRSA service-account annotation); retire `ops/k8s/04-minio.yaml`.
  4. Verify against a real (or test) S3 bucket, matching Story 2.2's original verification bar (real dependency, not mocked).
  5. Leave `docker-compose.yml` and local/CI test setup untouched.

**Success criteria:** Story 2.8 acceptance criteria met; production discovery-evidence writes land in S3; local dev/CI test suite continues passing unmodified against MinIO.

---

## Approval

Approved by Harsha — proceed to apply documentation edits directly (Batch mode, single pass). Applied 2026-07-24.
