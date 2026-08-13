"""packages/workflows — Temporal Workflow definitions.

Orchestration only (architecture AD-2): no network calls, no DB access, no
direct browser/LLM/Git calls — only calls to Activities and Workflow-safe
primitives. All I/O lives in apps/workers/* Activities.
"""

from workflows.discovery_workflow import (
    APPLICATION_MODEL_BUILDER_ACTIVITY_NAME,
    DISCOVERY_ACTIVITY_NAME,
    DISCOVERY_TASK_QUEUE,
    INFERENCE_ACTIVITY_NAME,
    ApplicationModelBuilderActivityInput,
    ApplicationModelBuilderActivityOutput,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    DiscoveryWorkflow,
    InferenceActivityInput,
)
from workflows.execution_workflow import (
    DEFAULT_MAX_CONCURRENCY,
    EXECUTE_TEST_ACTIVITY_NAME,
    EXECUTION_TASK_QUEUE,
    FINALIZE_TEST_RUN_ACTIVITY_NAME,
    PREPARE_TEST_RUN_ACTIVITY_NAME,
    ApplicationTestExecutionWorkflow,
    ExecutableTest,
    ExecuteTestActivityInput,
    ExecutionWorkflowInput,
    FinalizeTestRunActivityInput,
    PrepareTestRunActivityInput,
    PrepareTestRunActivityResult,
)
from workflows.generation_workflow import (
    GENERATION_TASK_QUEUE,
    SCENARIO_GENERATION_ACTIVITY_NAME,
    GenerationWorkflow,
    ScenarioGenerationActivityInput,
)
from workflows.suite_generation_workflow import (
    ENSURE_TEST_SUITE_ACTIVITY_NAME,
    PLAYWRIGHT_GENERATION_ACTIVITY_NAME,
    EnsureTestSuiteActivityInput,
    EnsureTestSuiteActivityResult,
    PlaywrightGenerationActivityInput,
    SuiteGenerationWorkflow,
)

__all__ = [
    "APPLICATION_MODEL_BUILDER_ACTIVITY_NAME",
    "DEFAULT_MAX_CONCURRENCY",
    "DISCOVERY_ACTIVITY_NAME",
    "DISCOVERY_TASK_QUEUE",
    "ENSURE_TEST_SUITE_ACTIVITY_NAME",
    "EXECUTE_TEST_ACTIVITY_NAME",
    "EXECUTION_TASK_QUEUE",
    "FINALIZE_TEST_RUN_ACTIVITY_NAME",
    "GENERATION_TASK_QUEUE",
    "INFERENCE_ACTIVITY_NAME",
    "PLAYWRIGHT_GENERATION_ACTIVITY_NAME",
    "PREPARE_TEST_RUN_ACTIVITY_NAME",
    "SCENARIO_GENERATION_ACTIVITY_NAME",
    "ApplicationModelBuilderActivityInput",
    "ApplicationModelBuilderActivityOutput",
    "ApplicationTestExecutionWorkflow",
    "DiscoveryActivityInput",
    "DiscoveryActivityOutput",
    "DiscoveryWorkflow",
    "EnsureTestSuiteActivityInput",
    "EnsureTestSuiteActivityResult",
    "ExecutableTest",
    "ExecuteTestActivityInput",
    "ExecutionWorkflowInput",
    "FinalizeTestRunActivityInput",
    "GenerationWorkflow",
    "InferenceActivityInput",
    "PlaywrightGenerationActivityInput",
    "PrepareTestRunActivityInput",
    "PrepareTestRunActivityResult",
    "ScenarioGenerationActivityInput",
    "SuiteGenerationWorkflow",
]
