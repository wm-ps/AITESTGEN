"""One-off: bring every recording persisted before the `--target
playwright-test` switch / "Recorded tests" bucket up to the current shape.

    python -m recording_worker.convert_legacy_recordings          # dry run (default)
    python -m recording_worker.convert_legacy_recordings --apply

Per Application, in one transaction:
1. Code: each recorded TestAsset still in Codegen's legacy standalone
   format goes through the same `uncomment_codegen_assertions` →
   `normalize_recorded_spec` → `apply_auth_tag` chain a fresh recording does,
   then the real typecheck gate. Only assets that typecheck clean get the
   new code; the rest are reported and left as-is.
2. Grouping: every recorded Scenario/TestAsset sitting in a per-recording
   Journey (`LEGACY_RECORDING_JOURNEY_DESCRIPTION`) moves into the
   Application's single "Recorded tests" Journey/TestSuite. The Scenario
   takes the old Journey's (already-unique) name, and any RecordingSession
   pointing at the old Journey is re-pointed.
3. The now-empty old TestSuite/Journey rows are deleted — only if nothing
   else (scenario/test_asset/journey_step/assertion) still references them;
   otherwise skipped and reported. TestResult rows reference the
   Scenario/TestAsset, which are kept, so run history survives.

The dry run executes the same DB writes and then rolls back, so what it
prints is exactly what `--apply` would commit.
"""

import argparse
import asyncio
import difflib
import uuid
from dataclasses import dataclass, field

from domain import (
    Application,
    Assertion,
    DiscoveryRun,
    Journey,
    JourneyStep,
    RecordingSession,
    Scenario,
    TestAsset,
    TestSuite,
)
from playwright_typecheck import typecheck_playwright_code
from sqlalchemy import func
from sqlmodel import Session, select

from recording_worker.assertion_uncomment import uncomment_codegen_assertions
from recording_worker.auth_tag import apply_auth_tag
from recording_worker.db import engine
from recording_worker.persistence import (
    LEGACY_RECORDING_JOURNEY_DESCRIPTION,
    ensure_test_suite_sync,
    get_or_create_recorded_tests_journey_sync,
)
from recording_worker.spec_normalizer import is_legacy_standalone_script, normalize_recorded_spec


@dataclass
class AssetPlan:
    test_asset_id: uuid.UUID
    application_name: str
    old_journey_name: str
    requires_auth: bool
    old_code: str
    new_code: str | None  # None: already in the current format
    typecheck_errors: list[str] = field(default_factory=list)


@dataclass
class ApplicationReport:
    application_name: str
    moved: list[str] = field(default_factory=list)
    deleted_journeys: list[str] = field(default_factory=list)
    skipped_journeys: list[str] = field(default_factory=list)
    code_updated: list[str] = field(default_factory=list)
    code_skipped: list[str] = field(default_factory=list)


def _recorded_rows(session: Session) -> list[tuple[TestAsset, Scenario, Journey]]:
    return list(
        session.exec(
            select(TestAsset, Scenario, Journey)
            .join(Scenario, Scenario.id == TestAsset.scenario_id)  # type: ignore[arg-type]
            .join(Journey, Journey.id == Scenario.journey_id)  # type: ignore[arg-type]
            .where(Scenario.source == "recorded")
            .order_by(TestAsset.created_at)  # type: ignore[arg-type]
        ).all()
    )


def convert_code(code: str, *, name: str, requires_auth: bool) -> str | None:
    """The new code for a legacy-format recording, or None if it's already
    in the current format."""
    if not is_legacy_standalone_script(code):
        return None
    converted = uncomment_codegen_assertions(code)
    converted = normalize_recorded_spec(converted, name=name, requires_auth=requires_auth)
    return apply_auth_tag(converted, requires_auth)


async def build_asset_plans() -> list[AssetPlan]:
    with Session(engine) as session:
        rows = _recorded_rows(session)
        app_names = {
            a.id: a.name
            for a in session.exec(
                select(Application).where(
                    Application.id.in_({j.application_id for _, _, j in rows})  # type: ignore[attr-defined]
                )
            ).all()
        }
        plans = [
            AssetPlan(
                test_asset_id=asset.id,
                application_name=app_names.get(journey.application_id, "?"),
                old_journey_name=journey.name,
                requires_auth=asset.requires_auth,
                old_code=asset.code,
                new_code=convert_code(
                    asset.code,
                    # Legacy recordings named their Scenario after their own
                    # Journey; that (already-unique) name is what the
                    # Scenario keeps once moved into the shared bucket.
                    name=journey.name
                    if journey.description == LEGACY_RECORDING_JOURNEY_DESCRIPTION
                    else scenario.name,
                    requires_auth=asset.requires_auth,
                ),
            )
            for asset, scenario, journey in rows
        ]
    for plan in plans:
        if plan.new_code is not None:
            plan.typecheck_errors = await typecheck_playwright_code(plan.new_code)
    return plans


def _reference_count(session: Session, model, column, value: uuid.UUID) -> int:
    return session.exec(select(func.count()).select_from(model).where(column == value)).one()


