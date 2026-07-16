"""DeliveryAdapter port (architecture AD-4).

`[FEATURE REMOVED 2026-07-15]` CI/CD delivery (formerly Epic 5) has no
supporting screen in the current UX and is removed from V1 scope in full.
This interface is retained only as a forward-compatible seam — no adapter
implementation (GitHub/GitLab/Azure Repos) is built, and no story builds
against it. Do not read this stub's presence as "CI/CD delivery is in
scope" — see architecture Deferred section.
"""

from typing import Any, Literal, Protocol


class DeliveryAdapter(Protocol):
    def deliver(
        self,
        test_asset: Any,
        application: Any,
        mode: Literal["pr", "direct_commit"],
    ) -> Any:
        """test_asset: TestAsset, application: Application -> DeliveryResult."""
        ...
