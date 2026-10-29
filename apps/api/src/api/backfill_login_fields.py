"""One-off: mark the login fields of Scenarios saved before login fields were
marked (`domain.login_fields`) — the same decision a fresh Scenario gets from
its own source:

- recorded: `extract_recorded_test_data` on the current TestAsset's code;
- Explorer (`grounding.explorer_test`): a saved-credential placeholder value;
- generated: `is_generated_login_field` on the Scenario's name/steps/result.

    python -m api.backfill_login_fields          # dry run (default)
    python -m api.backfill_login_fields --apply

Only adds `"login": true` to a field — never changes a value, a name, the
field order, the code, or any other column. A recorded Scenario whose stored
fields no longer line up with its code (by order and name) is skipped and
reported. `--apply` writes only where `test_data` is unchanged since the dry
run's read. Field values are never printed.
"""

import argparse
import uuid
from dataclasses import dataclass

from domain import Application, Journey, Scenario, TestAsset
from domain.login_fields import is_generated_login_field, is_saved_credential_value
from domain.recorded_test_data import extract_recorded_test_data
from sqlalchemy import cast, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, select

from api.db import engine


@dataclass
class BackfillRow:
    scenario_id: uuid.UUID
    application_name: str
    test_case_number: int
    scenario_name: str
    source: str
    before: list[dict]
    after: list[dict] | None  # None = skipped (recorded fields don't line up)

    @property
    def newly_marked(self) -> list[str]:
        if self.after is None:
            return []
        return [
            new["name"]
            for old, new in zip(self.before, self.after, strict=True)
            if new.get("login") is True and old.get("login") is not True
        ]


def marked_fields(
    test_data: list[dict],
    *,
    source: str,
    is_explorer: bool,
    name: str,
    steps: list[str],
    expected_result: str,
    code: str | None,
) -> list[dict] | None:
    """`test_data` with its login fields marked, or None when a recorded
    Scenario's stored fields no longer line up with its code."""
    if source == "recorded":
        extracted = extract_recorded_test_data(code or "")
        if [f["name"] for f in extracted] != [f["name"] for f in test_data]:
            return None
        flags = [f.get("login") is True for f in extracted]
    elif is_explorer:
        flags = [is_saved_credential_value(f.get("value")) for f in test_data]
    else:
        segments = [name, *steps, expected_result]
        flags = [is_generated_login_field(str(f.get("name")), name, segments) for f in test_data]
    return [
        {**field, "login": True} if flag or field.get("login") is True else dict(field)
        for field, flag in zip(test_data, flags, strict=True)
    ]


def plan_backfill() -> list[BackfillRow]:
    with Session(engine) as session:
        rows = session.exec(
            select(Scenario, Application)
            .join(Journey, Journey.id == Scenario.journey_id)  # type: ignore[arg-type]
            .join(Application, Application.id == Journey.application_id)  # type: ignore[arg-type]
            .where(Scenario.current.is_(True))  # type: ignore[attr-defined]
            .order_by(Application.name, Scenario.test_case_number)  # type: ignore[arg-type]
        ).all()
        plan: list[BackfillRow] = []
        for scenario, application in rows:
            if not scenario.test_data:
                continue
            code = None
            if scenario.source == "recorded":
                asset = session.exec(
                    select(TestAsset).where(
                        TestAsset.scenario_id == scenario.id,
                        TestAsset.current.is_(True),  # type: ignore[attr-defined]
                    )
                ).first()
                code = asset.code if asset else None
            after = marked_fields(
                scenario.test_data,
                source=scenario.source,
                is_explorer=bool((scenario.grounding or {}).get("explorer_test")),
                name=scenario.name,
                steps=scenario.steps,
                expected_result=scenario.expected_result,
                code=code,
            )
            row = BackfillRow(
                scenario_id=scenario.id,
                application_name=application.name,
                test_case_number=scenario.test_case_number,
                scenario_name=scenario.name,
                source=scenario.source,
                before=scenario.test_data,
                after=after,
            )
            if after is None or row.newly_marked:
                plan.append(row)
        return plan


def apply_backfill(rows: list[BackfillRow]) -> int:
    written = 0
    with Session(engine) as session:
        for row in rows:
            if not row.newly_marked:
                continue
            result = session.exec(  # type: ignore[call-overload]
                update(Scenario)
                .where(
                    Scenario.id == row.scenario_id,  # type: ignore[arg-type]
                    Scenario.test_data == cast(row.before, JSONB),  # type: ignore[arg-type]
                )
                .values(test_data=row.after)
            )
            written += result.rowcount
        session.commit()
    return written


def _print_report(rows: list[BackfillRow]) -> None:
    for row in rows:
        header = (
            f"[{row.application_name}] TC-{row.test_case_number:03d} "
            f"{row.scenario_name!r} ({row.source})"
        )
        if row.after is None:
            print(f"{header}: SKIPPED — stored fields no longer match the recorded code")
            continue
        kept = [f["name"] for f in row.after if f.get("login") is not True]
        print(f"{header}")
        print(f"    hide (login): {', '.join(row.newly_marked)}")
        print(f"    stays editable: {', '.join(kept) or '(none)'}")
    marked = sum(1 for r in rows if r.newly_marked)
    skipped = sum(1 for r in rows if r.after is None)
    print(f"\n{marked} scenario(s) would get login fields marked; {skipped} skipped.")


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
