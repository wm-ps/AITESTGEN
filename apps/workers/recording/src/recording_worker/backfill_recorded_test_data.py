"""One-off: give recordings saved before Edit Test Data supported them
their `Scenario.test_data` fields — the same extraction a fresh recording
gets in `persistence.save_recording_sync`.

    python -m recording_worker.backfill_recorded_test_data          # dry run (default)
    python -m recording_worker.backfill_recorded_test_data --apply

Only current `source="recorded"` Scenarios whose `test_data` is still `[]`,
read from their current TestAsset's code. `--apply` writes `test_data` and
nothing else (code, steps and assets are untouched), and only where it is
still `[]` at write time. Password values are never printed.
"""

import argparse
import uuid
from dataclasses import dataclass

from domain import Application, Journey, Scenario, TestAsset
from domain.recorded_test_data import extract_recorded_test_data, find_recorded_inputs
from sqlalchemy import cast, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, select

from recording_worker.db import engine


@dataclass
class BackfillRow:
    scenario_id: uuid.UUID
    application_name: str
    test_case_number: int
    scenario_name: str
    fields: list[dict]
    skipped_passwords: int


def plan_backfill() -> list[BackfillRow]:
    with Session(engine) as session:
        rows = session.exec(
            select(Scenario, TestAsset, Application)
            .join(TestAsset, TestAsset.scenario_id == Scenario.id)  # type: ignore[arg-type]
            .join(Journey, Journey.id == Scenario.journey_id)  # type: ignore[arg-type]
            .join(Application, Application.id == Journey.application_id)  # type: ignore[arg-type]
            .where(
                Scenario.source == "recorded",
                Scenario.current.is_(True),  # type: ignore[attr-defined]
                TestAsset.current.is_(True),  # type: ignore[attr-defined]
            )
            .order_by(Application.name, Scenario.test_case_number)  # type: ignore[arg-type]
        ).all()
        return [
            BackfillRow(
                scenario_id=scenario.id,
                application_name=application.name,
                test_case_number=scenario.test_case_number,
                scenario_name=scenario.name,
                fields=extract_recorded_test_data(asset.code),
                skipped_passwords=sum(1 for i in find_recorded_inputs(asset.code) if i.is_password),
            )
            for scenario, asset, application in rows
            if scenario.test_data == []
        ]


def apply_backfill(rows: list[BackfillRow]) -> int:
    written = 0
    with Session(engine) as session:
        for row in rows:
            if not row.fields:
                continue
            result = session.exec(  # type: ignore[call-overload]
                update(Scenario)
                .where(
                    Scenario.id == row.scenario_id,  # type: ignore[arg-type]
                    Scenario.test_data == cast([], JSONB),  # type: ignore[arg-type]
                )
                .values(test_data=row.fields)
            )
            written += result.rowcount
        session.commit()
    return written


def _print_report(rows: list[BackfillRow]) -> None:
    for row in rows:
        header = f"[{row.application_name}] TC-{row.test_case_number:03d} {row.scenario_name!r}"
        if not row.fields:
            note = (
                f" ({row.skipped_passwords} password field(s) skipped)"
                if row.skipped_passwords
                else ""
            )
            print(f"{header}: no typed values — stays without test data{note}")
            continue
        print(f"{header}: {len(row.fields)} field(s)")
        for f in row.fields:
            print(f"    {f['name']} = {f['value']!r}")
        if row.skipped_passwords:
            print(f"    ({row.skipped_passwords} password field(s) skipped, values not shown)")
    with_fields = sum(1 for r in rows if r.fields)
    print(f"\n{len(rows)} recorded test(s) without test data; {with_fields} would get fields.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write test_data (default: dry run)")
    args = parser.parse_args()

    rows = plan_backfill()
    _print_report(rows)
    if args.apply:
        print(f"Applied: {apply_backfill(rows)} scenario(s) updated.")
    else:
        print("Dry run — nothing written. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
