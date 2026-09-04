"""Schedules feature CRUD + action API. Requires PostgreSQL + Vault +
Temporal reachable, same skip-cleanly convention as `test_test_data_pool.py`.

Unlike Postgres (reset per test via `init_db()`), the docker-compose
Temporal namespace is NOT reset between test runs — every Temporal Schedule
a test creates must be explicitly torn down or it leaks into every
subsequent run (and keeps firing against a database that no longer has the
Application/data it was pointed at). `temporal_schedule_cleanup` tracks and
deletes every schedule id created by a test.

Every Application now gets 3 auto-seeded, disabled default schedules
("Nightly Regression", "Weekly Regression", "Monthly Regression") at
creation time — see `_seed_default_schedules` in `api.main`.
`_create_application` below tracks those for cleanup too, and
`_create_schedule`'s own default test-schedule name is deliberately NOT
"Nightly Regression" (or any of the other two default names), since that
would collide with the auto-seeded row of the same name on every fresh
Application.
"""

import asyncio
import json
import uuid

import hvac
import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from api.temporal_client import get_temporal_client
from domain import Application, TestRun
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from temporalio.client import ScheduleActionStartWorkflow, ScheduleOverlapPolicy
from temporalio.service import RPCError, RPCStatusCode

DEFAULT_SCHEDULE_NAMES = {"Nightly Regression", "Weekly Regression", "Monthly Regression"}


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except (VaultError, OSError):
        return False


