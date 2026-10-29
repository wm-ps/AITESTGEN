"""packages/explorer_core — Vantage Explorer's tables, shared by the API and
the explorer worker. See docs/vantage-explorer/PLAN.md."""

from explorer_core.models import (
    ExplorerAccess,
    ExplorerRole,
    ACTIVE_RUN_STATUSES,
    GOAL_FITS,
    MISSION_STATUSES,
    RUN_STATUSES,
    TEST_KINDS,
    ExplorerEvent,
    ExplorerHealthIssue,
    ExplorerKnowledge,
    ExplorerMission,
    ExplorerQuestion,
    ExplorerRecording,
    ExplorerRun,
    ExplorerScreen,
    ExplorerShot,
    ExplorerTestCase,
    ExplorerTransition,
)

EXPLORER_TASK_QUEUE = "explorer-task-queue"
EXPLORER_WORKFLOW_NAME = "ExplorerRunWorkflow"
# Authoring runs (a user's request) use their own workflow on the same queue.
AUTHORING_WORKFLOW_NAME = "AuthoringRunWorkflow"
BRIEF_CONFIRMED_SIGNAL = "brief_confirmed"
MISSIONS_ADDED_SIGNAL = "missions_added"


def explorer_workflow_id(run_external_id: object) -> str:
    return f"explorer-run-{run_external_id}"


def run_workflow_name(run: ExplorerRun) -> str:
    """The workflow that carries this run: authoring runs have their own."""
    return AUTHORING_WORKFLOW_NAME if run.prompt else EXPLORER_WORKFLOW_NAME


__all__ = [
    "run_workflow_name",
    "ExplorerAccess",
    "ExplorerRole",
    "ACTIVE_RUN_STATUSES",
    "AUTHORING_WORKFLOW_NAME",
    "BRIEF_CONFIRMED_SIGNAL",
    "EXPLORER_TASK_QUEUE",
    "EXPLORER_WORKFLOW_NAME",
    "GOAL_FITS",
    "RUN_STATUSES",
    "ExplorerEvent",
    "ExplorerHealthIssue",
    "ExplorerKnowledge",
    "ExplorerMission",
    "ExplorerQuestion",
    "ExplorerRecording",
    "ExplorerRun",
    "ExplorerScreen",
    "ExplorerShot",
    "ExplorerTestCase",
    "TEST_KINDS",
    "ExplorerTransition",
    "MISSIONS_ADDED_SIGNAL",
    "MISSION_STATUSES",
    "explorer_workflow_id",
]
