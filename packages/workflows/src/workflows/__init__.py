"""packages/workflows — Temporal Workflow definitions.

Orchestration only (architecture AD-2): no network calls, no DB access, no
direct browser/LLM/Git calls — only calls to Activities and Workflow-safe
primitives. All I/O lives in apps/workers/* Activities.
"""

from workflows.discovery_workflow import (
    DISCOVERY_ACTIVITY_NAME,
    DISCOVERY_TASK_QUEUE,
    INFERENCE_ACTIVITY_NAME,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    DiscoveryWorkflow,
    InferenceActivityInput,
)
from workflows.generation_workflow import GENERATION_TASK_QUEUE, GenerationWorkflow

__all__ = [
    "DISCOVERY_ACTIVITY_NAME",
    "DISCOVERY_TASK_QUEUE",
    "GENERATION_TASK_QUEUE",
    "INFERENCE_ACTIVITY_NAME",
    "DiscoveryActivityInput",
    "DiscoveryActivityOutput",
    "DiscoveryWorkflow",
    "GenerationWorkflow",
    "InferenceActivityInput",
]
