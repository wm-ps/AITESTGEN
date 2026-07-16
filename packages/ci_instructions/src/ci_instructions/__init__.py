"""CIInstructionsGenerator port (architecture AD-4 / Module Map).

`[FEATURE REMOVED 2026-07-15]` Same status as `delivery_adapters` — retained
only as a forward-compatible seam, no templates built, no story builds
against it in current scope.
"""

from typing import Any, Literal, Protocol


class CIInstructionsGenerator(Protocol):
    def render(
        self,
        ci_system: Literal["github_actions", "gitlab_ci", "jenkins", "azure_pipelines"],
    ) -> Any:
        """-> InstructionsTemplate (undesigned; not built in V1)."""
        ...
