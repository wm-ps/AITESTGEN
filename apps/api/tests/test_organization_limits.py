"""Organisation limits: ceilings a super admin sets on resource settings.

* Saving a value above a ceiling is refused (422) — never silently capped —
  for the organisation default, Explorer limits and an application's own
  generation settings; unchanged values are left alone.
* The effective value is held to the ceiling when read, so lowering a limit
  applies to settings saved earlier without rewriting them.
* Retention has a floor, not a ceiling.

Rows are built straight in the database (no Vault, no Temporal). Needs PostgreSQL.
"""

import uuid

import pytest
from api.auth import hash_password
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, ApplicationMember, PlatformUser, Team, generation_settings_for
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


class Org:
    """A super admin and an application admin of one application."""

    def __init__(self, generation: dict | None = None) -> None:
        init_db()
        suffix = uuid.uuid4().hex[:8]
        self.boss_email = f"boss-{suffix}@example.com"
        seed(email=self.boss_email, password="pw", org_name=f"Org Limits {suffix}", name="Boss")
        self.owner_email = f"owner-{suffix}@example.com"
        with Session(engine) as session:
            boss = session.exec(select(PlatformUser).where(PlatformUser.email == self.boss_email)).one()
            self.org_id = boss.organization_id
            owner = PlatformUser(
                organization_id=self.org_id,
                email=self.owner_email,
                name="Owner",
                hashed_password=hash_password("pw"),
                role="standard_user",
            )
            session.add(owner)
            session.flush()
            application = Application(
                organization_id=self.org_id,
                created_by_id=owner.id,
                created_by_name="Owner",
                name=f"App {suffix}",
                url="https://example.com/",
                environment="staging",
                auth_method="standard_login",
                secret_ref="unused",
                discovery_required=False,
                generation_settings=generation,
            )
            session.add(application)
            session.flush()
            session.add(ApplicationMember(application_id=application.id, user_id=owner.id, role="app_admin"))
            session.commit()
            self.app_id = application.id
            self.app_ext = str(application.external_id)
        self.boss = self._login(self.boss_email)
        self.owner = self._login(self.owner_email)

    @staticmethod
    def _login(email: str) -> TestClient:
        client = TestClient(app)
        assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
        return client

    def move_to_team(self) -> None:
        """Puts the application in a new team (it starts out personal)."""
        team = self.boss.post("/teams", json={"name": f"T {uuid.uuid4().hex[:6]}", "team_admin_emails": [self.owner_email]})
        assert team.status_code == 201, team.text
        with Session(engine) as session:
            team_id = session.exec(select(Team.id).where(Team.external_id == uuid.UUID(team.json()["id"]))).one()
            row = session.get(Application, self.app_id)
            row.team_id = team_id  # type: ignore[union-attr]
            session.add(row)
            session.commit()

    def set_limits(self, maximums: dict, min_retention: str | None = None) -> dict:
        response = self.boss.put(
            "/organization/limits", json={"maximums": maximums, "min_delete_project_after": min_retention}
        )
        assert response.status_code == 200, response.text
        return response.json()


def test_only_a_super_admin_sees_or_sets_limits() -> None:
    org = Org()
    assert org.owner.get("/organization/limits").status_code == 403
    assert org.owner.put("/organization/limits", json={"maximums": {"max_heal_attempts": 2}}).status_code == 403
    assert org.boss.get("/organization/limits").json() == {"maximums": {}, "min_delete_project_after": None, "above": []}


def test_limits_are_validated() -> None:
    org = Org()
    put = org.boss.put
    assert put("/organization/limits", json={"maximums": {"nonsense": 5}}).status_code == 422
    assert put("/organization/limits", json={"maximums": {"max_heal_attempts": 0}}).status_code == 422
    assert put("/organization/limits", json={"maximums": {"max_heal_attempts": -1}}).status_code == 422
    assert put("/organization/limits", json={"min_delete_project_after": "forever"}).status_code == 422


def test_an_application_admin_cannot_save_generation_settings_above_the_ceiling() -> None:
    org = Org()
    org.set_limits({"max_heal_attempts": 3, "max_test_cases_per_application": 100})
    path = f"/applications/{org.app_ext}/generation-settings"
    current = org.owner.get(path).json()

    over = org.owner.put(path, json={**current, "max_heal_attempts": 5})
    assert over.status_code == 422
    assert "Max heal attempts can't be more than 3" in over.json()["detail"]
    # "Unlimited" is above any ceiling.
    unlimited = org.owner.put(path, json={**current, "max_test_cases_per_application": None})
    assert unlimited.status_code == 422
    assert org.owner.put(path, json={**current, "max_heal_attempts": 3, "max_test_cases_per_application": 100}).status_code == 200


