"""Classify every pre-existing `Scenario` row that predates the Run All
Tests feature's `safety_classification` column.

The migration that added the column (`ecb9544baf0b`) defaults every
existing row to `safety_classification='UNKNOWN'` with
`safety_classification_reason=NULL` — and `UNKNOWN` is blocked from
execution unless an `ExecutionPolicy` explicitly permits it. Without this
backfill, every application onboarded before this feature shipped would
see 100% blocked results on its very first "Run All Tests" click, which
reads as a bug, not a safety feature (see the plan's own flagged risk).

`safety_classification_reason IS NULL` is exactly the set of rows this
migration defaulted and nothing has classified since — every row this
codebase's own generation activity classifies always sets a reason too
(see `classify_scenario_steps`), so `reason IS NULL` can never mean
"genuinely classified as UNKNOWN" — only "never classified at all". Safe
to re-run: a row already classified (reason set, by this script or by
generation) is never revisited.

Usage: `uv run python -m api.scripts.backfill_scenario_safety_classification`
"""

from domain import Scenario
from safety_classifier import classify_scenario_steps
from sqlmodel import Session, select

from api.db import engine, init_db


def backfill() -> int:
    init_db()
    updated = 0
    with Session(engine) as session:
        scenarios = session.exec(
            select(Scenario).where(Scenario.safety_classification_reason.is_(None))  # type: ignore[attr-defined]
        ).all()
        for scenario in scenarios:
            classification, reason = classify_scenario_steps(scenario.steps)
            scenario.safety_classification = classification
            scenario.safety_classification_reason = reason
            session.add(scenario)
            updated += 1
        session.commit()
    print(f"classified {updated} pre-existing scenario(s)")
    return updated


if __name__ == "__main__":
    backfill()
