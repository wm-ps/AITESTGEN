"""CleanupWorkflow — daily purge of soft-deleted Applications (AD-2).

Runs once a day (06:00 IST, via a Temporal Schedule created by
`apps/api/src/api/scripts/create_cleanup_schedule.py`), or on demand via
`POST /admin/cleanup/run` — both target execution-worker's task queue, which
also registers this workflow and its two Activities; no dedicated worker
process for a job this light. `Application.deleted_at` has been
soft-delete-only since Story 1.3/AD-15 — nothing ever purged the row, its
~26 dependent tables, its Vault secret, or its S3 objects. This workflow
does, once an Application has been soft-deleted longer than the
admin-configured `delete_project_after` (`DiscoverySettings`) window.

Two Activities, not one: `FindPurgeCandidatesActivity` reads the setting and
lists eligible Application ids; `PurgeApplicationActivity` purges exactly one
Application, re-checking eligibility itself rather than trusting the
candidate list (the setting or the row could change between the two calls —
an irreversible bulk delete must never skip that re-check). One Activity call
per Application, not one giant Activity for all of them, so a single bad row
can't sink the whole run and each purge gets its own Temporal retry/visibility.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow

FIND_PURGE_CANDIDATES_ACTIVITY_NAME = "FindPurgeCandidatesActivity"
PURGE_APPLICATION_ACTIVITY_NAME = "PurgeApplicationActivity"


@dataclass
class PurgeApplicationInput:
    application_id: str  # external_id, same worker-boundary convention as DiscoveryActivityInput


@dataclass
class PurgeApplicationResult:
    application_id: str
    skipped: bool
    rows_deleted: int = 0
    vault_secrets_deleted: int = 0
    s3_objects_deleted: int = 0


@dataclass
class CleanupSummary:
    candidates_found: int
    results: list[PurgeApplicationResult] = field(default_factory=list)


@workflow.defn(name="CleanupWorkflow")
class CleanupWorkflow:
    @workflow.run
    async def run(self) -> CleanupSummary:
        candidate_ids = await workflow.execute_activity(
            FIND_PURGE_CANDIDATES_ACTIVITY_NAME,
            start_to_close_timeout=timedelta(minutes=5),
            result_type=list[str],
        )

        results = []
        for application_id in candidate_ids:
            result = await workflow.execute_activity(
                PURGE_APPLICATION_ACTIVITY_NAME,
                PurgeApplicationInput(application_id=application_id),
                start_to_close_timeout=timedelta(minutes=10),
                result_type=PurgeApplicationResult,
            )
            results.append(result)

        return CleanupSummary(candidates_found=len(candidate_ids), results=results)