def _temporal_available() -> bool:
    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available() and _temporal_available()),
    reason="requires PostgreSQL + Vault + Temporal reachable — start docker compose",
)


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _create_application(client: TestClient, name: str, tracked: list[str]) -> dict:
    """Also registers the 3 auto-seeded default schedules' Temporal ids into
    `tracked`, so `temporal_schedule_cleanup` tears them down too — every
    call site must pass its `temporal_schedule_cleanup` fixture list."""
    response = client.post(
        "/applications",
        json={
            "name": name,
            "url": "https://staging.example.com",
            "environment": "staging",
            "auth_method": "standard_login",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    body = response.json()
    for schedule in client.get(f"/applications/{body['id']}/schedules").json():
        tracked.append(f"app-schedule-{schedule['id']}")
    return body


@pytest.fixture
def temporal_schedule_cleanup():
    """Tracks every Temporal Schedule a test creates and deletes it after —
    see the module docstring for why this is required here (unlike every
    other test file, which only needs `init_db()`)."""
    created: list[str] = []
    yield created

    async def _drop() -> None:
        client = await get_temporal_client()
        for schedule_id in created:
            try:
                await client.get_schedule_handle(schedule_id).delete()
            except RPCError:
                pass

    asyncio.run(_drop())


def _create_schedule(
    client: TestClient, application_id: str, tracked: list[str], **overrides
) -> dict:
    # Deliberately not any of DEFAULT_SCHEDULE_NAMES — every Application
    # already has those 3 (disabled) from creation, so reusing one here
    # would 409 on the partial-unique-index instead of creating a new row.
    payload = dict(
        name="Ad Hoc Regression",
        cadence_type="daily",
        hour=2,
        minute=30,
    )
    payload.update(overrides)
    response = client.post(f"/applications/{application_id}/schedules", json=payload)
    if response.status_code == 201:
        tracked.append(f"app-schedule-{response.json()['id']}")
    return response.json() if response.status_code == 201 else {"__status__": response.status_code, **response.json()}


async def _describe(temporal_schedule_id: str):
    client = await get_temporal_client()
    return await client.get_schedule_handle(temporal_schedule_id).describe()


class TestDefaultSchedules:
    def test_new_application_gets_three_disabled_defaults(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Defaults")
        application = _create_application(client, "Schedule Defaults App", temporal_schedule_cleanup)

        body = client.get(f"/applications/{application['id']}/schedules").json()
        by_name = {s["name"]: s for s in body}

        assert set(by_name) == DEFAULT_SCHEDULE_NAMES
        assert all(s["enabled"] is False for s in by_name.values())
        assert all(s["time_zone"] == "UTC" for s in by_name.values())

        nightly = by_name["Nightly Regression"]
        assert nightly["cadence_type"] == "daily"
        assert (nightly["hour"], nightly["minute"]) == (2, 0)
        assert nightly["cadence_label"] == "Every day at 02:00"

        weekly = by_name["Weekly Regression"]
        assert weekly["cadence_type"] == "weekly"
        assert weekly["days_of_week"] == [1]  # Monday
        assert weekly["cadence_label"] == "Every Mon at 02:00"

        monthly = by_name["Monthly Regression"]
        assert monthly["cadence_type"] == "monthly"
        assert monthly["day_of_month"] == 1
        assert monthly["cadence_label"] == "Day 1 of every month at 02:00"

        # Each default is a real, independently paused Temporal Schedule,
        # not just a DB row claiming enabled=False.
        for schedule in by_name.values():
            description = asyncio.run(_describe(f"app-schedule-{schedule['id']}"))
            assert description.schedule.state.paused is True


class TestCreateSchedule:
    def test_create_daily_schedule(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Create")
        application = _create_application(client, "Schedule Create App", temporal_schedule_cleanup)

        response = client.post(
            f"/applications/{application['id']}/schedules",
            json={
                "name": "Custom Nightly",
                "cadence_type": "daily",
                "hour": 2,
                "minute": 30,
            },
        )

        assert response.status_code == 201
        body = response.json()
        temporal_schedule_cleanup.append(f"app-schedule-{body['id']}")
        assert body["name"] == "Custom Nightly"
        assert body["cadence_type"] == "daily"
        assert body["enabled"] is True
        assert body["cadence_label"] == "Every day at 02:30"
        assert body["next_run_at"] is not None
        # No time_zone in the request — the server stamps its own default
        # unconditionally, same as the auto-seeded schedules.
        assert body["time_zone"] == "UTC"

        description = asyncio.run(_describe(f"app-schedule-{body['id']}"))
        assert description.schedule.policy.overlap is ScheduleOverlapPolicy.SKIP
        action = description.schedule.action
        assert isinstance(action, ScheduleActionStartWorkflow)
        assert action.id == f"scheduled-execution-{body['id']}"
        assert action.task_queue == "execution-task-queue"

    def test_create_weekly_non_contiguous_days_round_trips(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Weekly")
        application = _create_application(client, "Schedule Weekly App", temporal_schedule_cleanup)

        body = _create_schedule(
            client,
            application["id"],
            temporal_schedule_cleanup,
            cadence_type="weekly",
            days_of_week=[1, 4],
        )

        description = asyncio.run(_describe(f"app-schedule-{body['id']}"))
        [calendar] = description.schedule.spec.calendars
        from temporalio.client import ScheduleRange

        assert calendar.day_of_week == (ScheduleRange(1), ScheduleRange(4))

    def test_create_custom_cron_round_trips(self, temporal_schedule_cleanup: list[str]) -> None:
        """Temporal's server normalizes `cron_expressions` into an
        equivalent `ScheduleCalendarSpec` internally — `describe()` returns
        the calendar form with `cron_expressions` empty, confirmed directly
        against this deployment. This is real server behavior (matches
        temporalio's own docstring: cron_expressions "provided for easy
        migration... new uses should use calendars instead"), not something
        our code controls — `build_schedule_spec` still sends
        `cron_expressions` on create, which is the correct way to create a
        custom-cron schedule; this test checks what actually comes back."""
        init_db()
        client = _signed_in_client("Org Schedule Cron")
        application = _create_application(client, "Schedule Cron App", temporal_schedule_cleanup)

        body = _create_schedule(
            client,
            application["id"],
            temporal_schedule_cleanup,
            cadence_type="custom_cron",
            cron_expression="0 2 * * 1-5",
            hour=None,
            minute=None,
        )

        description = asyncio.run(_describe(f"app-schedule-{body['id']}"))
        from temporalio.client import ScheduleRange

        [calendar] = description.schedule.spec.calendars
        assert calendar.hour == (ScheduleRange(2),)
        assert calendar.day_of_week == (ScheduleRange(1, 5),)

    def test_invalid_cron_is_rejected_before_any_side_effect(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Bad Cron")
        application = _create_application(client, "Schedule Bad Cron App", temporal_schedule_cleanup)

        response = client.post(
            f"/applications/{application['id']}/schedules",
            json={
                "name": "Bad Cron",
                "cadence_type": "custom_cron",
                "cron_expression": "not a cron",
            },
        )

        assert response.status_code == 422
        with Session(engine) as session:
            rows = session.exec(select(Application)).all()
            app_row = next(a for a in rows if str(a.external_id) == application["id"])
            from domain import Schedule

            schedules = session.exec(
                select(Schedule).where(Schedule.application_id == app_row.id)
            ).all()
            # Only the 3 auto-seeded defaults exist — the rejected "Bad
            # Cron" attempt left no trace among them.
            assert {s.name for s in schedules} == DEFAULT_SCHEDULE_NAMES

    def test_invalid_time_zone_is_rejected_on_patch(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        """`create_schedule` no longer takes a `time_zone` from the client at
        all (every new schedule gets SCHEDULE_DEFAULT_TIME_ZONE
        unconditionally) — `validate_time_zone`'s HTTP-layer coverage moves
        to the one remaining place a client can still supply one: PATCH."""
        init_db()
        client = _signed_in_client("Org Schedule Bad TZ")
        application = _create_application(client, "Schedule Bad TZ App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        response = client.patch(
            f"/schedules/{created['id']}", json={"time_zone": "Mars/Olympus"}
        )

        assert response.status_code == 422

    def test_duplicate_name_is_rejected(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Dup")
        application = _create_application(client, "Schedule Dup App", temporal_schedule_cleanup)
        _create_schedule(client, application["id"], temporal_schedule_cleanup)

        response = client.post(
            f"/applications/{application['id']}/schedules",
            json={
                "name": "Ad Hoc Regression",
                "cadence_type": "daily",
                "hour": 3,
                "minute": 0,
            },
        )

        assert response.status_code == 409

    def test_name_reusable_after_delete(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Reuse Name")
        application = _create_application(client, "Schedule Reuse Name App", temporal_schedule_cleanup)
        first = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        client.delete(f"/schedules/{first['id']}")

        second = _create_schedule(client, application["id"], temporal_schedule_cleanup)
        assert "__status__" not in second


class TestListSchedules:
    def test_list_returns_created_schedules(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Schedule List")
        application = _create_application(client, "Schedule List App", temporal_schedule_cleanup)
        _create_schedule(client, application["id"], temporal_schedule_cleanup, name="A")
        _create_schedule(client, application["id"], temporal_schedule_cleanup, name="B")

        body = client.get(f"/applications/{application['id']}/schedules").json()
        by_name = {s["name"]: s for s in body}

        # The 3 auto-seeded defaults are present alongside the 2 explicitly
        # created schedules — disabled vs. enabled distinguishes them.
        assert set(by_name) == DEFAULT_SCHEDULE_NAMES | {"A", "B"}
        assert by_name["A"]["enabled"] is True
        assert by_name["B"]["enabled"] is True
        assert by_name["A"]["next_run_at"] is not None
        assert by_name["B"]["next_run_at"] is not None
        for default_name in DEFAULT_SCHEDULE_NAMES:
            assert by_name[default_name]["enabled"] is False


class TestUpdateSchedule:
    def test_patch_name_and_time_propagates_to_temporal(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Patch")
        application = _create_application(client, "Schedule Patch App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        response = client.patch(
            f"/schedules/{created['id']}", json={"name": "Renamed Regression", "hour": 5}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed Regression"
        assert body["hour"] == 5

        description = asyncio.run(_describe(f"app-schedule-{created['id']}"))
        [calendar] = description.schedule.spec.calendars
        from temporalio.client import ScheduleRange

        assert calendar.hour == (ScheduleRange(5),)
        # The rename propagated into the action args too — proves it's
        # rebuilt on every update, not just create. `describe()` returns
        # raw, undeserialized `Payload` protobufs for action args (no data
        # converter applied), so decode the JSON payload directly rather
        # than expecting a reconstructed ScheduledExecutionWorkflowInput.
        action = description.schedule.action
        assert isinstance(action, ScheduleActionStartWorkflow)
        [payload] = action.args
        assert json.loads(payload.data)["schedule_name"] == "Renamed Regression"

    def test_patch_on_disabled_schedule_stays_disabled(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        """The subtlest correctness property in the whole feature: editing a
        paused schedule's cadence must not silently re-enable it."""
        init_db()
        client = _signed_in_client("Org Schedule Patch Disabled")
        application = _create_application(client, "Schedule Patch Disabled App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)
        client.post(f"/schedules/{created['id']}/disable")

        response = client.patch(f"/schedules/{created['id']}", json={"hour": 9})

        assert response.status_code == 200
        assert response.json()["enabled"] is False
        description = asyncio.run(_describe(f"app-schedule-{created['id']}"))
        assert description.schedule.state.paused is True

    def test_patch_after_delete_returns_404_not_502(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Patch Deleted")
        application = _create_application(client, "Schedule Patch Deleted App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)
        assert client.delete(f"/schedules/{created['id']}").status_code == 204

        response = client.patch(f"/schedules/{created['id']}", json={"hour": 9})

        assert response.status_code == 404


class TestEnableDisableSchedule:
    def test_disable_then_enable_round_trip(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Enable Disable")
        application = _create_application(client, "Schedule Enable Disable App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        disabled = client.post(f"/schedules/{created['id']}/disable")
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        description = asyncio.run(_describe(f"app-schedule-{created['id']}"))
        assert description.schedule.state.paused is True

        enabled = client.post(f"/schedules/{created['id']}/enable")
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True
        description = asyncio.run(_describe(f"app-schedule-{created['id']}"))
        assert description.schedule.state.paused is False


class TestDeleteSchedule:
    def test_delete_removes_from_list_and_temporal(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Delete")
        application = _create_application(client, "Schedule Delete App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        response = client.delete(f"/schedules/{created['id']}")

        assert response.status_code == 204
        remaining = {s["name"] for s in client.get(f"/applications/{application['id']}/schedules").json()}
        assert remaining == DEFAULT_SCHEDULE_NAMES
        with pytest.raises(RPCError) as exc_info:
            asyncio.run(_describe(f"app-schedule-{created['id']}"))
        assert exc_info.value.status == RPCStatusCode.NOT_FOUND

        with Session(engine) as session:
            from domain import Schedule

            row = session.exec(
                select(Schedule).where(Schedule.external_id == uuid.UUID(created["id"]))
            ).one()
            assert row.deleted_at is not None

    def test_delete_tolerates_temporal_already_gone(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        """The scenario `handle.delete()`'s NOT_FOUND tolerance actually
        protects: the Temporal Schedule is gone (an operator deleted it
        directly, or a prior request's Temporal delete succeeded but its
        Postgres commit failed — see the create/update compensating-action
        notes) while the Postgres row is still active. `DELETE` must still
        succeed rather than 502. (Calling the API's own DELETE twice in a
        row is a *different* case — the second call 404s via
        `_get_org_schedule`'s own soft-delete filter before ever reaching
        Temporal, which is the correct, expected behavior for a resource
        that's already gone from this API's perspective.)"""
        init_db()
        client = _signed_in_client("Org Schedule Delete Temporal Gone")
        application = _create_application(client, "Schedule Delete Temporal Gone App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        async def _delete_in_temporal_only() -> None:
            temporal_client = await get_temporal_client()
            await temporal_client.get_schedule_handle(f"app-schedule-{created['id']}").delete()

        asyncio.run(_delete_in_temporal_only())

        response = client.delete(f"/schedules/{created['id']}")

        assert response.status_code == 204
        with Session(engine) as session:
            from domain import Schedule

            row = session.exec(
                select(Schedule).where(Schedule.external_id == uuid.UUID(created["id"]))
            ).one()
            assert row.deleted_at is not None


class TestApplicationDeletePausesSchedules:
    def test_deleting_the_application_pauses_every_live_schedule(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org App Delete Pauses Schedules")
        application = _create_application(client, "App Delete Pauses Schedules App", temporal_schedule_cleanup)
        first = _create_schedule(client, application["id"], temporal_schedule_cleanup, name="A")
        second = _create_schedule(client, application["id"], temporal_schedule_cleanup, name="B")

        # delete_application 409s while its DiscoveryRun is "running" — real
        # onboarding eventually completes it via the discovery worker, which
        # isn't running in this test process, so mark it complete directly.
        with Session(engine) as session:
            from domain import DiscoveryRun

            app_row = session.exec(
                select(Application).where(Application.external_id == uuid.UUID(application["id"]))
            ).one()
            discovery_run = session.exec(
                select(DiscoveryRun).where(DiscoveryRun.application_id == app_row.id)
            ).one()
            discovery_run.status = "complete"
            session.add(discovery_run)
            session.commit()

        response = client.delete(f"/applications/{application['id']}")

        assert response.status_code == 204
        for created in (first, second):
            description = asyncio.run(_describe(f"app-schedule-{created['id']}"))
            assert description.schedule.state.paused is True
        with Session(engine) as session:
            from domain import Schedule

            rows = session.exec(
                select(Schedule).where(
                    Schedule.external_id.in_(  # type: ignore[attr-defined]
                        [uuid.UUID(first["id"]), uuid.UUID(second["id"])]
                    )
                )
            ).all()
            assert all(row.enabled is False for row in rows)


class TestRunScheduleNow:
    def test_run_now_conflicts_with_an_in_progress_run(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Schedule Run Now Conflict")
        application = _create_application(client, "Schedule Run Now Conflict App", temporal_schedule_cleanup)
        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        with Session(engine) as session:
            app_row = session.exec(
                select(Application).where(Application.external_id == uuid.UUID(application["id"]))
            ).one()
            session.add(
                TestRun(
                    application_id=app_row.id,
                    run_number=1,
                    status="running",
                    environment_snapshot="staging",
                    target_base_url_snapshot="https://staging.example.com",
                )
            )
            session.commit()

        response = client.post(f"/schedules/{created['id']}/run-now")

        assert response.status_code == 409
        assert response.json()["detail"] == "EXECUTION_IN_PROGRESS"


class TestScheduleOrgScoping:
    def test_other_org_cannot_list_or_create_against_this_application(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        owner_client = _signed_in_client("Org Schedule Scope Owner")
        owner_app = _create_application(owner_client, "Scope Owner App", temporal_schedule_cleanup)
        other_client = _signed_in_client("Org Schedule Scope Other")

        assert other_client.get(f"/applications/{owner_app['id']}/schedules").status_code == 404
        assert (
            other_client.post(
                f"/applications/{owner_app['id']}/schedules",
                json={
                    "name": "Intruder",
                    "cadence_type": "daily",
                    "hour": 2,
                    "minute": 0,
                },
            ).status_code
            == 404
        )

    def test_other_org_cannot_mutate_or_trigger_this_schedule(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        owner_client = _signed_in_client("Org Schedule Scope Owner 2")
        owner_app = _create_application(owner_client, "Scope Owner App 2", temporal_schedule_cleanup)
        created = _create_schedule(owner_client, owner_app["id"], temporal_schedule_cleanup)
        other_client = _signed_in_client("Org Schedule Scope Other 2")

        assert other_client.patch(f"/schedules/{created['id']}", json={"hour": 9}).status_code == 404
        assert other_client.post(f"/schedules/{created['id']}/enable").status_code == 404
        assert other_client.post(f"/schedules/{created['id']}/disable").status_code == 404
        assert other_client.post(f"/schedules/{created['id']}/run-now").status_code == 404
        assert other_client.delete(f"/schedules/{created['id']}").status_code == 404
