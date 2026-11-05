"""Test suites (`api.test_collections`) — user-made named groups of test cases.

Postgres only: every case seeds Journey/Scenario/TestSuite/TestAsset rows
directly. Starting a real run needs Temporal, so the trigger cases here stop at
the checks that happen before it (422/409), and the run-id resolution is tested
as a function.
"""

import uuid

import pytest
from api import test_collections as api_test_collections
from api.db import engine
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import (
    DiscoveryRun,
    Journey,
    Scenario,
    TestAsset,
    TestCollection,
    TestCollectionMember,
    TestResult,
    TestRun,
    TestSuite,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _signed_in_client() -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=f"Org {uuid.uuid4()}", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _create_application(client: TestClient) -> dict:
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


def _seed_cases(application: dict, names: list[str], journey_name: str = "Checkout") -> list[dict]:
    """One Journey with a current TestSuite and one current TestAsset per name.
    Returns `[{scenario_id (external), scenario_pk, asset_pk}]`."""
    out = []
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name=journey_name,
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        suite = TestSuite(
            journey_id=journey.id, name=f"{journey_name} suite", generation_run_id=journey.attempt
        )
        session.add(suite)
        session.flush()
        for number, name in enumerate(names, start=1):
            scenario = Scenario(
                journey_id=journey.id,
                type="happy",
                name=name,
                steps=["step"],
                expected_result="ok",
                test_data=[],
                generation_run_id=journey.attempt,
                test_case_number=number,
            )
            session.add(scenario)
            session.flush()
            asset = TestAsset(scenario_id=scenario.id, test_suite_id=suite.id, code="// spec\n")
            session.add(asset)
            session.flush()
            out.append(
                {
                    "scenario_id": str(scenario.external_id),
                    "scenario_pk": scenario.id,
                    "asset_pk": asset.id,
                }
            )
        session.commit()
    return out


def _create_suite(client: TestClient, application: dict, name: str) -> dict:
    response = client.post(
        f"/applications/{application['id']}/test-collections", json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _save(client: TestClient, suite: dict, add: list[str] = (), remove: list[str] = ()):
    return client.put(
        f"/test-collections/{suite['id']}/members", json={"add": list(add), "remove": list(remove)}
    )


def _seed_run(
    application: dict, suite_id: str | None, *, status: str = "completed", name: str | None = None
):
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        collection_pk = None
        if suite_id is not None:
            collection_pk = session.exec(
                select(TestCollection.id).where(TestCollection.external_id == uuid.UUID(suite_id))
            ).one()
        run = TestRun(
            application_id=discovery_run.application_id,
            run_number=1000 + len(str(uuid.uuid4())) + uuid.uuid4().int % 100000,
            status=status,
            environment_snapshot="staging",
            target_base_url_snapshot="https://staging.example.com",
            suite_name=name,
            test_collection_id=collection_pk,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id, run.external_id


# --- create / rename ------------------------------------------------------------


def test_create_and_list_with_counts() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a", "b", "c"])
    smoke = _create_suite(client, application, "  Smoke ")
    assert smoke["name"] == "Smoke"
    assert _save(client, smoke, add=[c["scenario_id"] for c in cases[:2]]).status_code == 200

    listed = client.get(f"/applications/{application['id']}/test-collections").json()
    assert [
        (s["name"], s["test_case_count"], s["unavailable_count"], s["run_count"]) for s in listed
    ] == [("Smoke", 2, 0, 0)]


def test_duplicate_name_is_rejected_case_insensitively_on_create_and_rename() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    smoke = _create_suite(client, application, "Smoke")
    other = _create_suite(client, application, "Regression")

    dup = client.post(f"/applications/{application['id']}/test-collections", json={"name": "SMOKE"})
    assert dup.status_code == 409
    assert dup.json()["detail"] == "COLLECTION_NAME_TAKEN"
    rename = client.patch(f"/test-collections/{other['id']}", json={"name": "smoke"})
    assert rename.status_code == 409
    # the failed rename changed nothing
    assert client.get(f"/test-collections/{other['id']}").json()["name"] == "Regression"
    assert client.get(f"/test-collections/{smoke['id']}").json()["name"] == "Smoke"


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
def test_invalid_names_are_rejected(name: str) -> None:
    client = _signed_in_client()
    application = _create_application(client)
    response = client.post(
        f"/applications/{application['id']}/test-collections", json={"name": name}
    )
    assert response.status_code == 422


def test_rename_updates_only_this_suites_runs() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    smoke = _create_suite(client, application, "Smoke")
    other = _create_suite(client, application, "Regression")
    suite_run, _ = _seed_run(application, smoke["id"], name="Smoke")
    other_suite_run, _ = _seed_run(application, other["id"], name="Regression")
    selective_run, _ = _seed_run(application, None, name="Smoke")  # hand-named, same text
    full_run, _ = _seed_run(application, None, name=None)

    assert (
        client.patch(f"/test-collections/{smoke['id']}", json={"name": "Smoke v2"}).status_code
        == 200
    )

    with Session(engine) as session:
        names = {
            key: session.get(TestRun, pk).suite_name
            for key, pk in {
                "suite": suite_run,
                "other": other_suite_run,
                "selective": selective_run,
                "full": full_run,
            }.items()
        }
    assert names == {"suite": "Smoke v2", "other": "Regression", "selective": "Smoke", "full": None}


# --- membership -----------------------------------------------------------------


def test_a_test_case_can_be_in_many_suites_and_removal_is_independent() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a", "b"])
    smoke = _create_suite(client, application, "Smoke")
    regression = _create_suite(client, application, "Regression")
    shared = cases[0]["scenario_id"]
    _save(client, smoke, add=[shared])
    _save(client, regression, add=[shared, cases[1]["scenario_id"]])

    picker = {
        c["scenario_id"]: sorted(r["name"] for r in c["in_collections"])
        for c in client.get(f"/applications/{application['id']}/test-collection-cases").json()
    }
    assert picker[shared] == ["Regression", "Smoke"]
    assert picker[cases[1]["scenario_id"]] == ["Regression"]

    assert _save(client, smoke, remove=[shared]).json()["test_case_count"] == 0
    regression_detail = client.get(f"/test-collections/{regression['id']}").json()
    assert {m["scenario_id"] for m in regression_detail["available"]} == {
        c["scenario_id"] for c in cases
    }


def test_adding_twice_is_harmless() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a"])
    smoke = _create_suite(client, application, "Smoke")
    assert _save(client, smoke, add=[cases[0]["scenario_id"]]).json()["test_case_count"] == 1
    assert _save(client, smoke, add=[cases[0]["scenario_id"]]).json()["test_case_count"] == 1


def test_a_bad_id_rejects_the_whole_save_with_no_partial_change() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    other_application = _create_application(client)
    cases = _seed_cases(application, ["a", "b"])
    foreign = _seed_cases(other_application, ["x"])
    smoke = _create_suite(client, application, "Smoke")

    for bad in (str(uuid.uuid4()), foreign[0]["scenario_id"]):
        response = _save(client, smoke, add=[cases[0]["scenario_id"], bad])
        assert response.status_code == 422
    assert client.get(f"/test-collections/{smoke['id']}").json()["test_case_count"] == 0

    both = _save(client, smoke, add=[cases[0]["scenario_id"]], remove=[cases[0]["scenario_id"]])
    assert both.status_code == 422


# --- unavailable cases ----------------------------------------------------------


def test_retired_scenario_becomes_unavailable_and_is_only_removed_explicitly() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["keep", "retire"])
    smoke = _create_suite(client, application, "Smoke")
    _save(client, smoke, add=[c["scenario_id"] for c in cases])

    with Session(engine) as session:  # what Explorer promote's _retire does
        session.get(Scenario, cases[1]["scenario_pk"]).current = False
        session.commit()

    detail = client.get(f"/test-collections/{smoke['id']}").json()
    assert detail["test_case_count"] == 1
    assert [m["name"] for m in detail["unavailable"]] == ["retire"]
    summary = client.get(f"/applications/{application['id']}/test-collections").json()[0]
    assert (summary["test_case_count"], summary["unavailable_count"]) == (1, 1)

    # Saving a diff of available cases never drops the unavailable member.
    _save(client, smoke, add=[], remove=[cases[0]["scenario_id"]])
    assert (
        client.get(f"/test-collections/{smoke['id']}").json()["unavailable"][0]["name"] == "retire"
    )

    cleared = _save(client, smoke, remove=[cases[1]["scenario_id"]])
    assert cleared.json()["unavailable_count"] == 0


# --- delete ---------------------------------------------------------------------


def test_delete_without_runs_leaves_test_cases_alone() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a"])
    smoke = _create_suite(client, application, "Smoke")
    _save(client, smoke, add=[cases[0]["scenario_id"]])

    assert client.delete(f"/test-collections/{smoke['id']}").status_code == 204
    assert client.get(f"/test-collections/{smoke['id']}").status_code == 404
    with Session(engine) as session:
        assert session.get(Scenario, cases[0]["scenario_pk"]).current is True
        assert session.get(TestAsset, cases[0]["asset_pk"]).current is True
        assert not session.exec(select(TestCollectionMember)).all() or all(
            m.scenario_id != cases[0]["scenario_pk"]
            for m in session.exec(select(TestCollectionMember))
        )
    # the name is free again
    assert _create_suite(client, application, "Smoke")["name"] == "Smoke"


def test_delete_with_runs_needs_consent_and_then_removes_only_its_runs(monkeypatch) -> None:
    deleted_prefixes: list[str] = []

    class _FakeStore:
        def delete_prefix(self, prefix: str) -> int:
            deleted_prefixes.append(prefix)
            return 0

    monkeypatch.setattr(api_test_collections, "ObjectStore", _FakeStore)
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a"])
    smoke = _create_suite(client, application, "Smoke")
    other = _create_suite(client, application, "Regression")
    _save(client, smoke, add=[cases[0]["scenario_id"]])
    run_pks = [_seed_run(application, smoke["id"], name="Smoke") for _ in range(3)]
    other_run, _ = _seed_run(application, other["id"], name="Regression")
    with Session(engine) as session:
        session.add(
            TestResult(
                test_run_id=run_pks[0][0],
                test_asset_id=cases[0]["asset_pk"],
                scenario_id=cases[0]["scenario_pk"],
                status="passed",
            )
        )
        session.commit()

    refused = client.delete(f"/test-collections/{smoke['id']}")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "SUITE_HAS_RUNS"
    assert client.get(f"/test-collections/{smoke['id']}").json()["run_count"] == 3

    assert client.delete(f"/test-collections/{smoke['id']}?delete_runs=true").status_code == 204
    with Session(engine) as session:
        assert all(session.get(TestRun, pk) is None for pk, _ in run_pks)
        assert session.get(TestRun, other_run) is not None
        assert session.get(Scenario, cases[0]["scenario_pk"]) is not None
        assert not session.exec(
            select(TestResult).where(TestResult.test_run_id == run_pks[0][0])
        ).all()
    assert sorted(deleted_prefixes) == sorted(f"test-runs/{ext}/" for _, ext in run_pks)


def test_delete_is_refused_while_a_run_is_in_progress() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    smoke = _create_suite(client, application, "Smoke")
    _seed_run(application, smoke["id"], status="running", name="Smoke")

    response = client.delete(f"/test-collections/{smoke['id']}?delete_runs=true")
    assert response.status_code == 409
    assert response.json()["detail"] == "SUITE_RUN_IN_PROGRESS"
    assert client.get(f"/test-collections/{smoke['id']}").status_code == 200


def test_delete_survives_object_store_failure(monkeypatch) -> None:
    class _BrokenStore:
        def delete_prefix(self, prefix: str) -> int:
            raise RuntimeError("storage down")

    monkeypatch.setattr(api_test_collections, "ObjectStore", _BrokenStore)
    client = _signed_in_client()
    application = _create_application(client)
    smoke = _create_suite(client, application, "Smoke")
    _seed_run(application, smoke["id"], name="Smoke")
    assert client.delete(f"/test-collections/{smoke['id']}?delete_runs=true").status_code == 204


# --- trigger --------------------------------------------------------------------


def test_trigger_with_both_selectors_is_rejected() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    smoke = _create_suite(client, application, "Smoke")
    response = client.post(
        f"/applications/{application['id']}/test-runs",
        json={
            "test_collection_id": smoke["id"],
            "test_case_ids": [str(uuid.uuid4())],
            "suite_name": "x",
        },
    )
    assert response.status_code == 422


def test_trigger_with_an_empty_or_all_unavailable_suite_is_a_409_not_a_complete_run() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a"])
    smoke = _create_suite(client, application, "Smoke")

    empty = client.post(
        f"/applications/{application['id']}/test-runs", json={"test_collection_id": smoke["id"]}
    )
    assert empty.status_code == 409
    assert empty.json()["detail"] == "COLLECTION_EMPTY"

    _save(client, smoke, add=[cases[0]["scenario_id"]])
    with Session(engine) as session:
        session.get(Scenario, cases[0]["scenario_pk"]).current = False
        session.commit()
    stale = client.post(
        f"/applications/{application['id']}/test-runs", json={"test_collection_id": smoke["id"]}
    )
    assert stale.status_code == 409


def test_trigger_with_an_unknown_suite_or_another_orgs_suite_is_404() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    other_client = _signed_in_client()
    other_application = _create_application(other_client)
    foreign = _create_suite(other_client, other_application, "Smoke")

    for suite_id in (str(uuid.uuid4()), foreign["id"]):
        response = client.post(
            f"/applications/{application['id']}/test-runs", json={"test_collection_id": suite_id}
        )
        assert response.status_code == 404
    assert client.get(f"/test-collections/{foreign['id']}").status_code == 404
    assert client.delete(f"/test-collections/{foreign['id']}").status_code == 404


def test_resolution_follows_a_heal_to_the_new_test_asset() -> None:
    client = _signed_in_client()
    application = _create_application(client)
    cases = _seed_cases(application, ["a", "b"])
    smoke = _create_suite(client, application, "Smoke")
    _save(client, smoke, add=[c["scenario_id"] for c in cases])

    with Session(engine) as session:  # what supersede_test_asset does on a heal
        old = session.get(TestAsset, cases[0]["asset_pk"])
        old.current = False
        new = TestAsset(
            scenario_id=old.scenario_id, test_suite_id=old.test_suite_id, code="// healed\n"
        )
        session.add(new)
        session.commit()
        session.refresh(new)
        new_external_id = new.external_id
        other_external_id = session.get(TestAsset, cases[1]["asset_pk"]).external_id

        collection = session.exec(
            select(TestCollection).where(TestCollection.external_id == uuid.UUID(smoke["id"]))
        ).one()
        application_row = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        from domain import Application

        app_row = session.get(Application, application_row.application_id)
        ids = api_test_collections.resolve_runnable_asset_ids(session, app_row, collection)

    assert ids == [new_external_id, other_external_id]
