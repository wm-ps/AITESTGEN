"""Everything the understanding loop writes down: live feed events,
screenshots, understood screens, health issues, run status. Short-lived DB
sessions per write so the Live screen sees progress immediately."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from domain import Application, DiscoveryRun, PlatformUser
from explorer_core import (
    ExplorerEvent,
    ExplorerHealthIssue,
    ExplorerMission,
    ExplorerRun,
    ExplorerScreen,
    ExplorerShot,
    ExplorerTransition,
)
from explorer_core.notify import send_pause_email
from sqlmodel import Session, col, select

from explorer_worker.db import engine

logger = logging.getLogger(__name__)


def _fail_discovery(session: Session, application_id: uuid.UUID, reason: str | None) -> None:
    discovery_run = session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "crawler")
        .order_by(col(DiscoveryRun.created_at).desc())
    ).first()
    if discovery_run is not None and discovery_run.status == "running":
        discovery_run.status, discovery_run.failure_reason = "failed", (reason or "")[:500] or None
        session.add(discovery_run)


class Journal:
    """Writes for one run; `mission_id` tags events/edges with the mission
    that produced them (Stage 2), so each mission has its own feed."""

    def __init__(self, run_id: uuid.UUID, mission_id: uuid.UUID | None = None) -> None:
        self.run_id = run_id
        self.mission_id = mission_id

    def update_run(self, **changes: Any) -> None:
        with Session(engine) as session:
            run = session.get(ExplorerRun, self.run_id)
            if run is None:
                return
            if run.status == "paused" and "status" not in changes:
                return  # a step still winding down must not overwrite "Paused"
            for key, value in changes.items():
                setattr(run, key, value)
            run.updated_at = datetime.now(UTC)
            session.add(run)
            if changes.get("status") in ("failed", "expired"):
                # Ended without a hand-off: the app's discovery record (Stage 8)
                # says so too, instead of "running" forever.
                _fail_discovery(session, run.application_id, run.error or run.headline)
            session.commit()

    def status(self) -> str | None:
        with Session(engine) as session:
            run = session.get(ExplorerRun, self.run_id)
            if run is None:
                return None
            # Everything in flight halts on a pause exactly as on a stop; the
            # run picks up again on resume.
            return "stopped" if run.status == "paused" else run.status

    def shot(self, data: bytes) -> uuid.UUID:
        with Session(engine) as session:
            row = ExplorerShot(run_id=self.run_id, data=data)
            session.add(row)
            session.commit()
            return row.id

    def event(
        self, kind: str, title: str, detail: str | None = None, shot_id: uuid.UUID | None = None
    ) -> None:
        # Phases start and end with these: mirrored to the worker log.
        if kind in ("phase", "summary", "error"):
            logger.info(
                "run %s%s %s: %s",
                self.run_id,
                f" mission {self.mission_id}" if self.mission_id else "",
                kind,
                title if not detail else f"{title} — {' '.join(detail.split())[:200]}",
            )
        with Session(engine) as session:
            session.add(
                ExplorerEvent(
                    run_id=self.run_id,
                    kind=kind,
                    title=title[:300],
                    detail=detail,
                    shot_id=shot_id,
                    mission_id=self.mission_id,
                )
            )
            session.commit()

    def email_starter(self, heading: str, body: str) -> None:
        """Tell the person who started this run that it needs them. Blocking
        (SMTP): async callers run it in a thread."""
        with Session(engine) as session:
            run = session.get(ExplorerRun, self.run_id)
            if run is None or run.started_by_id is None:
                return
            user = session.get(PlatformUser, run.started_by_id)
            app = session.get(Application, run.application_id)
            if user is None or app is None:
                return
            to_email, app_name = user.email, app.name
        send_pause_email(to_email, app_name, heading, body)

    def upsert_screen(
        self, signature: str, values: dict[str, Any], home_pattern: str | None = None
    ) -> tuple[uuid.UUID, bool]:
        """Returns the screen's id and whether it is newly understood.

        Same meaning (signature) = same screen. Also: the same kind of screen
        at the same app address is the same screen even when two readings
        named it differently ("Claim vehicle details" / "Vehicle details") —
        except at the app's home address, which single-URL apps reuse for
        every screen."""
        pattern = values.get("url_pattern")
        with Session(engine) as session:
            existing = session.exec(
                select(ExplorerScreen).where(
                    ExplorerScreen.run_id == self.run_id, ExplorerScreen.signature == signature
                )
            ).first()
            if existing is None:
                # The model is told to reuse a known screen's exact name; a
                # differing view_kind/mode reading must not split it in two.
                existing = session.exec(
                    select(ExplorerScreen).where(
                        ExplorerScreen.run_id == self.run_id,
                        ExplorerScreen.name == values.get("name"),
                    )
                ).first()
            if existing is None and pattern and pattern != home_pattern:
                existing = session.exec(
                    select(ExplorerScreen).where(
                        ExplorerScreen.run_id == self.run_id,
                        ExplorerScreen.url_pattern == pattern,
                        # forms and wizard steps get labelled either way
                        col(ExplorerScreen.view_kind).in_(
                            ("form", "wizard")
                            if values.get("view_kind") in ("form", "wizard")
                            else (values.get("view_kind"),)
                        ),
                    )
                ).first()
            if existing is not None:
                existing.visits += 1
                if existing.goal_fit is None and values.get("goal_fit"):
                    existing.goal_fit = values["goal_fit"]  # the first verdict wins
                if values.get("reached_by") == "Start page":
                    # a screen copied from an earlier run may be this run's start
                    existing.reached_by = "Start page"
                # Keep the richer reading: later visits often see more fields.
                if len(values.get("fields", [])) > len(existing.fields):
                    existing.fields = values["fields"]
                existing.hidden_hints = list(
                    dict.fromkeys(existing.hidden_hints + values.get("hidden_hints", []))
                )
                session.add(existing)
                session.commit()
                return existing.id, False
            row = ExplorerScreen(run_id=self.run_id, signature=signature, **values)
            session.add(row)
            session.commit()
            return row.id, True

    def set_goal_fit(self, fits: dict[str, str]) -> None:
        """Each named screen's place against the run's Goal (explorer_core.GOAL_FITS)."""
        with Session(engine) as session:
            for screen in session.exec(
                select(ExplorerScreen).where(ExplorerScreen.run_id == self.run_id)
            ).all():
                if screen.name in fits:
                    screen.goal_fit = fits[screen.name]
                    session.add(screen)
            session.commit()

    def transition(self, from_id: uuid.UUID, to_id: uuid.UUID, action: str) -> None:
        """One App Map edge per (from, to, action) — repeats aren't stored."""
        action = action[:200]
        with Session(engine) as session:
            exists = session.exec(
                select(ExplorerTransition.id).where(
                    ExplorerTransition.run_id == self.run_id,
                    ExplorerTransition.from_screen_id == from_id,
                    ExplorerTransition.to_screen_id == to_id,
                    ExplorerTransition.action == action,
                )
            ).first()
            if exists is None:
                session.add(
                    ExplorerTransition(
                        run_id=self.run_id,
                        from_screen_id=from_id,
                        to_screen_id=to_id,
                        action=action,
                        mission_id=self.mission_id,
                    )
                )
                session.commit()

    def update_mission(self, **changes: Any) -> None:
        assert self.mission_id is not None
        with Session(engine) as session:
            mission = session.get(ExplorerMission, self.mission_id)
            if mission is None:
                return
            for key, value in changes.items():
                setattr(mission, key, value)
            session.add(mission)
            session.commit()

    def mission_status(self) -> str | None:
        assert self.mission_id is not None
        with Session(engine) as session:
            mission = session.get(ExplorerMission, self.mission_id)
            return mission.status if mission else None

    def health_issue(
        self,
        kind: str,
        severity: str,
        title: str,
        detail: str | None,
        url: str,
        shot_id: uuid.UUID | None,
    ) -> bool:
        """Returns True when this is a new problem (repeats just count up).
        Background/server errors are the same problem wherever they show up,
        so they match on what failed; page problems match on the page."""
        detail = (detail or "")[:1000] or None
        same_place = (
            ExplorerHealthIssue.detail == detail
            if kind in ("server_error", "background_error")
            else ExplorerHealthIssue.url == url
        )
        with Session(engine) as session:
            existing = session.exec(
                select(ExplorerHealthIssue).where(
                    ExplorerHealthIssue.run_id == self.run_id,
                    ExplorerHealthIssue.kind == kind,
                    ExplorerHealthIssue.title == title[:300],
                    same_place,
                )
            ).first()
            if existing is not None:
                existing.occurrences += 1
                session.add(existing)
                session.commit()
                return False
            session.add(
                ExplorerHealthIssue(
                    run_id=self.run_id,
                    kind=kind,
                    severity=severity,
                    title=title[:300],
                    detail=detail,
                    url=url,
                    shot_id=shot_id,
                )
            )
            session.commit()
            return True

    def issue_id(self, title: str) -> uuid.UUID | None:
        with Session(engine) as session:
            return session.exec(
                select(ExplorerHealthIssue.id).where(
                    ExplorerHealthIssue.run_id == self.run_id,
                    ExplorerHealthIssue.title == title[:300],
                )
            ).first()

    def health_rows(self) -> list[ExplorerHealthIssue]:
        with Session(engine) as session:
            return list(
                session.exec(
                    select(ExplorerHealthIssue).where(ExplorerHealthIssue.run_id == self.run_id)
                ).all()
            )

    def screen_rows(self) -> list[ExplorerScreen]:
        with Session(engine) as session:
            return list(
                session.exec(
                    select(ExplorerScreen).where(ExplorerScreen.run_id == self.run_id)
                ).all()
            )