def test_lowering_a_limit_holds_existing_settings_without_rewriting_them() -> None:
    org = Org(generation={"max_heal_attempts": 8, "max_scenarios_per_journey": 10, "max_test_cases_per_application": 50,
                          "screenshot_capture": "all"})
    path = f"/applications/{org.app_ext}/generation-settings"
    assert org.owner.get(path).json()["max_heal_attempts"] == 8

    # A personal application's name is private, even from the super admin who sets the limits.
    personal = org.set_limits({"max_heal_attempts": 4, "max_scenarios_per_journey": 5})["above"]
    assert not [a for a in personal if a["scope"].startswith("App ")]
    org.move_to_team()
    above = org.set_limits({"max_heal_attempts": 4, "max_scenarios_per_journey": 5})["above"]
    mine = {(a["setting"], a["value"], a["limit"]) for a in above if a["scope"].startswith("App ")}
    assert mine == {("max_heal_attempts", 8, 4), ("max_scenarios_per_journey", 10, 5)}

    # Read (and so used) at the ceiling; the stored value is untouched.
    held = org.owner.get(path).json()
    assert held["max_heal_attempts"] == 4 and held["max_scenarios_per_journey"] == 5
    assert held["max_test_cases_per_application"] == 50  # no ceiling on this one
    with Session(engine) as session:
        assert session.get(Application, org.app_id).generation_settings["max_heal_attempts"] == 8  # type: ignore[union-attr]
        assert generation_settings_for(session, org.app_id).max_heal_attempts == 4

    # An old, now-too-high value does not block saving something else.
    saved = org.owner.put(path, json={**org.owner.get(path).json(), "screenshot_capture": "failed"})
    assert saved.status_code == 200, saved.text


def test_removing_the_limits_lifts_the_cap() -> None:
    org = Org(generation={"max_heal_attempts": 8})
    org.set_limits({"max_heal_attempts": 2})
    path = f"/applications/{org.app_ext}/generation-settings"
    assert org.owner.get(path).json()["max_heal_attempts"] == 2
    org.set_limits({})
    assert org.owner.get(path).json()["max_heal_attempts"] == 8


def test_limits_apply_to_the_organisation_default_and_explorer_limits() -> None:
    org = Org()
    settings = org.boss.get("/settings").json()
    explorer = org.boss.get("/explorer/settings").json()
    budget = 5.0  # the default AI budget is "no limit", so give it a real value to test against
    try:
        assert org.boss.put("/explorer/settings", json={**explorer, "ai_budget_usd": budget}).status_code == 200
        org.set_limits({"max_pages": settings["max_pages"], "ai_budget_usd": budget})
        too_many = org.boss.patch("/settings", json={"max_pages": settings["max_pages"] + 1})
        assert too_many.status_code == 422 and "Max pages" in too_many.json()["detail"]
        too_costly = org.boss.put("/explorer/settings", json={**explorer, "ai_budget_usd": budget + 1})
        assert too_costly.status_code == 422 and "Ai budget usd" in too_costly.json()["detail"]
        unlimited = org.boss.put("/explorer/settings", json={**explorer, "ai_budget_usd": None})
        assert unlimited.status_code == 422  # "no limit" is above any ceiling
        # Saving the same values (or lower) is fine.
        assert org.boss.patch("/settings", json={"max_pages": settings["max_pages"]}).status_code == 200
        assert org.boss.put("/explorer/settings", json={**explorer, "ai_budget_usd": budget}).status_code == 200
    finally:
        org.set_limits({})
        org.boss.patch("/settings", json={"max_pages": settings["max_pages"]})
        org.boss.put("/explorer/settings", json=explorer)


def test_retention_has_a_floor() -> None:
    org = Org()
    before = org.boss.get("/settings").json()["delete_project_after"]
    try:
        org.set_limits({}, min_retention="1_week")
        too_short = org.boss.patch("/settings", json={"delete_project_after": "1_day"})
        assert too_short.status_code == 422 and "Retention can't be shorter than 1 week" in too_short.json()["detail"]
        assert org.boss.patch("/settings", json={"delete_project_after": "1_week"}).status_code == 200
        assert org.boss.patch("/settings", json={"delete_project_after": "1_month"}).status_code == 200
    finally:
        org.boss.patch("/settings", json={"delete_project_after": before})


def test_the_explorer_snapshot_is_held_to_the_ceilings() -> None:
    init_db()
    with Session(engine) as session:
        plain = snapshot(session)
        capped = snapshot(session, {"ai_budget_usd": 0.5, "max_screens": 1, "not_a_limit": 1})
    def held(value, ceiling):
        return ceiling if value is None else min(value, ceiling)  # no limit -> the ceiling

    assert capped["ai_budget_usd"] == held(plain["ai_budget_usd"], 0.5)
    assert capped["max_screens"] == held(plain["max_screens"], 1)
    assert "not_a_limit" not in capped
    assert {k: v for k, v in capped.items() if k not in ("ai_budget_usd", "max_screens")} == {
        k: v for k, v in plain.items() if k not in ("ai_budget_usd", "max_screens")
    }


def test_one_organisations_limits_never_touch_another() -> None:
    first, second = Org(generation={"max_heal_attempts": 8}), Org(generation={"max_heal_attempts": 8})
    first.set_limits({"max_heal_attempts": 2})
    assert first.owner.get(f"/applications/{first.app_ext}/generation-settings").json()["max_heal_attempts"] == 2
    assert second.owner.get(f"/applications/{second.app_ext}/generation-settings").json()["max_heal_attempts"] == 8
