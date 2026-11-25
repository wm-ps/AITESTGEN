"""Per-workspace settings: each team and each person keeps their own Explorer
limits, retention and discovery/generation defaults, on top of an organisation
default that stays as it was.

* A team's settings: its team admins and super admins. A personal workspace's:
  its owner. A team member, or someone outside the team, is refused.
* A workspace stores only what it changed; everything else follows the default.
* The values are read where the work happens: application generation settings,
  new Explorer runs and the retention clean-up all use the workspace's own.
* The organisation's ceilings still apply to what a workspace may save.

Rows are built straight in the database (no Vault, no Temporal). Needs PostgreSQL.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api.access import join_default_team
from api.auth import hash_password
from api.db import engine, init_db
from api.main import app
from api.organization_limits import explorer_overrides
from api.scripts.seed_dev_data import seed
from domain import Application, ApplicationMember, PlatformUser, Team, TeamMember, generation_settings_for
from execution_worker.cleanup_activities import _past_retention
from explorer_core.limits import snapshot
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


pytestmark = pytest.mark.skipif(not _db_available(), reason="requires PostgreSQL reachable")


def _login(email: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
    return client


class Org:
    """A super admin, a team admin and a member of a team, plus an outsider."""

    def __init__(self) -> None:
        init_db()
        suffix = uuid.uuid4().hex[:8]
        self.emails = {"boss": f"boss-{suffix}@example.com"}
        seed(email=self.emails["boss"], password="pw", org_name=f"Org WsSettings {suffix}", name="Boss")
        with Session(engine) as session:
            boss = session.exec(select(PlatformUser).where(PlatformUser.email == self.emails["boss"])).one()
            self.org_id = boss.organization_id
            for key in ("lead", "worker", "outsider", "solo"):
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
        # Two teams: A (lead is its admin, worker a member) and B.
        self.team_a = self._team("Alpha", "lead")
        self.team_b = self._team("Beta", "solo")
        self.clients["boss"].post(f"/teams/{self.team_a}/members", json={"email": self.emails["worker"]})

    def _team(self, name: str, admin: str) -> str:
        response = self.clients["boss"].post("/teams", json={"name": name, "team_admin_emails": [self.emails[admin]]})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def application(self, name: str, team_ext: str | None, adder: str, generation: dict | None = None) -> uuid.UUID:
        with Session(engine) as session:
            team_id = None if team_ext is None else session.exec(select(Team.id).where(Team.external_id == uuid.UUID(team_ext))).one()
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
                generation_settings=generation,
            )
            session.add(application)
            session.flush()
            session.add(ApplicationMember(application_id=application.id, user_id=adder_id, role="app_admin"))
            session.commit()
            return application.id


def head(team: str) -> dict[str, str]:
    return {"X-Team-Id": team}


# --- who may edit ------------------------------------------------------------


def test_team_admins_and_super_admins_edit_a_teams_settings_and_others_cannot() -> None:
    org = Org()
    path, header = "/settings", head(org.team_a)
    for who in ("lead", "boss"):
        assert org.clients[who].get(path, headers=header).status_code == 200, who
    for who in ("worker", "outsider"):
        assert org.clients[who].get(path, headers=header).status_code in (403,), who
        assert org.clients[who].patch(path, headers=header, json={"max_pages": 5}).status_code == 403, who
    explorer = org.clients["lead"].get("/explorer/settings", headers=header).json()
    assert org.clients["worker"].put("/explorer/settings", headers=header, json=explorer).status_code == 403
    assert org.clients["lead"].put("/explorer/settings", headers=header, json=explorer).status_code == 200
    # A team admin of one team has no say over another's.
    assert org.clients["lead"].get(path, headers=head(org.team_b)).status_code == 403


def test_a_personal_workspace_is_edited_by_its_owner() -> None:
    org = Org()
    header = head("personal")
    assert org.clients["worker"].patch("/settings", headers=header, json={"max_pages": 11}).json()["max_pages"] == 11
    # Nobody else's personal settings change, and the owner's follow them everywhere they work.
    assert org.clients["outsider"].get("/settings", headers=header).json()["max_pages"] != 11
    assert org.clients["worker"].get("/settings", headers=header).json()["max_pages"] == 11


def test_without_a_workspace_only_super_admins_edit_the_organisation_default() -> None:
    org = Org()
    assert org.clients["lead"].get("/settings").status_code == 403
    assert org.clients["lead"].patch("/settings", json={"max_pages": 3}).status_code == 403
    assert org.clients["boss"].get("/settings").status_code == 200


# --- stored per workspace ----------------------------------------------------


def test_a_team_keeps_its_own_values_and_the_rest_follow_the_default() -> None:
    org = Org()
    default = org.clients["boss"].get("/settings").json()
    saved = org.clients["lead"].patch("/settings", headers=head(org.team_a), json={"delete_project_after": "1_day", "max_heal_attempts": 1})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["delete_project_after"] == "1_day" and body["max_heal_attempts"] == 1
    assert body["max_pages"] == default["max_pages"]  # untouched: follows the default

    # Another team, and the organisation default, are unchanged.
    assert org.clients["boss"].get("/settings", headers=head(org.team_b)).json() == default
    assert org.clients["boss"].get("/settings").json() == default
    again = org.clients["boss"].get("/settings", headers=head(org.team_a)).json()
    assert again["delete_project_after"] == "1_day"


def test_explorer_limits_are_per_workspace() -> None:
    org = Org()
    default = org.clients["boss"].get("/explorer/settings").json()
    mine = {**default, "ai_budget_usd": 7.5, "max_screens": 12}
    assert org.clients["lead"].put("/explorer/settings", headers=head(org.team_a), json=mine).status_code == 200
    assert org.clients["lead"].get("/explorer/settings", headers=head(org.team_a)).json()["ai_budget_usd"] == 7.5
    assert org.clients["boss"].get("/explorer/settings", headers=head(org.team_b)).json() == default
    assert org.clients["boss"].get("/explorer/settings").json() == default


# --- used where the work happens ---------------------------------------------


def test_an_applications_generation_settings_layer_default_then_workspace_then_its_own() -> None:
    org = Org()
    default = org.clients["boss"].get("/settings").json()
    org.clients["lead"].patch("/settings", headers=head(org.team_a), json={"max_heal_attempts": 1, "max_test_cases_per_application": 40})
    in_team = org.application("InAlpha", org.team_a, "lead")
    own = org.application("OwnValue", org.team_a, "lead", generation={"max_heal_attempts": 2})
    elsewhere = org.application("InBeta", org.team_b, "solo")
    with Session(engine) as session:
        assert generation_settings_for(session, in_team).max_heal_attempts == 1  # the team's
        assert generation_settings_for(session, in_team).max_test_cases_per_application == 40
        assert generation_settings_for(session, own).max_heal_attempts == 2  # the application's own wins
        assert generation_settings_for(session, own).max_test_cases_per_application == 40
        assert generation_settings_for(session, elsewhere).max_heal_attempts == default["max_heal_attempts"]


def test_a_personal_application_uses_its_owners_settings() -> None:
    org = Org()
    org.clients["worker"].patch("/settings", headers=head("personal"), json={"max_heal_attempts": 0})
    personal = org.application("Mine", None, "worker")
    others = org.application("Theirs", None, "outsider")
    with Session(engine) as session:
        assert generation_settings_for(session, personal).max_heal_attempts == 0
        assert generation_settings_for(session, others).max_heal_attempts != 0


def test_new_explorer_runs_use_the_workspaces_limits_held_to_the_ceilings() -> None:
    org = Org()
    default = org.clients["boss"].get("/explorer/settings").json()
    org.clients["lead"].put(
        "/explorer/settings", headers=head(org.team_a), json={**default, "ai_budget_usd": 20.0, "max_screens": 30}
    )
    application = org.application("Explore", org.team_a, "lead")
    with Session(engine) as session:
        row = session.get(Application, application)
        overrides = explorer_overrides(session, row)  # type: ignore[arg-type]
        assert overrides["ai_budget_usd"] == 20.0
        plain = snapshot(session, None, overrides)
        capped = snapshot(session, {"ai_budget_usd": 5.0}, overrides)
    assert plain["ai_budget_usd"] == 20.0 and plain["max_screens"] == 30
    assert capped["ai_budget_usd"] == 5.0 and capped["max_screens"] == 30


def test_retention_is_per_workspace() -> None:
    org = Org()
    org.clients["lead"].patch("/settings", headers=head(org.team_a), json={"delete_project_after": "1_day"})
    deleted = datetime.now(UTC) - timedelta(days=3)
    short = org.application("ShortKept", org.team_a, "lead")
    default = org.application("DefaultKept", org.team_b, "solo")
    with Session(engine) as session:
        for application_id in (short, default):
            row = session.get(Application, application_id)
            row.deleted_at = deleted  # type: ignore[union-attr]
            session.add(row)
        session.commit()
        assert _past_retention(session, session.get(Application, short)) is True  # type: ignore[arg-type]  # kept 1 day, gone for 3
        assert _past_retention(session, session.get(Application, default)) is False  # type: ignore[arg-type]  # 1 month default


def test_the_organisations_ceilings_still_bind_a_workspace() -> None:
    org = Org()
    assert org.clients["boss"].put("/organization/limits", json={"maximums": {"max_heal_attempts": 3}, "min_delete_project_after": "1_week"}).status_code == 200
    header = head(org.team_a)
    over = org.clients["lead"].patch("/settings", headers=header, json={"max_heal_attempts": 5})
    assert over.status_code == 422 and "Max heal attempts can't be more than 3" in over.json()["detail"]
    short = org.clients["lead"].patch("/settings", headers=header, json={"delete_project_after": "1_day"})
    assert short.status_code == 422 and "Retention can't be shorter than 1 week" in short.json()["detail"]
    assert org.clients["lead"].patch("/settings", headers=header, json={"max_heal_attempts": 3, "delete_project_after": "1_week"}).status_code == 200


def test_removing_a_team_member_or_team_leaves_other_workspaces_alone() -> None:
    org = Org()
    org.clients["lead"].patch("/settings", headers=head(org.team_a), json={"max_pages": 21})
    org.clients["solo"].patch("/settings", headers=head(org.team_b), json={"max_pages": 22})
    org.clients["boss"].delete(f"/teams/{org.team_a}/members/{org.emails['worker']}")
    assert org.clients["boss"].get("/settings", headers=head(org.team_a)).json()["max_pages"] == 21
    assert org.clients["boss"].get("/settings", headers=head(org.team_b)).json()["max_pages"] == 22
