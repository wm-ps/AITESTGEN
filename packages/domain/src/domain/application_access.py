"""Who may see an Application, and as what role — the one rule, shared by the API
(`api.access`) and the workers (who must not email someone who has lost access).

* Super admin — `app_admin` on every *team* application of their organisation.
  A personal application stays private, even from them.
* Team admin — `app_admin` on every application of their team.
* Anyone else — the role on their `application_member` row, else no access.
"""

from sqlmodel import Session, select

from domain.application import Application
from domain.application_member import APP_ADMIN_ROLE, ApplicationMember
from domain.platform_user import SUPER_ADMIN_ROLE, PlatformUser
from domain.team import TEAM_ADMIN_ROLE, TeamMember


def application_role(session: Session, user: PlatformUser, application: Application) -> str | None:
    """The user's role on the application, or None if it is hidden from them."""
    if application.organization_id != user.organization_id:
        return None
    if application.team_id is not None:
        if user.role == SUPER_ADMIN_ROLE:
            return APP_ADMIN_ROLE
        team_role = session.exec(
            select(TeamMember.role).where(TeamMember.team_id == application.team_id, TeamMember.user_id == user.id)
        ).first()
        if team_role == TEAM_ADMIN_ROLE:
            return APP_ADMIN_ROLE
    return session.exec(
        select(ApplicationMember.role).where(
            ApplicationMember.application_id == application.id, ApplicationMember.user_id == user.id
        )
    ).first()
