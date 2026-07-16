"""packages/domain — SQLModel entities and their invariants (architecture Structural Seed).

Story 1.1 adds only `ScaffoldProbe`, solely to prove the FastAPI + SQLModel +
Alembic + PostgreSQL wiring end-to-end. The real domain model — Organization,
Application, DiscoveryRun, Capability, Journey, Scenario, TestAsset, Evidence —
is NOT built here; it lands in Stories 1.2/1.3 and beyond.
"""

from domain.scaffold_probe import ScaffoldProbe

__all__ = ["ScaffoldProbe"]
