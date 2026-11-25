"""Teams: create them, manage who is in them, switch workspace, remove a person.

Rows are built straight in the database (no Vault, no Temporal). Needs PostgreSQL.

* Only a super admin creates teams and changes membership; a team admin gets a
  read-only view of their own team.
* A team always keeps a team admin; an organisation always keeps a super admin
  (also for two admins acting at once).
* The `X-Team-Id` header scopes lists to a team or to the personal workspace; a
  team the caller isn't in is refused.
* Removing a person: personal applications go with them, team applications stay.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api.access import join_default_team
from api.activity import _collect
from api.auth import hash_password
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import (
    Application,
    ApplicationMember,
    ActivityEvent,
    PasswordReset,
    PlatformUser,
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


def _login(email: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
    return client


class Org:
    """An organisation with a super admin (`boss`) and a few plain users, all in
    the Migrated team."""

    def __init__(self, *people: str) -> None:
        init_db()
        suffix = uuid.uuid4().hex[:8]
        self.emails = {"boss": f"boss-{suffix}@example.com"}
        seed(email=self.emails["boss"], password="pw", org_name=f"Org Teams {suffix}", name="Boss")
        with Session(engine) as session:
            boss = session.exec(select(PlatformUser).where(PlatformUser.email == self.emails["boss"])).one()
            self.org_id = boss.organization_id
            self.default_team_id = session.exec(
                select(Team.id).where(Team.organization_id == self.org_id, Team.is_default)  # type: ignore[arg-type]
            ).one()
            for key in people:
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
                join_default_team(session, user)
                self.emails[key] = email
            session.commit()
        self.clients = {key: _login(email) for key, email in self.emails.items()}

    def user_id(self, key: str) -> uuid.UUID:
        with Session(engine) as session:
            return session.exec(select(PlatformUser.id).where(PlatformUser.email == self.emails[key])).one()

    def new_team(self, name: str, admins: list[str]) -> str:
        response = self.clients["boss"].post(
            "/teams", json={"name": name, "team_admin_emails": [self.emails[a] for a in admins]}
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def application(self, name: str, *, team_external_id: str | None, adder: str, shared: dict[str, str] | None = None) -> str:
        """An application row added by `adder` in the team (None = personal)."""
        with Session(engine) as session:
            team_id = (
                None
                if team_external_id is None
                else session.exec(select(Team.id).where(Team.external_id == uuid.UUID(team_external_id))).one()
            )
            adder_id = session.exec(select(PlatformUser.id).where(PlatformUser.email == self.emails[adder])).one()
            application = Application(
                organization_id=self.org_id,
                team_id=team_id,
                created_by_id=adder_id,
                created_by_name=adder.title(),
                name=f"{name} {uuid.uuid4().hex[:5]}",
                url="https://example.com/",
                environment="staging",
                auth_method="standard_login",
                secret_ref="unused",
                discovery_required=False,
            )
            session.add(application)
            session.flush()
            session.add(ApplicationMember(application_id=application.id, user_id=adder_id, role="app_admin"))
            for key, role in (shared or {}).items():
                uid = session.exec(select(PlatformUser.id).where(PlatformUser.email == self.emails[key])).one()
                session.add(ApplicationMember(application_id=application.id, user_id=uid, role=role))
            session.commit()
            return str(application.external_id)


def _names(client: TestClient, **headers: str) -> set[str]:
    response = client.get("/applications", headers=headers)
    assert response.status_code == 200, response.text
    return {a["name"].rsplit(" ", 1)[0] for a in response.json()}


# --- creating teams ----------------------------------------------------------


def test_only_a_super_admin_creates_teams() -> None:
    org = Org("ann", "bob")
    body = {"name": "Payments", "team_admin_emails": [org.emails["ann"]]}
    assert org.clients["ann"].post("/teams", json=body).status_code == 403
    assert org.clients["ann"].get("/teams").status_code == 403
    created = org.clients["boss"].post("/teams", json=body)
    assert created.status_code == 201, created.text
    assert created.json()["team_admins"] == ["Ann"] and created.json()["member_count"] == 1


def test_a_team_needs_a_team_admin_and_a_unique_name() -> None:
    org = Org("ann")
    boss = org.clients["boss"]
    assert boss.post("/teams", json={"name": "Empty", "team_admin_emails": []}).status_code == 422
    assert boss.post("/teams", json={"name": "   ", "team_admin_emails": [org.emails["ann"]]}).status_code == 422
    assert boss.post("/teams", json={"name": "Nobody", "team_admin_emails": ["nobody@example.com"]}).status_code == 404
    assert boss.post("/teams", json={"name": "Core", "team_admin_emails": [org.emails["ann"]]}).status_code == 201
    # Same name in any case is taken.
    assert boss.post("/teams", json={"name": "CORE", "team_admin_emails": [org.emails["ann"]]}).status_code == 409
    assert boss.post("/teams", json={"name": " core ", "team_admin_emails": [org.emails["ann"]]}).status_code == 409
    names = [t["name"] for t in boss.get("/teams").json()]
    assert names.count("Core") == 1 and "Migrated" in names


def test_creating_a_team_never_uses_a_person_from_another_organisation() -> None:
    org, other = Org("ann"), Org("zed")
    response = org.clients["boss"].post("/teams", json={"name": "X", "team_admin_emails": [other.emails["zed"]]})
    assert response.status_code == 404


# --- members -----------------------------------------------------------------


def test_super_admin_adds_changes_and_removes_team_members() -> None:
    org = Org("ann", "bob", "cy")
    team = org.new_team("Growth", ["ann"])
    boss = org.clients["boss"]
    assert boss.post(f"/teams/{team}/members", json={"email": org.emails["bob"]}).json()["role"] == "team_member"
    assert boss.post(f"/teams/{team}/members", json={"email": org.emails["bob"]}).status_code == 409
    assert boss.post(f"/teams/{team}/members", json={"email": "nobody@example.com"}).status_code == 404
    assert boss.post(f"/teams/{team}/members", json={"email": org.emails["cy"], "role": "owner"}).status_code == 422
    changed = boss.patch(f"/teams/{team}/members/{org.emails['bob']}", json={"role": "team_admin"})
    assert changed.status_code == 200 and changed.json()["role"] == "team_admin"
    members = boss.get(f"/teams/{team}/members").json()
    assert [m["email"] for m in members][:2] == sorted([org.emails["ann"], org.emails["bob"]], key=lambda e: e)
    assert boss.delete(f"/teams/{team}/members/{org.emails['bob']}").status_code == 204
    assert boss.delete(f"/teams/{team}/members/{org.emails['bob']}").status_code == 404


def test_a_team_admin_only_reads_their_own_team() -> None:
    org = Org("ann", "bob")
    mine, other = org.new_team("Mine", ["ann"]), org.new_team("Other", ["bob"])
    ann = org.clients["ann"]
    assert ann.get(f"/teams/{mine}").status_code == 200
    assert [m["email"] for m in ann.get(f"/teams/{mine}/members").json()] == [org.emails["ann"]]
    assert ann.get(f"/teams/{mine}/applications").status_code == 200
    # Everything that changes a team is for super admins.
    assert ann.post(f"/teams/{mine}/members", json={"email": org.emails["bob"]}).status_code == 403
    assert ann.patch(f"/teams/{mine}/members/{org.emails['ann']}", json={"role": "team_member"}).status_code == 403
    assert ann.delete(f"/teams/{mine}/members/{org.emails['ann']}").status_code == 403
    # Another team doesn't exist for them; nor does any team for a plain member.
    assert ann.get(f"/teams/{other}").status_code == 404
    assert ann.get(f"/teams/{other}/members").status_code == 404
    assert org.clients["bob"].get(f"/teams/{mine}").status_code == 404


def test_activity_is_for_super_admins_only_not_team_admins() -> None:
    org = Org("ann", "bob")
    org.new_team("Mine", ["ann"])
    assert org.clients["boss"].get("/activity").status_code == 200
    assert org.clients["ann"].get("/activity").status_code == 403  # a Team Admin
    assert org.clients["bob"].get("/activity").status_code == 403  # a plain member


def test_a_team_always_keeps_a_team_admin() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Solo", ["ann"])
    boss = org.clients["boss"]
    demote = boss.patch(f"/teams/{team}/members/{org.emails['ann']}", json={"role": "team_member"})
    assert demote.status_code == 409
    assert "only Team Admin" in demote.json()["detail"] and "Solo" in demote.json()["detail"]
    assert boss.delete(f"/teams/{team}/members/{org.emails['ann']}").status_code == 409
    # With a second admin the first can go.
    boss.post(f"/teams/{team}/members", json={"email": org.emails["bob"], "role": "team_admin"})
    assert boss.delete(f"/teams/{team}/members/{org.emails['ann']}").status_code == 204


def test_two_super_admins_cannot_strip_the_last_two_team_admins_at_once() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Race", ["ann", "bob"])
    results: list[int] = []

    def demote(email: str) -> None:
        results.append(TestClient(app).patch(f"/teams/{team}/members/{email}", json={"role": "team_member"}).status_code)

    # The admin-row lock serialises them, so the second sees one admin left.
    clients = [_login(org.emails["boss"]), _login(org.emails["boss"])]

    def run(client: TestClient, email: str) -> None:
        results.append(client.patch(f"/teams/{team}/members/{email}", json={"role": "team_member"}).status_code)

    threads = [
        threading.Thread(target=run, args=(clients[0], org.emails["ann"])),
        threading.Thread(target=run, args=(clients[1], org.emails["bob"])),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert sorted(results) == [200, 409], results
    with Session(engine) as session:
        team_id = session.exec(select(Team.id).where(Team.external_id == uuid.UUID(team))).one()
        admins = session.exec(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.role == "team_admin")).all()
    assert len(admins) == 1


def test_removing_someone_from_a_team_takes_their_application_access_but_not_the_applications_they_added() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Shared", ["ann"])
    boss = org.clients["boss"]
    boss.post(f"/teams/{team}/members", json={"email": org.emails["bob"]})
    added_by_bob = org.application("BobsApp", team_external_id=team, adder="bob")
    shared_with_bob = org.application("AnnsApp", team_external_id=team, adder="ann", shared={"bob": "contributor"})
    assert org.clients["bob"].get(f"/applications/{added_by_bob}").status_code == 200
    assert org.clients["bob"].get(f"/applications/{shared_with_bob}").status_code == 200

    assert boss.delete(f"/teams/{team}/members/{org.emails['bob']}").status_code == 204

    assert org.clients["bob"].get(f"/applications/{shared_with_bob}").status_code == 404
    assert org.clients["bob"].get(f"/applications/{added_by_bob}").status_code == 404  # no longer in the team
    # The application they added stays with the team, under its team admin.
    assert org.clients["ann"].get(f"/applications/{added_by_bob}").status_code == 200
    assert org.clients["ann"].get(f"/applications/{added_by_bob}").json()["added_by_name"] == "Bob"
    team_apps = {a["name"].rsplit(" ", 1)[0] for a in org.clients["ann"].get(f"/teams/{team}/applications").json()}
    assert team_apps == {"BobsApp", "AnnsApp"}


def test_team_application_list_shows_who_is_working_on_each() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Crew", ["ann"])
    org.clients["boss"].post(f"/teams/{team}/members", json={"email": org.emails["bob"]})
    org.application("Checkout", team_external_id=team, adder="ann", shared={"bob": "viewer"})
    row = org.clients["boss"].get(f"/teams/{team}/applications").json()[0]
    assert row["added_by_name"] == "Ann" and row["people"] == ["Ann", "Bob"] and row["people_count"] == 2
    assert row["my_role"] == "app_admin"


# --- the workspace switcher --------------------------------------------------


def test_the_switcher_lists_personal_and_my_teams() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Alpha", ["ann"])
    org.application("Mine", team_external_id=None, adder="ann")
    org.application("InAlpha", team_external_id=team, adder="ann")
    mine = org.clients["ann"].get("/me/workspaces").json()
    assert mine["personal"] == {
        "id": "personal", "name": "My workspace", "kind": "personal", "role": None, "is_default": False, "application_count": 1,
    }
    by_name = {t["name"]: t for t in mine["teams"]}
    assert by_name["Alpha"]["role"] == "team_admin" and by_name["Alpha"]["application_count"] == 1
    assert by_name["Migrated"]["role"] == "team_member" and by_name["Migrated"]["is_default"] is True
    # Bob is only in the Migrated team.
    assert [t["name"] for t in org.clients["bob"].get("/me/workspaces").json()["teams"]] == ["Migrated"]
    # A super admin can enter every team.
    boss_teams = org.clients["boss"].get("/me/workspaces").json()["teams"]
    assert {t["name"] for t in boss_teams} == {"Alpha", "Migrated"} and {t["role"] for t in boss_teams} == {"super_admin"}


def test_the_active_workspace_scopes_lists() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Beta", ["ann"])
    org.application("PersonalApp", team_external_id=None, adder="ann")
    org.application("BetaApp", team_external_id=team, adder="ann")
    ann = org.clients["ann"]
    assert _names(ann, **{"X-Team-Id": "personal"}) == {"PersonalApp"}
    assert _names(ann, **{"X-Team-Id": team}) == {"BetaApp"}
    assert _names(ann) == {"PersonalApp", "BetaApp"}  # no header: everything she can see
    assert ann.get("/overview-stats", headers={"X-Team-Id": team}).status_code == 200
    assert ann.get("/credentials", headers={"X-Team-Id": "personal"}).status_code == 200
    # Not in the team -> refused, and a malformed or unknown id is no different.
    bob = org.clients["bob"]
    assert bob.get("/applications", headers={"X-Team-Id": team}).status_code == 403
    assert bob.get("/applications", headers={"X-Team-Id": str(uuid.uuid4())}).status_code == 403
    assert bob.get("/applications", headers={"X-Team-Id": "not-a-team"}).status_code == 400
    # A super admin may enter any team.
    assert org.clients["boss"].get("/applications", headers={"X-Team-Id": team}).status_code == 200


def test_the_header_does_not_widen_what_a_route_addressed_by_id_returns() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Gamma", ["ann"])
    app_id = org.application("Hidden", team_external_id=team, adder="ann")
    bob = org.clients["bob"]
    for header in ({}, {"X-Team-Id": "personal"}, {"X-Team-Id": team}):
        assert bob.get(f"/applications/{app_id}", headers=header).status_code == 404


def test_the_last_workspace_is_remembered_and_checked() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Delta", ["ann"])
    ann = org.clients["ann"]
    assert ann.patch("/me/workspace", json={"workspace": team}).status_code == 204
    assert ann.get("/me/workspaces").json()["last_workspace"] == team
    assert ann.patch("/me/workspace", json={"workspace": "personal"}).status_code == 204
    assert ann.get("/me/workspaces").json()["last_workspace"] == "personal"
    assert org.clients["bob"].patch("/me/workspace", json={"workspace": team}).status_code == 403
    assert ann.patch("/me/workspace", json={"workspace": "nope"}).status_code == 422
    assert ann.patch("/me/workspace", json={"workspace": str(uuid.uuid4())}).status_code == 404


# --- the people list ---------------------------------------------------------


def test_the_people_list_shows_each_persons_teams() -> None:
    org = Org("ann", "bob")
    org.new_team("Zeta", ["ann"])
    rows = {r["email"]: r for r in org.clients["boss"].get("/team").json()}
    assert rows[org.emails["ann"]]["teams"] == ["Migrated", "Zeta"]
    assert rows[org.emails["bob"]]["teams"] == ["Migrated"]


# --- removing a person -------------------------------------------------------


def test_removal_impact_counts_what_goes() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Eta", ["ann"])
    org.application("P1", team_external_id=None, adder="bob", shared={"ann": "viewer"})
    org.application("P2", team_external_id=None, adder="bob")
    org.application("T1", team_external_id=team, adder="bob")
    impact = org.clients["boss"].get(f"/team/{org.emails['bob']}/removal-impact").json()
    assert impact == {
        "name": "Bob",
        "personal_applications": 2,
        "people_losing_access": 1,
        "team_applications_added": 1,
        "teams": 1,
        "schedules_without_recipient": 0,
    }
    assert org.clients["ann"].get(f"/team/{org.emails['bob']}/removal-impact").status_code == 403
    assert org.clients["boss"].get("/team/nobody@example.com/removal-impact").status_code == 404


def test_removing_a_person_deletes_their_personal_work_but_keeps_team_applications() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Theta", ["ann"])
    org.clients["boss"].post(f"/teams/{team}/members", json={"email": org.emails["bob"]})
    personal = org.application("Personal", team_external_id=None, adder="bob", shared={"ann": "viewer"})
    in_team = org.application("InTeam", team_external_id=team, adder="bob")
    with Session(engine) as session:
        session.add(
            PasswordReset(
                user_id=org.user_id("bob"),
                token_hash=uuid.uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.commit()

    assert org.clients["boss"].delete(f"/team/{org.emails['bob']}").status_code == 204

    with Session(engine) as session:
        assert session.exec(select(PlatformUser).where(PlatformUser.email == org.emails["bob"])).first() is None
        personal_row = session.exec(select(Application).where(Application.external_id == uuid.UUID(personal))).one()
        team_row = session.exec(select(Application).where(Application.external_id == uuid.UUID(in_team))).one()
        assert personal_row.deleted_at is not None  # goes with them (retention purges it later)
        assert team_row.deleted_at is None and team_row.created_by_id is None and team_row.created_by_name == "Bob"
        assert session.exec(select(ApplicationMember).where(ApplicationMember.application_id == team_row.id)).all() == []
    assert org.clients["ann"].get(f"/applications/{personal}").status_code == 404
    assert org.clients["ann"].get(f"/applications/{in_team}").json()["added_by_name"] == "Bob"
    # Their session stops working at once.
    assert org.clients["bob"].get("/auth/me").status_code == 401


def test_a_user_who_invited_someone_can_still_be_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    org = Org("ann")
    captured: list[str] = []
    monkeypatch.setattr("api.main.send_invite_email", lambda _to, token: captured.append(token))
    # Make Ann a super admin so she can send an invite, then have the boss remove her.
    org.clients["boss"].patch(f"/team/{org.emails['ann']}/role", json={"role": "super_admin"})
    sent = org.clients["ann"].post("/invites", json={"email": f"new-{uuid.uuid4()}@example.com"})
    assert sent.status_code == 201, sent.text
    removed = org.clients["boss"].delete(f"/team/{org.emails['ann']}")
    assert removed.status_code == 204, removed.text
    # Their pending invite goes with them: it must not still be able to create an account.
    assert org.clients["boss"].get("/invites").json() == []
    accepted = TestClient(app).post("/invites/accept", json={"token": captured[0], "name": "New", "password": "a-long-password-1"})
    assert accepted.status_code >= 400


def test_removal_guards() -> None:
    org = Org("ann")
    boss = org.clients["boss"]
    assert boss.delete(f"/team/{org.emails['boss']}").status_code == 422  # not yourself
    assert org.clients["ann"].delete(f"/team/{org.emails['boss']}").status_code == 403
    assert boss.delete("/team/nobody@example.com").status_code == 404
    other = Org("zed")
    assert boss.delete(f"/team/{other.emails['zed']}").status_code == 404  # another organisation


def test_two_super_admins_cannot_remove_each_other_and_empty_the_organisation() -> None:
    org = Org("ann")
    org.clients["boss"].patch(f"/team/{org.emails['ann']}/role", json={"role": "super_admin"})
    results: list[int] = []
    clients = {"boss": _login(org.emails["boss"]), "ann": _login(org.emails["ann"])}

    def remove(who: str, target: str) -> None:
        results.append(clients[who].delete(f"/team/{org.emails[target]}").status_code)

    threads = [threading.Thread(target=remove, args=("boss", "ann")), threading.Thread(target=remove, args=("ann", "boss"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    # One removal wins; the other is refused: 409 (the last super admin), 403 (it was demoted
    # or removed meanwhile) or 401 (its account was already deleted when it got in).
    assert sorted(results) in ([204, 401], [204, 403], [204, 409]), results
    with Session(engine) as session:
        remaining = session.exec(select(PlatformUser).where(PlatformUser.organization_id == org.org_id)).all()
    assert [u.role for u in remaining].count("super_admin") == 1


def test_the_only_super_admin_can_hand_over_and_step_down() -> None:
    org = Org("ann")
    boss = org.clients["boss"]
    assert boss.post("/team/step-down", json={"successor_email": org.emails["boss"]}).status_code == 422
    assert boss.post("/team/step-down", json={"successor_email": "nobody@example.com"}).status_code == 404
    assert org.clients["ann"].post("/team/step-down", json={"successor_email": org.emails["ann"]}).status_code == 403
    assert boss.post("/team/step-down", json={"successor_email": org.emails["ann"]}).status_code == 204
    roles = {r["email"]: r["role"] for r in org.clients["ann"].get("/team").json()}
    assert roles == {org.emails["ann"]: "super_admin", org.emails["boss"]: "standard_user"}
    # The old super admin is a plain user now: no Teams, no Users.
    assert boss.get("/team").status_code == 403


def test_nobody_promotes_or_demotes_themselves() -> None:
    org = Org("ann")
    assert org.clients["ann"].patch(f"/team/{org.emails['ann']}/role", json={"role": "super_admin"}).status_code == 403
    assert org.clients["boss"].patch(f"/team/{org.emails['boss']}/role", json={"role": "standard_user"}).status_code == 422


# --- activity ----------------------------------------------------------------


def _event(org: Org, application_external_id: str | None, summary: str) -> None:
    with Session(engine) as session:
        application = (
            session.exec(select(Application).where(Application.external_id == uuid.UUID(application_external_id))).one()
            if application_external_id
            else None
        )
        session.add(
            ActivityEvent(
                organization_id=org.org_id,
                application_id=application.id if application else None,
                application_name=application.name if application else None,
                actor_name="Someone",
                category="settings",
                outcome="changed",
                summary=summary,
                details={},
            )
        )
        session.commit()


def _summaries(client: TestClient, **headers: str) -> list[str]:
    response = client.get("/activity", params={"category": "settings", "since_hours": 24}, headers=headers)
    assert response.status_code == 200, response.text
    return [i["summary"] for i in response.json()["items"]]


def test_activity_is_scoped_to_what_each_person_can_see() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Iota", ["ann"])
    org.clients["boss"].post(f"/teams/{team}/members", json={"email": org.emails["bob"]})
    visible = org.application("SharedApp", team_external_id=team, adder="ann", shared={"bob": "viewer"})
    hidden = org.application("HiddenApp", team_external_id=team, adder="ann")
    private = org.application("PrivateApp", team_external_id=None, adder="ann")
    marker = uuid.uuid4().hex[:6]
    _event(org, visible, f"visible-{marker}")
    _event(org, hidden, f"hidden-{marker}")
    _event(org, private, f"private-{marker}")
    _event(org, None, f"org-level-{marker}")

    def mine(client: TestClient, **headers: str) -> set[str]:
        return {s.split("-")[0] for s in _summaries(client, **headers) if s.endswith(marker)}

    def seen_by(email: str) -> set[str]:
        # The Activity page is for super admins only, so what a plain person
        # would see is checked at the query that feeds it.
        with Session(engine) as session:
            person = session.exec(select(PlatformUser).where(PlatformUser.email == email)).one()
            items, _ = _collect(
                session, person.organization_id, since=datetime.now(UTC) - timedelta(days=1),
                cursor=None, limit=100, category="settings", viewer=person,
            )
            return {i.summary.split("-")[0] for i in items if i.summary.endswith(marker)}

    assert seen_by(org.emails["bob"]) == {"visible"}  # only applications shared with him, nothing org-level
    assert seen_by(org.emails["ann"]) == {"visible", "hidden", "private"}  # her own, incl. personal; not org-level
    assert mine(org.clients["boss"]) == {"visible", "hidden", "org"}  # every team application + org-level; no personal
    assert mine(org.clients["boss"], **{"X-Team-Id": "personal"}) == {"org"}


def test_a_super_admin_deletes_an_empty_team() -> None:
    org = Org("ann", "bob")
    team = org.new_team("Temp", ["ann"])
    boss = org.clients["boss"]
    assert org.clients["bob"].delete(f"/teams/{team}").status_code == 403
    assert org.clients["ann"].delete(f"/teams/{team}").status_code == 403  # a team admin only reads their team
    # A member's personal application is not in the team, so it doesn't block.
    org.application("Personal", team_external_id=None, adder="ann")
    assert org.clients["ann"].patch("/me/workspace", json={"workspace": team}).status_code in (200, 204)

    assert boss.delete(f"/teams/{team}").status_code == 204
    assert team not in [t["id"] for t in boss.get("/teams").json()]
    assert boss.delete(f"/teams/{team}").status_code == 404
    # Ann's remembered workspace pointed at the team; she is back to the default.
    assert org.clients["ann"].get("/me/workspaces").json()["last_workspace"] != team


def test_a_team_with_applications_cannot_be_deleted() -> None:
    org = Org("ann")
    team = org.new_team("Busy", ["ann"])
    boss = org.clients["boss"]
    application = org.application("Checkout", team_external_id=team, adder="ann")

    blocked = boss.delete(f"/teams/{team}")
    assert blocked.status_code == 409
    assert "1 application" in blocked.json()["detail"]
    assert team in [t["id"] for t in boss.get("/teams").json()]

    # Once the application is cleaned up, the team can go.
    assert boss.delete(f"/applications/{application}").status_code in (200, 204)
    assert boss.delete(f"/teams/{team}").status_code == 204


def test_the_migrated_team_is_deletable_like_any_other_when_empty() -> None:
    org = Org("ann")
    boss = org.clients["boss"]
    migrated = next(t["id"] for t in boss.get("/teams").json() if t["is_default"])
    assert boss.delete(f"/teams/{migrated}").status_code == 204
    assert migrated not in [t["id"] for t in boss.get("/teams").json()]