def migrate_application_sync(
    session: Session, application_id: uuid.UUID, plans_by_asset_id: dict[uuid.UUID, AssetPlan]
) -> ApplicationReport:
    """All DB writes for one Application, on the caller's session — the
    caller decides commit (--apply) vs rollback (dry run)."""
    application = session.get(Application, application_id)
    assert application is not None
    report = ApplicationReport(application_name=application.name)

    rows = [r for r in _recorded_rows(session) if r[2].application_id == application_id]
    legacy_journeys = {
        j.id: j for _, _, j in rows if j.description == LEGACY_RECORDING_JOURNEY_DESCRIPTION
    }

    # Code first, independent of grouping.
    for asset, _, journey in rows:
        plan = plans_by_asset_id.get(asset.id)
        if plan is None or plan.new_code is None:
            continue
        if plan.typecheck_errors:
            report.code_skipped.append(f"{journey.name}: {'; '.join(plan.typecheck_errors)}")
            continue
        asset.code = plan.new_code
        session.add(asset)
        report.code_updated.append(journey.name)

    if not legacy_journeys:
        session.flush()
        return report

    recorded_run = session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "recorded")
        .order_by(DiscoveryRun.created_at)  # type: ignore[arg-type]
    ).first()
    assert recorded_run is not None, (
        "legacy recorded journeys exist without a recorded DiscoveryRun"
    )
    bucket = get_or_create_recorded_tests_journey_sync(
        session, application_id=application_id, discovery_run_id=recorded_run.id
    )
    bucket_suite = ensure_test_suite_sync(session, bucket)

    for asset, scenario, journey in rows:
        if journey.id not in legacy_journeys:
            continue
        scenario.journey_id = bucket.id
        scenario.name = journey.name
        asset.test_suite_id = bucket_suite.id
        session.add(scenario)
        session.add(asset)
        report.moved.append(journey.name)

    for recording_session in session.exec(
        select(RecordingSession).where(
            RecordingSession.journey_external_id.in_(  # type: ignore[union-attr]
                [j.external_id for j in legacy_journeys.values()]
            )
        )
    ).all():
        recording_session.journey_external_id = bucket.external_id
        session.add(recording_session)
    session.flush()

    for journey in legacy_journeys.values():
        suites = session.exec(select(TestSuite).where(TestSuite.journey_id == journey.id)).all()
        blockers = {
            "test_asset": sum(
                _reference_count(session, TestAsset, TestAsset.test_suite_id, s.id) for s in suites
            ),
            "scenario": _reference_count(session, Scenario, Scenario.journey_id, journey.id),
            "journey_step": _reference_count(
                session, JourneyStep, JourneyStep.journey_id, journey.id
            ),
            "assertion": _reference_count(session, Assertion, Assertion.journey_id, journey.id),
        }
        remaining = {k: v for k, v in blockers.items() if v}
        if remaining:
            report.skipped_journeys.append(f"{journey.name} (still referenced: {remaining})")
            continue
        for suite in suites:
            session.delete(suite)
        session.flush()
        session.delete(journey)
        session.flush()
        report.deleted_journeys.append(journey.name)

    return report


def _print_plan(plan: AssetPlan) -> None:
    tag = "@auth" if plan.requires_auth else "@public"
    print(f"\n=== {plan.application_name} / {plan.old_journey_name}  [{tag}]")
    print(f"    asset={plan.test_asset_id}")
    if plan.new_code is None:
        print("    code: already in the current format — unchanged")
        return
    print(f"    typecheck: {'OK' if not plan.typecheck_errors else 'FAILED'}")
    for error in plan.typecheck_errors:
        print(f"      {error}")
    print("    --- new code ---")
    for line in plan.new_code.splitlines():
        print(f"    | {line}")
    diff = difflib.unified_diff(
        plan.old_code.splitlines(), plan.new_code.splitlines(), "before", "after", lineterm="", n=1
    )
    print("    --- diff ---")
    for line in diff:
        print(f"    {line}")


def _print_report(report: ApplicationReport) -> None:
    print(f"\n##### {report.application_name}")
    print(f"  code updated ({len(report.code_updated)}): {report.code_updated}")
    print(f"  code skipped ({len(report.code_skipped)}): {report.code_skipped}")
    print(f"  moved into 'Recorded tests' ({len(report.moved)}): {report.moved}")
    print(f"  journeys deleted ({len(report.deleted_journeys)}): {report.deleted_journeys}")
    print(f"  journeys skipped ({len(report.skipped_journeys)}): {report.skipped_journeys}")


async def main(apply: bool) -> None:
    plans = await build_asset_plans()
    for plan in plans:
        _print_plan(plan)

    plans_by_asset_id = {p.test_asset_id: p for p in plans}
    with Session(engine) as session:
        application_ids = sorted({j.application_id for _, _, j in _recorded_rows(session)})
    for application_id in application_ids:
        with Session(engine) as session:
            report = migrate_application_sync(session, application_id, plans_by_asset_id)
            if apply:
                session.commit()
            else:
                session.rollback()
        _print_report(report)

    print("\nAPPLIED." if apply else "\nDRY RUN — nothing committed. Re-run with --apply to write.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="commit the changes (default: dry run)"
    )
    asyncio.run(main(parser.parse_args().apply))
