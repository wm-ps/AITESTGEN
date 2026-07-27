---
baseline_commit: 6df2663
---

# Story 2.8: Production Object Storage on AWS S3

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Added 2026-07-24 per `sprint-change-proposal-2026-07-24.md`. Resolves the object-storage backend provider question the architecture explicitly deferred (AD-8, Operational Envelope) — decided as AWS S3 for production. Next available Epic 2 story number.*

## Story

As an operator running AITestGen in production,
I want discovery-evidence binaries (screenshots, DOM snapshots) stored in AWS S3 instead of a self-hosted MinIO deployment,
so that the platform relies on managed, durable cloud storage rather than an in-cluster stateful service we operate ourselves.

## Acceptance Criteria

1. **Given** a production (EKS) deployment, **when** `DiscoveryActivity` persists a screenshot via `object_store.py`, **then** the binary is written to an AWS S3 bucket using the same `put(bytes) -> key` / `get(key) -> bytes` contract Story 2.2 established — no caller (`crawler.py`, `activities.py`) changes. [Source: epics.md#Story 2.8; architecture#AD-8]
2. **Given** the production deployment, **when** the discovery-worker pods are provisioned, **then** the in-cluster `minio` Deployment/Service/PVC (`ops/k8s/04-minio.yaml`) is removed, and `ops/k8s/01-configmap.yaml`/`ops/k8s/08-discovery-worker.yaml` (+ `aitestgen-secrets`) are updated for an S3 bucket + region instead of a MinIO endpoint; the pods authenticate to S3 via EKS Pod Identity (or IRSA, only where Pod Identity isn't available — see Latest Technical Notes) where the cluster supports it, falling back to an access-key pair in `aitestgen-secrets` otherwise. [Source: epics.md#Story 2.8; sprint-change-proposal-2026-07-24.md]
3. **Given** local development or CI, **when** the same `object_store.py` code runs, **then** it continues to target the existing docker-compose MinIO service unchanged (dev ergonomics only, per the architecture's local/production split) — the backend is selected by endpoint/credential configuration, never a code branch the caller sees. [Source: epics.md#Story 2.8; docker-compose.yml header comment]

**Notes (from epics.md):** Local-dev behavior is intentionally out of scope — MinIO in `docker-compose.yml` remains the local/CI substitute (S3 wire-compatible). Only the production (`ops/k8s/`) deployment and its ConfigMap/Secret wiring change.

## Tasks / Subtasks

- [x] Task 1: Add an S3-backed implementation behind `object_store.py`'s existing contract (AC: 1, 3)
  - [x] Added `boto3>=1.43` to `apps/workers/discovery/pyproject.toml`; `uv sync` verified the resolve (`uv.lock` updated).
  - [x] `ObjectStore.__init__` now picks its backend by configuration: `AWS_S3_BUCKET` set → `boto3.client("s3", region_name=AWS_REGION, config=_S3_CONFIG)`; unset (the local dev/CI default, since `docker-compose.yml` never sets it) → the original `Minio(...)` client, byte-for-byte unchanged.
  - [x] `put`/`get` keep their exact original signatures; the S3 branch calls `put_object(Bucket=..., Key=key, Body=data)` / `get_object(Bucket=..., Key=key)["Body"].read()`, same key scheme (`discovery-runs/{discovery_run_id}/{uuid4()}`).
  - [x] Added `_S3_CONFIG = BotoConfig(connect_timeout=5, read_timeout=30)`, mirroring `_HTTP_CLIENT`'s existing MinIO timeout bound, for the same asyncio-offload reason.
  - [x] `activities.py`/`crawler.py`/`session.py` untouched — confirmed via `git status`, no changes outside `object_store.py`, its test, and `pyproject.toml`.
- [x] Task 2: Provision production S3 + IAM (AC: 2) — **bucket + access-key auth path verified against real AWS infrastructure.**
  - [x] Added `ops/scripts/provision-s3-object-storage.sh` — a copy-paste-ready script that creates the bucket (public-access blocked, SSE-S3 encryption on), a least-privilege IAM policy scoped to `s3:GetObject`/`s3:PutObject` on `discovery-runs/*` only, an IAM role trusted by `pods.eks.amazonaws.com`, and the EKS Pod Identity association to the `discovery-worker` ServiceAccount — with a `SKIP_POD_IDENTITY=true` escape hatch for clusters where Pod Identity/IRSA isn't available, printing the same least-privilege policy for a manually-created IAM user instead.
  - [x] Real production bucket exists (operator-provisioned): `wmps-ai-testgen`, `us-east-1`. `ops/k8s/01-configmap.yaml`'s `AWS_S3_BUCKET` updated from the `REPLACE_S3_BUCKET_NAME` placeholder to `wmps-ai-testgen`.
  - [x] Access-key fallback path (option (b), already wired in `ops/k8s/08-discovery-worker.yaml`) verified end-to-end against the real bucket using operator-supplied `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` — see Task 4's round-trip evidence below. Credentials were supplied directly by the operator for this one-time verification and were **not** written to any file in this repo (matches this project's existing convention: secrets are created via `kubectl create secret generic aitestgen-secrets ...`, never committed as YAML). The operator must run that `kubectl create secret` command against the target cluster with these values before the discovery-worker pods can actually authenticate in production — that step requires the live cluster's kubectl context, which this session does not have.
  - [ ] Pod Identity/IRSA (option (a)) was not set up — the operator chose the access-key fallback for this bucket instead, which is a supported, already-implemented path per AC2 ("falling back to an access-key pair ... otherwise"). If Pod Identity/IRSA is wanted instead later, run `provision-s3-object-storage.sh` without `SKIP_POD_IDENTITY`, add a `ServiceAccount` + `serviceAccountName`, and remove the two AWS secret env entries from `ops/k8s/08-discovery-worker.yaml`.
- [x] Task 3: Update k8s manifests (AC: 2)
  - [x] Removed `ops/k8s/04-minio.yaml` in full.
  - [x] `ops/k8s/01-configmap.yaml`: `MINIO_BUCKET`/`MINIO_ENDPOINT` → `AWS_S3_BUCKET` (placeholder)/`AWS_REGION` (`us-east-1` default).
  - [x] `ops/k8s/08-discovery-worker.yaml`: implemented **option (b), the access-key fallback** — `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` `secretKeyRef` entries replaced with `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, with a comment noting Pod Identity/IRSA is preferable and would drop these entries entirely. **Option (a) — an IAM-role-annotated `ServiceAccount` + `serviceAccountName` field — was not added**, since the actual IAM role ARN is Task 2's output and doesn't exist yet; an operator who provisions Pod Identity/IRSA should add the `ServiceAccount` manifest and remove these two secret env entries at that time.
  - [x] Updated the file's header comment: "temporal/postgres/vault/minio" → "temporal/postgres/vault/s3".
- [x] Task 4: Verify (AC: 1, 2, 3 — including real-bucket round trip)
  - [x] Added `apps/workers/discovery/tests/test_object_store.py` — backend-selection unit tests (S3 path and MinIO path), both fully faked, no network. `uv run pytest tests/test_object_store.py` → 2 passed; `ruff check`/`pyright` on the new and changed files → clean.
  - [x] Manual `put`/`get` round-trip against the real `wmps-ai-testgen` bucket, run from this session using the operator-supplied access-key pair as ephemeral environment variables (never written to disk): `ObjectStore()` selected `_backend == "s3"` as expected; `put(b"...", uuid4())` wrote to `discovery-runs/<run_id>/<uuid4>` and returned a key; `get(key)` read back the identical payload. The test object was deleted immediately after (`s3.delete_object`) to avoid leaving test data in the production bucket. This is real-dependency verification against the actual production backend, not a mock.
  - [x] Full existing local/CI suite confirmed green: `uv run --package discovery-worker pytest apps/workers/discovery` → 41 passed, 9 skipped (the skipped tests are the real-dependency integration tests that need a live Postgres/Vault/MinIO stack, not present in this sandbox — expected, matches Story 2.2's own skip convention). `ruff check`/`pyright` across the whole discovery-worker package are clean (3 pre-existing issues remain in untouched files — see Completion Notes). No regression to local dev/CI.

## Dev Notes

- **The entire change is isolated to one module by design.** `object_store.py`'s own docstring (written in Story 2.2) already anticipated this exact swap: "swapping to real S3/GCS/Azure Blob later only touches this module, since they all speak the same object-key model." `crawler.py`, `activities.py`, and `session.py` import and call `ObjectStore`/`put`/`get` but never touch MinIO-specific types — no changes needed there. [Source: apps/workers/discovery/src/discovery_worker/object_store.py — module docstring]
- **`object_store.py` as implemented** (Task 1, complete — see the file itself for the authoritative version): `ObjectStore.__init__` branches on module-level `AWS_S3_BUCKET`. If set, it builds `boto3.client("s3", region_name=AWS_REGION, config=_S3_CONFIG)` and stores it on `self._s3_client`; `self._minio_client` stays `None`. Otherwise it builds the original `Minio(...)` client on `self._minio_client` unchanged (including the `bucket_exists`/`make_bucket` auto-create call — see note below), and `self._s3_client` stays `None`. `self._backend` (`"s3"` or `"minio"`) records which was chosen; `put`/`get` branch on it to call the right client with the right kwargs, asserting the corresponding client is non-`None` first (satisfies pyright without weakening the runtime check). Two separate typed attributes (`_minio_client: Minio | None`, `_s3_client: Any`) were used instead of one polymorphic `_client` — a single shared attribute made pyright infer its type ambiguously across both assignment branches and produced false call-signature errors.
  The `bucket_exists`/`make_bucket` auto-create-on-init behavior stayed MinIO-only, as planned — it is **not** replicated for the S3 path, since production bucket creation belongs in Task 2 (infra provisioning), not in application startup code that would otherwise need `s3:CreateBucket` IAM permission on every pod boot.
- **Why timeouts matter here specifically:** `activities.py` calls `await asyncio.to_thread(ObjectStore)` and offloads `put`/`get` the same way — this is a documented fix for a real incident ("Observed live: this was blocking the crawler's asyncio event loop outright... now off-loaded via `asyncio.to_thread`, a bound still matters so a stuck call frees its thread instead of parking it forever" — `object_store.py` comment). A boto3 client constructed without an explicit `Config(connect_timeout=..., read_timeout=...)` can hang indefinitely on a network blip the same way MinIO's default client did. Don't skip this for the S3 path just because boto3 "usually" has sane defaults — MinIO's http_client "usually" did too, until it didn't.
- **AD-8 / Operational Envelope (architecture):** the object-storage-key *shape* (Postgres holds `Page.object_storage_key`, binaries never stored inline) is a made decision this story does not touch. Only the provider *behind* that key changes. [Source: architecture#AD-8; architecture — Operational Envelope, Deferred section, `[RESOLVED 2026-07-24]`]
- **Local dev is explicitly out of scope.** `docker-compose.yml`'s own header comment: "Local-dev dependencies only... dev ergonomics, NOT the deferred SaaS/on-prem Temporal-hosting or production-infra decision." Its `minio` service block reiterates: "MinIO unblocks the build now and stays swappable for real S3/GCS/Azure Blob later." Do not remove or modify the docker-compose `minio` service.
- **Test-skip pattern to follow:** `apps/workers/discovery/tests/test_discovery_activity_integration.py` already has a `_minio_available()` helper (health-checks `MINIO_ENDPOINT` before running) alongside `_db_available()`/`_vault_available()`, combined into one `pytest.mark.skipif`. Any new S3-specific integration test should follow the same "skip if the real dependency isn't reachable, don't mock it away" convention Story 2.2 established, rather than mocking boto3 in an integration-tier test.
- **`ops/k8s/01-configmap.yaml`** currently holds `MINIO_BUCKET`/`MINIO_ENDPOINT` alongside unrelated config (CORS, AI model, Temporal/Vault addresses, Postgres host — externally hosted, not this story's concern). Only the two MinIO keys change.
- **`ops/k8s/08-discovery-worker.yaml`** currently injects `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` from `aitestgen-secrets` as plain env vars alongside `POSTGRES_PASSWORD`/`VAULT_TOKEN`/`ANTHROPIC_API_KEY` (same pattern). If Pod Identity/IRSA is used instead, no new secret env vars are needed at all — the mechanism is a `serviceAccountName` + IAM trust policy, not a Secret. Don't add unused `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` entries if Pod Identity is actually wired up; only add them for the explicit fallback case (Task 2).

### Project Structure Notes

- Modified: `apps/workers/discovery/src/discovery_worker/object_store.py`, `apps/workers/discovery/pyproject.toml` (+`boto3>=1.43`), `uv.lock`, `ops/k8s/01-configmap.yaml`, `ops/k8s/08-discovery-worker.yaml`.
- New: `apps/workers/discovery/tests/test_object_store.py`.
- Removed: `ops/k8s/04-minio.yaml`.
- New: `ops/scripts/provision-s3-object-storage.sh` — Task 2's provisioning automation (bucket + least-privilege IAM policy + Pod Identity association, with an access-key-fallback path); not yet run against a real AWS account.
- Unchanged (explicitly, by design): `docker-compose.yml`, `apps/workers/discovery/src/discovery_worker/{crawler,session,activities}.py`, `apps/workers/discovery/tests/test_discovery_activity_integration.py`'s existing MinIO-path tests.
- **Not yet created (Task 2, outside this session's reach):** the real S3 bucket, its IAM policy, and either an IRSA/Pod-Identity-annotated `ServiceAccount` manifest or a populated `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` pair in `aitestgen-secrets`. `ops/k8s/01-configmap.yaml`'s `AWS_S3_BUCKET` is a `REPLACE_S3_BUCKET_NAME` placeholder until an operator does this.
- No domain/migration changes — `Page.object_storage_key` is an opaque string column already; nothing about its shape depends on the backend.
- No `apps/api` changes — the API never reads/writes object storage directly (only `discovery_worker` does, per AD-8's writer rules).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.8: Production Object Storage on AWS S3]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-24.md]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md — AD-8, Operational Envelope]
- [Source: apps/workers/discovery/src/discovery_worker/object_store.py — full current implementation]
- [Source: apps/workers/discovery/src/discovery_worker/activities.py:243-251 — `asyncio.to_thread(ObjectStore)` construction, timeout rationale]
- [Source: apps/workers/discovery/tests/test_discovery_activity_integration.py:15,41-52 — `_minio_available()` skip pattern]
- [Source: docker-compose.yml — `minio` service, header comment on local-dev-only scope]
- [Source: ops/k8s/04-minio.yaml, 01-configmap.yaml, 08-discovery-worker.yaml — current MinIO k8s wiring]
- [Source: README.md — K8s Deployment section, secrets/service table]
- [Source: apps/workers/discovery/pyproject.toml — current dependencies, `minio>=7.2`]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — Task 2, original object-storage-abstraction decision and rationale]

## Previous Story Intelligence

Story 2.7 (`review`, the immediately preceding Epic 2 story by file order) is a frontend-only progress-display feature unrelated to object storage — no direct technical carryover. The actually relevant predecessor is **Story 2.2**, which built `object_store.py` in the first place: its Task 2 explicitly recommended MinIO as "this build's concrete, swappable-later adapter" and left the provider undecided at the architecture level on purpose (no formal Protocol port exists for object storage, unlike `AIProvider`/`SecretsClient`/`DeliveryAdapter` — a deliberate omission, not an oversight, per AD-8). This story is that swap being exercised. Story 2.2 also established the "real dependency, not mocked" verification bar (`test_discovery_activity_integration.py` against real Postgres/Vault/MinIO) — Task 4 here holds this story to the same bar for S3.

## Latest Technical Notes

- **boto3**: current stable is in the 1.43.x line as of 2026-07 (production/stable on PyPI, actively released). Pin as `boto3>=1.43` (or the current stable minor at implementation time — verify rather than assuming, per this project's stack-versioning convention).
- **EKS Pod Identity vs. IRSA**: AWS shipped EKS Pod Identity in late 2023 as IRSA's successor, and by 2026 it's the recommended default for new EC2-based EKS clusters — simpler to set up (no OIDC-provider-per-cluster federation, no per-role trust-policy-per-service-account boilerplate) and faster credential delivery. IRSA remains necessary only for scenarios Pod Identity doesn't yet cover (e.g. some Fargate configurations, cross-account role chaining, or older cluster versions) — treat IRSA as the fallback, not the default, when provisioning Task 2's IAM wiring; confirm which the target cluster actually supports before choosing.
- boto3 automatically resolves credentials from whichever mechanism is present (env vars → shared config → container credentials from Pod Identity's webhook-injected token or IRSA's projected service-account token → instance profile) — the application code in Task 1 does not need to know or branch on which one is active; `boto3.client("s3")` with no explicit credentials argument is correct for both.

Sources:
- [How to Implement AWS EKS IRSA](https://oneuptime.com/blog/post/2026-01-30-aws-eks-irsa/view)
- [IAM Roles for Service Accounts (IRSA) on Amazon EKS: Complete Guide](https://computingforgeeks.com/iam-roles-for-service-accounts-irsa-eks-guide/)
- [IAM Roles for Service Accounts - Eksctl User Guide](https://docs.aws.amazon.com/eks/latest/eksctl/iamserviceaccounts.html)
- [boto3 · PyPI](https://pypi.org/project/boto3/)

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

None — no failing runs to debug. `pyright` initially flagged the single-`self._client` design (ambiguous inferred type across the two backend branches); resolved by splitting into `_minio_client`/`_s3_client` typed attributes rather than suppressing the error.

### Completion Notes List

- Tasks 1, 3, and the mockable half of Task 4 are complete and verified (unit tests, `ruff`, `pyright`, and the full existing discovery-worker pytest suite all pass — 41 passed, 9 skipped, 0 regressions).
- Task 2 and the real-bucket half of Task 4 are now **done**: the operator provided the real bucket (`wmps-ai-testgen`, `us-east-1`) and an access-key pair for it directly. `ops/k8s/01-configmap.yaml`'s `AWS_S3_BUCKET` is updated from the placeholder to the real bucket name. A live `put`/`get` round trip through the actual `ObjectStore` S3 code path succeeded against this bucket (backend correctly selected `s3`, payload round-tripped byte-for-byte); the test object was deleted afterward. The access-key credentials were used only as ephemeral environment variables for that one verification run and were never written to any file in this repo.
- **Remaining, genuinely outside this session's reach:** applying `ops/k8s/*.yaml` and running `kubectl create secret generic aitestgen-secrets --from-literal=AWS_ACCESS_KEY_ID=... --from-literal=AWS_SECRET_ACCESS_KEY=...` against the actual live EKS cluster — this session has no kubeconfig/cluster context (verified: no `~/.kube`, no `KUBECONFIG`). This is a routine deploy-time action, consistent with how every other `ops/k8s/` change in this repo's history has been handled (plain commits, no in-repo gate requiring live-cluster application before merge).
- **Security note:** the operator pasted a live AWS secret access key directly into the conversation to enable this verification. That key should be rotated (new key created, old one deleted in IAM) once the target cluster's Secret is created from it, since it now exists in this session's transcript.
- Chose the access-key-pair fallback (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` via `aitestgen-secrets`) over wiring an IAM-role-annotated `ServiceAccount` for Pod Identity/IRSA — this was the operator's actual choice for the real `wmps-ai-testgen` bucket, confirmed working via the Task 4 round trip. Pod Identity/IRSA remains a documented follow-up (`provision-s3-object-storage.sh` without `SKIP_POD_IDENTITY`) if wanted later, with a comment in the manifest pointing at it.
- Status is `review`, not `done` — Task 2 has landed and Task 4's real-bucket verification passed, but applying these manifests + creating the `aitestgen-secrets` Secret on the actual live EKS cluster is still an operator action outside this session's reach (no kubeconfig/cluster context here); `done` should follow once that deploy step happens.
- Local dev/CI is unaffected: `docker-compose.yml`, `AWS_S3_BUCKET` unset by default, MinIO path exercised exactly as before.

### File List

- Modified: `apps/workers/discovery/src/discovery_worker/object_store.py`
- Modified: `apps/workers/discovery/pyproject.toml`
- Modified: `uv.lock`
- New: `apps/workers/discovery/tests/test_object_store.py`
- Modified: `ops/k8s/01-configmap.yaml`
- Modified: `ops/k8s/08-discovery-worker.yaml`
- Removed: `ops/k8s/04-minio.yaml`
- New: `ops/scripts/provision-s3-object-storage.sh`
- Modified: `README.md`
- Modified: `_bmad-output/planning-artifacts/epics.md`
- Modified: `_bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md`
- Modified: `_bmad-output/implementation-artifacts/sprint-status.yaml`
