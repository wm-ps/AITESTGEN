"""DiscoverySettings — global config for the discovery worker.

Singleton (single row, fixed id=1, enforced by a check constraint) since
these settings are global, not per-Application/per-run. Every consumer can
assume the row exists — the migration that creates this table seeds it.
"""

from typing import Literal

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

InteractionLevel = Literal["passive", "normal", "aggressive"]


class DiscoverySettings(SQLModel, table=True):
    __tablename__ = "discovery_settings"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (CheckConstraint("id = 1", name="discovery_settings_singleton"),)

    id: int = Field(default=1, primary_key=True)
    max_pages: int = Field(default=500)
    max_discovery_duration_minutes: int = Field(default=30)
    navigation_timeout_seconds: float = Field(default=15.0)
    # str, not the InteractionLevel Literal — SQLModel can't infer a column
    # type from Literal; the Literal is still the source of truth for callers.
    interaction_level: str = Field(default="normal")
    # Generation-volume caps, for testing cost control. None = unlimited
    # (today's behaviour). Each is a hard stop — generation halts mid-run
    # once hit, rather than refusing upfront or truncating after the fact.
    max_journeys: int | None = Field(default=None)
    max_scenarios_per_journey: int | None = Field(default=None)
    max_test_cases_per_application: int | None = Field(default=None)
