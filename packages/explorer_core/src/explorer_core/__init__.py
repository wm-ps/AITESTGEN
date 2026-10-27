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
BRIEF_CONFIRMED_SIGNAL = "brief_confirmed"
MISSIONS_ADDED_SIGNAL = "missions_added"


def explorer_workflow_id(run_external_id: object) -> str:
    return f"explorer-run-{run_external_id}"


__all__ = [
    "ExplorerAccess",
    "ExplorerRole",
    "ACTIVE_RUN_STATUSES",
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
