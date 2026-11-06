"""Scheduling a test suite and downloading by suite. Same skip-cleanly
convention as `test_schedules.py` (PostgreSQL + Vault + Temporal): the module
reuses its `pytestmark`, and the schedule cases need Temporal because creating
a schedule creates a Temporal Schedule.

`test_collection_id` NULL (no suite) is the application-wide behavior that
existed before; several cases here pin that it stays that way.
"""

import io
import uuid
import zipfile

from api.db import engine, init_db
from domain import Application, Schedule, TestCollection
from sqlmodel import Session, select
from test_schedules import (
    _create_application,
    _create_schedule,
    _signed_in_client,
    pytestmark,  # noqa: F401 — the skip condition
    temporal_schedule_cleanup,  # noqa: F401 — pytest fixture
)
from test_test_collections import _create_suite, _save, _seed_cases


def _specs(response) -> list[str]:
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    return sorted(n for n in zf.namelist() if n.endswith(".spec.ts"))


def _suite_with_cases(client, application, names, suite_name="Smoke", journey="Checkout"):
    cases = _seed_cases(application, names, journey_name=journey)
    suite = _create_suite(client, application, suite_name)
    assert _save(client, suite, add=[c["scenario_id"] for c in cases]).status_code == 200
    return suite, cases


def _plain_application(client) -> dict:
    """An application with no schedule tracking — for cases that never create
    a Temporal Schedule (the 3 seeded ones are disabled and paused)."""
    response = client.post(
        "/applications",
        json={
            "name": f"App {uuid.uuid4()}",
            "url": "https://staging.example.com",
            "environment": "staging",
            "auth_method": "standard_login",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    return response.json()


class TestScheduleWithSuite:
    def test_create_with_suite_and_read_back(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule")
        application = _create_application(client, "Suite Schedule App", temporal_schedule_cleanup)
        suite, _ = _suite_with_cases(client, application, ["Login works", "Cart works"])

        created = _create_schedule(
            client, application["id"], temporal_schedule_cleanup, test_collection_id=suite["id"]
        )

        assert created["test_collection_id"] == suite["id"]
        assert created["test_collection_name"] == "Smoke"
        # The seeded schedules keep running everything.
        listed = client.get(f"/applications/{application['id']}/schedules").json()
        seeded = [s for s in listed if s["id"] != created["id"]]
        assert seeded
        assert all(s["test_collection_id"] is None for s in seeded)
        assert all(s["test_collection_name"] is None for s in seeded)

    def test_without_suite_stays_application_wide(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule Null")
        application = _create_application(client, "Suite Null App", temporal_schedule_cleanup)

        created = _create_schedule(client, application["id"], temporal_schedule_cleanup)

        assert created["test_collection_id"] is None
        assert created["test_collection_name"] is None

    def test_edit_without_the_field_keeps_the_suite_and_null_clears_it(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule Patch")
        application = _create_application(client, "Suite Patch App", temporal_schedule_cleanup)
        suite, _ = _suite_with_cases(client, application, ["Login works"])
        created = _create_schedule(
            client, application["id"], temporal_schedule_cleanup, test_collection_id=suite["id"]
        )

        cadence_only = client.patch(f"/schedules/{created['id']}", json={"hour": 4})
        assert cadence_only.status_code == 200
        assert cadence_only.json()["test_collection_id"] == suite["id"]

        cleared = client.patch(f"/schedules/{created['id']}", json={"test_collection_id": None})
        assert cleared.status_code == 200
        assert cleared.json()["test_collection_id"] is None
        assert cleared.json()["test_collection_name"] is None

    def test_suite_rename_shows_on_the_schedule(self, temporal_schedule_cleanup: list[str]) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule Rename")
        application = _create_application(client, "Suite Rename App", temporal_schedule_cleanup)
        suite, _ = _suite_with_cases(client, application, ["Login works"])
        created = _create_schedule(
            client, application["id"], temporal_schedule_cleanup, test_collection_id=suite["id"]
        )

        renamed = client.patch(f"/test-collections/{suite['id']}", json={"name": "Smoke v2"})
        assert renamed.status_code == 200

        listed = client.get(f"/applications/{application['id']}/schedules").json()
        by_id = {s["id"]: s for s in listed}
        assert by_id[created["id"]]["test_collection_name"] == "Smoke v2"

    def test_empty_suite_is_refused_on_create_and_edit(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule Empty")
        application = _create_application(client, "Suite Empty App", temporal_schedule_cleanup)
        empty = _create_suite(client, application, "Empty")

        refused = _create_schedule(
            client, application["id"], temporal_schedule_cleanup, test_collection_id=empty["id"]
        )
        assert refused["__status__"] == 409
        assert refused["detail"] == "COLLECTION_EMPTY"

        plain = _create_schedule(client, application["id"], temporal_schedule_cleanup)
        edit = client.patch(f"/schedules/{plain['id']}", json={"test_collection_id": empty["id"]})
        assert edit.status_code == 409
        assert edit.json()["detail"] == "COLLECTION_EMPTY"

    def test_unknown_or_other_applications_suite_is_404(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule 404")
        application = _create_application(client, "Suite 404 App A", temporal_schedule_cleanup)
        other = _create_application(client, "Suite 404 App B", temporal_schedule_cleanup)
        foreign, _ = _suite_with_cases(client, other, ["Login works"], suite_name="Foreign")

        for suite_id in (str(uuid.uuid4()), foreign["id"]):
            refused = _create_schedule(
                client, application["id"], temporal_schedule_cleanup, test_collection_id=suite_id
            )
            assert refused["__status__"] == 404

    def test_a_suite_with_a_schedule_cannot_be_deleted(
        self, temporal_schedule_cleanup: list[str]
    ) -> None:
        init_db()
        client = _signed_in_client("Org Suite Schedule Delete")
        application = _create_application(client, "Suite Delete App", temporal_schedule_cleanup)
        suite, _ = _suite_with_cases(client, application, ["Login works"])
        created = _create_schedule(
            client, application["id"], temporal_schedule_cleanup, test_collection_id=suite["id"]
        )

        blocked = client.delete(f"/test-collections/{suite['id']}")
        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "SUITE_HAS_SCHEDULES"
        # `delete_runs` does not override it.
        with_runs = client.delete(f"/test-collections/{suite['id']}", params={"delete_runs": True})
        assert with_runs.status_code == 409

        assert client.delete(f"/schedules/{created['id']}").status_code == 204
        assert client.delete(f"/test-collections/{suite['id']}").status_code == 204


class TestDeleteGuard:
    def test_a_disabled_schedule_still_blocks_the_delete(self) -> None:
        init_db()
        client = _signed_in_client("Org Suite Disabled Schedule")
        application = _plain_application(client)
        suite, _ = _suite_with_cases(client, application, ["Login works"])
        with Session(engine) as session:
            app_row = session.exec(
                select(Application).where(Application.external_id == uuid.UUID(application["id"]))
            ).one()
            collection = session.exec(
                select(TestCollection).where(TestCollection.external_id == uuid.UUID(suite["id"]))
            ).one()
            session.add(
                Schedule(
                    application_id=app_row.id,
                    name="Parked",
                    cadence_type="daily",
                    hour=1,
                    minute=0,
                    time_zone="UTC",
                    enabled=False,
                    temporal_schedule_id=f"app-schedule-{uuid.uuid4()}",
                    test_collection_id=collection.id,
                )
            )
            session.commit()

        blocked = client.delete(f"/test-collections/{suite['id']}")

        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "SUITE_HAS_SCHEDULES"


class TestDownloadBySuite:
    def test_only_the_suites_tests_are_exported(self) -> None:
        init_db()
        client = _signed_in_client("Org Download Suite")
        application = _plain_application(client)
        cases = _seed_cases(application, ["Login works", "Cart works", "Pay works"])
        suite = _create_suite(client, application, "Smoke")
        assert _save(client, suite, add=[cases[0]["scenario_id"]]).status_code == 200
        url = f"/applications/{application['id']}/test-suites/download"

        everything = client.get(url)
        only_suite = client.get(url, params={"test_collection_id": suite["id"]})

        assert everything.status_code == 200
        assert only_suite.status_code == 200
        assert len(_specs(everything)) == 3
        assert len(_specs(only_suite)) == 1
        assert "-smoke.zip" in only_suite.headers["content-disposition"].lower()
        readme = zipfile.ZipFile(io.BytesIO(only_suite.content)).read("README.md").decode()
        assert "**Smoke** test suite" in readme
        full_readme = zipfile.ZipFile(io.BytesIO(everything.content)).read("README.md").decode()
        assert "## Test suite" not in full_readme

    def test_no_suite_is_unchanged_and_byte_identical(self) -> None:
        init_db()
        client = _signed_in_client("Org Download Unchanged")
        application = _plain_application(client)
        _suite_with_cases(client, application, ["Login works", "Cart works"])
        url = f"/applications/{application['id']}/test-suites/download"

        first = client.get(url)
        second = client.get(url)

        assert first.status_code == 200
        assert first.content == second.content

    def test_empty_suite_is_409_and_unknown_suite_is_404(self) -> None:
        init_db()
        client = _signed_in_client("Org Download Refusals")
        application = _plain_application(client)
        _seed_cases(application, ["Login works"])
        empty = _create_suite(client, application, "Empty")
        url = f"/applications/{application['id']}/test-suites/download"

        empty_response = client.get(url, params={"test_collection_id": empty["id"]})
        unknown_response = client.get(url, params={"test_collection_id": str(uuid.uuid4())})

        assert empty_response.status_code == 409
        assert empty_response.json()["detail"] == "COLLECTION_EMPTY"
        assert unknown_response.status_code == 404

    def test_another_applications_suite_is_404(self) -> None:
        init_db()
        client = _signed_in_client("Org Download Foreign")
        application = _plain_application(client)
        other = _plain_application(client)
        foreign, _ = _suite_with_cases(client, other, ["Login works"], suite_name="Foreign")
        _seed_cases(application, ["Cart works"])

        response = client.get(
            f"/applications/{application['id']}/test-suites/download",
            params={"test_collection_id": foreign["id"]},
        )

        assert response.status_code == 404
