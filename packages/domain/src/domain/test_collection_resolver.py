"""Which test cases a test suite (`TestCollection`) runs, resolved now.

Lives in `domain` (not `api`) because three callers need the same answer: the
API (manual run, download, save-time checks), and the execution worker (a
scheduled suite run resolves membership at fire time). One resolver means a
suite's run, download and count can never disagree.
"""

import uuid
from dataclasses import dataclass

from sqlmodel import Session, col, select

from domain.journey import Journey
from domain.scenario import Scenario
from domain.test_asset import TestAsset
from domain.test_collection import TestCollectionMember
from domain.test_suite import TestSuite


@dataclass
class Runnable:
    scenario: Scenario
    asset: TestAsset
    journey: Journey


def runnable_by_scenario(session: Session, application_id: uuid.UUID) -> dict[uuid.UUID, Runnable]:
    """`Scenario.id` -> its runnable test case, for this application. Same
    filter as `list_test_suites` (the Test cases tab), so a suite's counts
    always agree with that tab."""
    rows = session.exec(
        select(TestAsset, Scenario, Journey)
        .join(TestSuite, col(TestSuite.id) == col(TestAsset.test_suite_id))
        .join(Scenario, col(Scenario.id) == col(TestAsset.scenario_id))
        .join(Journey, col(Journey.id) == col(TestSuite.journey_id))
        .where(
            Journey.application_id == application_id,
            Journey.status == "candidate",
            col(TestSuite.current).is_(True),
            col(TestAsset.current).is_(True),
            col(Scenario.current).is_(True),
        )
    ).all()
    result: dict[uuid.UUID, Runnable] = {}
    for asset, scenario, journey in rows:
        result.setdefault(scenario.id, Runnable(scenario, asset, journey))
    return result


def runnable_asset_external_ids(
    session: Session, application_id: uuid.UUID, collection_id: uuid.UUID
) -> list[uuid.UUID]:
    """The `TestAsset.external_id`s of a suite's available members, ordered by
    test case number. Empty when none are runnable — the caller decides what
    that means (the API answers 409; a scheduled run skips)."""
    runnable = runnable_by_scenario(session, application_id)
    member_ids = session.exec(
        select(TestCollectionMember.scenario_id).where(
            TestCollectionMember.collection_id == collection_id
        )
    ).all()
    live = sorted(
        (runnable[sid] for sid in member_ids if sid in runnable),
        key=lambda r: r.scenario.test_case_number,
    )
    return [r.asset.external_id for r in live]
