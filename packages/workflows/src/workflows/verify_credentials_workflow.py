"""VerifyCredentialsWorkflow — "Start discovery" pre-flight login check.

Before an Application row exists, the Add-application form asks the discovery
worker (the only process with Chromium) to really log in with the entered
username/password, so discovery never starts on credentials that can't sign
in. Same start+poll shape as AutofillScenarioTestDataWorkflow — the browser
login can take over a minute, far too long for one blocking HTTP request.

Workflow id convention: `verify-credentials-{organization_id}-{check_id}` —
org-scoped by construction, so the status route can only ever describe its
own organization's checks.

The activity is deliberately single-attempt: a retried failed login would
count as extra bad attempts against the target app's lockout policy.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.discovery_workflow import DISCOVERY_TASK_QUEUE

VERIFY_CREDENTIALS_ACTIVITY_NAME = "VerifyCredentialsActivity"

# ponytail: worst-case worker budget is ~125s (see credential_check.py's
# phases); these two are sized from that sum, not configurable. Revisit if the
# settle window or navigation retries there change.
VERIFY_CREDENTIALS_START_TO_CLOSE = timedelta(seconds=150)
VERIFY_CREDENTIALS_HEARTBEAT_TIMEOUT = timedelta(seconds=60)


@dataclass
class VerifyCredentialsActivityInput:
    # Temporary Vault path holding {"username", "password"} — never the raw
    # password, so it can't land in Temporal's persisted workflow history.
    secret_ref: str
    url: str
    login_url: str | None = None


@dataclass
class VerifyCredentialsResult:
    status: str  # valid | invalid | uncertain
    detail: str | None = None


@workflow.defn(name="VerifyCredentialsWorkflow")
class VerifyCredentialsWorkflow:
    @workflow.run
    async def run(self, input: VerifyCredentialsActivityInput) -> VerifyCredentialsResult:
        try:
            return await workflow.execute_activity(
                VERIFY_CREDENTIALS_ACTIVITY_NAME,
                input,
                start_to_close_timeout=VERIFY_CREDENTIALS_START_TO_CLOSE,
                heartbeat_timeout=VERIFY_CREDENTIALS_HEARTBEAT_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=1),
                result_type=VerifyCredentialsResult,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the result, not re-raised
            workflow.logger.warning("VerifyCredentialsWorkflow: activity failed: %s", exc)
            return VerifyCredentialsResult(
                status="uncertain",
                detail="Could not complete the login check.",
            )


__all__ = [
    "DISCOVERY_TASK_QUEUE",
    "VERIFY_CREDENTIALS_ACTIVITY_NAME",
    "VERIFY_CREDENTIALS_HEARTBEAT_TIMEOUT",
    "VERIFY_CREDENTIALS_START_TO_CLOSE",
    "VerifyCredentialsActivityInput",
    "VerifyCredentialsResult",
    "VerifyCredentialsWorkflow",
]
