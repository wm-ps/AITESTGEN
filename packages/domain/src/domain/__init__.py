"""packages/domain — SQLModel entities and their invariants (architecture Structural Seed).

Story 1.1's `ScaffoldProbe` proved the wiring end-to-end and has been
removed now that the real domain model supersedes it (its own docstring
called this out as safe to do). Stories 1.2/1.3 add the real model:
`Organization`, `PlatformUser`, `Application`, `DiscoveryRun`.
"""

from domain.application import Application, AuthMethod
from domain.discovery_run import DiscoveryRun
from domain.organization import Organization
from domain.platform_user import PlatformUser

__all__ = [
    "Application",
    "AuthMethod",
    "DiscoveryRun",
    "Organization",
    "PlatformUser",
]
