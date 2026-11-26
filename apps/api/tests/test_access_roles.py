"""Who can see an application, and as what: private by default, shared by role.

Rows are built straight in the database (no Vault, no Temporal), so these run in
seconds. Needs PostgreSQL only.

* A new application is visible to its adder, the team admins of its team and
  super admins (team applications only) — nobody else, not even by id (404).
* Sharing gives viewer (read only), contributor (run/edit, no settings) or
  app_admin (everything, including sharing).
* A personal application (no team) is private even from a super admin.
* Child rows (journeys, scenarios, activity, credentials, domains) follow the
  application they belong to.
"""

import uuid

import pytest
from api.access import join_default_team
from api.auth import hash_password
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import (
    ActivityEvent,
    Application,
    ApplicationMember,
    DiscoveryRun,
    Journey,
    Organization,
    PlatformUser,
    Scenario,
    Team,
    TeamMember,
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
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="no PostgreSQL reachable at DATABASE_URL — start docker compose to run this test"
)


class World:
    """One organisation with a Default team, people in every position, and
    two applications: `shared` (team application added by A, with a viewer and a
    contributor) and `personal` (no team, added by A)."""

    def __init__(self) -> None:
        init_db()
        suffix = uuid.uuid4().hex[:8]
        self.emails: dict[str, str] = {}
        boss_email = f"boss-{suffix}@example.com"
        seed(email=boss_email, password="pw", org_name=f"Org Access {suffix}", name="Boss")
        self.emails["boss"] = boss_email
        with Session(engine) as session:
            boss = session.exec(select(PlatformUser).where(PlatformUser.email == boss_email)).one()
            self.org_id = boss.organization_id
            self.team_id = session.exec(
                select(Team.id).where(Team.organization_id == self.org_id, Team.is_default)  # type: ignore[arg-type]
            ).one()
            for key, in_team in (("teamadmin", True), ("adder", True), ("outsider", True), ("viewer", True), ("contributor", True), ("loner", False)):
                email = f"{key}-{suffix}@example.com"
                user = PlatformUser(
                    organization_id=self.org_id,
                    email=email,
                    name=key.title(),
                    hashed_password=hash_password("pw"),
                    role="standard_user",
                )
                session.add(user)
                session.flush()
                if in_team:
                    join_default_team(session, user)
                self.emails[key] = email
            session.commit()
            ids = {
                k: session.exec(select(PlatformUser.id).where(PlatformUser.email == e)).one() for k, e in self.emails.items()
            }
            self.ids = ids
            member = session.exec(
                select(TeamMember).where(TeamMember.team_id == self.team_id, TeamMember.user_id == ids["teamadmin"])
            ).one()
            member.role = "team_admin"
            session.add(member)

            self.shared_id = self._application(session, "Shared", self.team_id, ids["adder"])
            self.personal_id = self._application(session, "Personal", None, ids["adder"])
            for key, role in (("viewer", "viewer"), ("contributor", "contributor")):
                session.add(ApplicationMember(application_id=self.shared_id, user_id=ids[key], role=role))
            self.journey_ext, self.scenario_ext = self._journey(session, self.shared_id)
            session.commit()
            self.shared_ext = session.get(Application, self.shared_id).external_id  # type: ignore[union-attr]
            self.personal_ext = session.get(Application, self.personal_id).external_id  # type: ignore[union-attr]
        self.clients = {key: self._login(email) for key, email in self.emails.items()}

    def _application(self, session: Session, name: str, team_id: uuid.UUID | None, adder: uuid.UUID) -> uuid.UUID:
        application = Application(
            organization_id=self.org_id,
            team_id=team_id,
            created_by_id=adder,
            created_by_name="Adder",
            name=f"{name} {uuid.uuid4().hex[:6]}",
            url="https://example.com/",
            environment="staging",
            auth_method="standard_login",
            secret_ref="unused",
            discovery_required=False,
        )
        session.add(application)
        session.flush()
        session.add(ApplicationMember(application_id=application.id, user_id=adder, role="app_admin", granted_by_id=adder))
        return application.id

    def _journey(self, session: Session, application_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        run = DiscoveryRun(application_id=application_id, status="complete")
        session.add(run)
        session.flush()
        journey = Journey(
            application_id=application_id, discovery_run_id=run.id, name="Checkout", identity_key=f"id-{uuid.uuid4()}"
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item"],
            expected_result="Order confirmed",
            test_data=[],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()
        return journey.external_id, scenario.external_id

    @staticmethod
    def _login(email: str) -> TestClient:
        client = TestClient(app)
        assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
        return client


@pytest.fixture(scope="module")
def world() -> World:
    return World()


def _names(client: TestClient) -> set[str]:
    return {a["name"] for a in client.get("/applications").json()}


# --- visibility --------------------------------------------------------------


def test_an_application_is_hidden_from_everyone_it_was_not_shared_with(world: World) -> None:
    path = f"/applications/{world.shared_ext}"
    for who in ("outsider", "loner"):
        assert world.clients[who].get(path).status_code == 404, who
    names = {a["name"] for a in world.clients["outsider"].get("/applications").json()}
    assert not any(n.startswith("Shared") for n in names)


def test_the_adder_team_admin_and_super_admin_see_a_team_application(world: World) -> None:
    path = f"/applications/{world.shared_ext}"
    expected = {"adder": "app_admin", "teamadmin": "app_admin", "boss": "app_admin", "viewer": "viewer", "contributor": "contributor"}
    for who, role in expected.items():
        response = world.clients[who].get(path)
        assert response.status_code == 200, (who, response.text)
        assert response.json()["my_role"] == role, who


def test_lists_only_contain_visible_applications(world: World) -> None:
    for who in ("adder", "viewer", "contributor", "teamadmin", "boss"):
        assert any(n.startswith("Shared") for n in _names(world.clients[who])), who
    assert not any(n.startswith("Shared") for n in _names(world.clients["outsider"]))
    stats = world.clients["outsider"].get("/overview-stats")
    assert stats.status_code == 200


def test_a_personal_application_is_private_even_from_a_super_admin(world: World) -> None:
    path = f"/applications/{world.personal_ext}"
    assert world.clients["adder"].get(path).status_code == 200
    for who in ("boss", "teamadmin", "outsider"):
        assert world.clients[who].get(path).status_code == 404, who
        assert not any(n.startswith("Personal") for n in _names(world.clients[who])), who


def test_another_organisation_sees_nothing(world: World) -> None:
    init_db()
    email = f"other-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=f"Org Access Other {uuid.uuid4().hex[:6]}", name="Other")
    other = World._login(email)
    assert other.get(f"/applications/{world.shared_ext}").status_code == 404
    assert other.get(f"/applications/{world.shared_ext}/access").status_code == 404


# --- child rows follow the application ---------------------------------------


def test_child_rows_are_reachable_only_through_access_to_their_application(world: World) -> None:
    steps = f"/journeys/{world.journey_ext}/steps"
    assert world.clients["outsider"].get(steps).status_code == 404
    assert world.clients["loner"].get(steps).status_code == 404
    for who in ("viewer", "contributor", "adder", "teamadmin", "boss"):
        assert world.clients[who].get(steps).status_code == 200, who


def test_a_viewer_cannot_change_child_rows_but_a_contributor_can(world: World) -> None:
    rename = f"/journeys/{world.journey_ext}"
    delete_scenario = f"/scenarios/{world.scenario_ext}"
    assert world.clients["viewer"].patch(rename, json={"name": "Nope"}).status_code == 403
    assert world.clients["viewer"].delete(delete_scenario).status_code == 403
    assert world.clients["outsider"].patch(rename, json={"name": "Nope"}).status_code == 404
    assert world.clients["outsider"].delete(delete_scenario).status_code == 404
    renamed = world.clients["contributor"].patch(rename, json={"name": "Checkout flow"})
    assert renamed.status_code == 200, renamed.text


def test_only_application_admins_change_application_settings(world: World) -> None:
    path = f"/applications/{world.shared_ext}/generation-settings"
    current = world.clients["adder"].get(path).json()
    for who in ("viewer", "contributor"):
        assert world.clients[who].get(path).status_code == 200, who  # readable
        assert world.clients[who].put(path, json=current).status_code == 403, who
    assert world.clients["outsider"].get(path).status_code == 404
    for who in ("adder", "teamadmin", "boss"):
        assert world.clients[who].put(path, json=current).status_code == 200, who


def test_rename_and_delete_need_an_application_admin(world: World) -> None:
    path = f"/applications/{world.shared_ext}"
    for who in ("viewer", "contributor"):
        assert world.clients[who].patch(path, json={"name": "Nope"}).status_code == 403, who
        assert world.clients[who].delete(path).status_code == 403, who
    assert world.clients["outsider"].delete(path).status_code == 404


class _FakeVault:
    """The rows here point at no real secret; the list only needs one to resolve."""

    def resolve(self, _ref: object) -> bytes:
        return b'{"username": "qa", "password": "pw"}'


def test_saved_credentials_are_listed_and_revealed_only_for_applications_you_administer(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("api.main.VaultSecretsClient", _FakeVault)

    def listed(who: str) -> set[str]:
        return {c["application_name"] for c in world.clients[who].get("/credentials").json()}

    assert any(n.startswith("Shared") for n in listed("adder"))
    assert any(n.startswith("Shared") for n in listed("boss"))
    assert any(n.startswith("Shared") for n in listed("teamadmin"))
    assert not any(n.startswith("Shared") for n in listed("contributor"))
    assert not any(n.startswith("Shared") for n in listed("viewer"))
    assert not any(n.startswith("Personal") for n in listed("boss"))  # personal stays private
    reveal = f"/credentials/{world.shared_ext}/reveal"
    assert world.clients["contributor"].post(reveal).status_code == 403
    assert world.clients["outsider"].post(reveal).status_code == 404


def test_activity_never_shows_a_personal_application_to_a_super_admin(world: World) -> None:
    name = f"Private {uuid.uuid4().hex[:6]}"
    with Session(engine) as session:
        session.add(
            ActivityEvent(
                organization_id=world.org_id,
                application_id=world.personal_id,
                application_name=name,
                actor_name="Adder",
                category="settings",
                outcome="changed",
                summary=f"Renamed {name}",
                details={},
            )
        )
        session.commit()
    summaries = [i["summary"] for i in world.clients["boss"].get("/activity", params={"category": "settings"}).json()["items"]]
    assert not any(name in s for s in summaries)


def test_domains_list_names_only_visible_applications(world: World) -> None:
    domains = world.clients["boss"].post("/domains", json={"host": "example.com"})
    assert domains.status_code in (201, 409)
    seen = world.clients["boss"].get("/domains").json()
    used = {a["name"] for d in seen for a in d["applications"]}
    assert not any(n.startswith("Personal") for n in used)


# --- sharing -----------------------------------------------------------------


def _fresh_application(world: World) -> tuple[uuid.UUID, str]:
    """A team application added by `adder` that nobody else has been given."""
    with Session(engine) as session:
        application_id = world._application(session, "Fresh", world.team_id, world.ids["adder"])
        session.commit()
        return application_id, str(session.get(Application, application_id).external_id)  # type: ignore[union-attr]


def test_sharing_gives_access_changes_the_role_and_removes_it(world: World) -> None:
    _, ext = _fresh_application(world)
    access = f"/applications/{ext}/access"
    assert world.clients["outsider"].get(f"/applications/{ext}").status_code == 404

    shared = world.clients["adder"].post(access, json={"email": world.emails["outsider"]})
    assert shared.status_code == 201, shared.text
    assert shared.json()["role"] == "viewer"  # the default is the least privilege
    assert world.clients["outsider"].get(f"/applications/{ext}").json()["my_role"] == "viewer"

    changed = world.clients["adder"].patch(f"{access}/{world.emails['outsider']}", json={"role": "contributor"})
    assert changed.status_code == 200
    assert world.clients["outsider"].get(f"/applications/{ext}").json()["my_role"] == "contributor"

    assert world.clients["adder"].delete(f"{access}/{world.emails['outsider']}").status_code == 204
    assert world.clients["outsider"].get(f"/applications/{ext}").status_code == 404


def test_the_access_list_puts_the_adder_and_team_admins_first_and_locked(world: World) -> None:
    _, ext = _fresh_application(world)
    world.clients["adder"].post(f"/applications/{ext}/access", json={"email": world.emails["viewer"], "role": "viewer"})
    rows = world.clients["adder"].get(f"/applications/{ext}/access").json()
    assert [(r["email"], r["locked"], r["reason"]) for r in rows[:2]] == [
        (world.emails["adder"], True, "Added by"),
        (world.emails["teamadmin"], True, "Team Admin"),
    ]
    # Super Admins hold admin on team applications: locked rows, after the team admins.
    assert (rows[2]["email"], rows[2]["locked"], rows[2]["reason"]) == (world.emails["boss"], True, "Super Admin")
    assert rows[3]["email"] == world.emails["viewer"] and rows[3]["locked"] is False


def test_sharing_rules(world: World) -> None:
    _, ext = _fresh_application(world)
    access = f"/applications/{ext}/access"
    adder = world.clients["adder"]
    # Locked people already have full access and can't be edited or removed.
    for locked in ("adder", "teamadmin", "boss"):
        assert adder.post(access, json={"email": world.emails[locked]}).status_code == 409, locked
    assert adder.patch(f"{access}/{world.emails['adder']}", json={"role": "viewer"}).status_code in (404, 409)
    assert adder.delete(f"{access}/{world.emails['adder']}").status_code in (404, 409)
    # A team application can only be shared with people in its team.
    assert adder.post(access, json={"email": world.emails["loner"]}).status_code == 404
    assert adder.post(access, json={"email": "nobody@example.com"}).status_code == 404
    # Valid roles only; no double sharing.
    assert adder.post(access, json={"email": world.emails["outsider"], "role": "owner"}).status_code == 422
    assert adder.post(access, json={"email": world.emails["outsider"]}).status_code == 201
    assert adder.post(access, json={"email": world.emails["outsider"]}).status_code == 409


def test_only_application_admins_can_manage_access(world: World) -> None:
    _, ext = _fresh_application(world)
    access = f"/applications/{ext}/access"
    world.clients["adder"].post(access, json={"email": world.emails["viewer"], "role": "viewer"})
    world.clients["adder"].post(access, json={"email": world.emails["contributor"], "role": "contributor"})
    for who in ("viewer", "contributor"):
        assert world.clients[who].get(access).status_code == 403, who
        assert world.clients[who].post(access, json={"email": world.emails["outsider"]}).status_code == 403, who
    assert world.clients["outsider"].get(access).status_code == 404
    # A person promoted to app_admin can then share.
    world.clients["adder"].patch(f"{access}/{world.emails['contributor']}", json={"role": "app_admin"})
    assert world.clients["contributor"].post(access, json={"email": world.emails["outsider"]}).status_code == 201


def test_a_personal_application_can_be_shared_with_anyone_in_the_organisation(world: World) -> None:
    access = f"/applications/{world.personal_ext}/access"
    shared = world.clients["adder"].post(access, json={"email": world.emails["loner"], "role": "contributor"})
    assert shared.status_code == 201, shared.text
    assert world.clients["loner"].get(f"/applications/{world.personal_ext}").json()["my_role"] == "contributor"
    # The super admin still cannot see it.
    assert world.clients["boss"].get(f"/applications/{world.personal_ext}").status_code == 404
    world.clients["adder"].delete(f"{access}/{world.emails['loner']}")


def test_candidates_are_team_members_without_access(world: World) -> None:
    _, ext = _fresh_application(world)
    path = f"/applications/{ext}/access/candidates"
    found = world.clients["adder"].get(path, params={"q": "outs"}).json()
    assert [c["email"] for c in found] == [world.emails["outsider"]]
    assert world.clients["adder"].get(path, params={"q": "adder"}).json() == []  # already has access
    assert world.clients["adder"].get(path, params={"q": "loner"}).json() == []  # not in the team
    assert world.clients["viewer"].get(path, params={"q": "outs"}).status_code == 404  # no access at all
    world.clients["adder"].post(f"/applications/{ext}/access", json={"email": world.emails["viewer"], "role": "viewer"})
    assert world.clients["viewer"].get(path, params={"q": "outs"}).status_code == 403  # a viewer can't manage access
    assert world.clients["adder"].get(path, params={"q": ""}).status_code == 422


def test_removing_a_user_from_the_team_is_not_possible_yet_but_roles_stay_org_level(world: World) -> None:
    # The organisation roles are only super_admin and standard_user.
    for key in ("adder", "viewer"):
        assert world.clients["boss"].patch(f"/team/{world.emails[key]}/role", json={"role": "viewer"}).status_code == 422


def test_access_rows_cascade_when_an_application_is_deleted(world: World) -> None:
    application_id, ext = _fresh_application(world)
    assert world.clients["adder"].delete(f"/applications/{ext}").status_code == 204
    assert world.clients["adder"].get(f"/applications/{ext}").status_code == 404
    with Session(engine) as session:
        assert session.exec(select(Organization.id).where(Organization.id == world.org_id)).first() is not None
