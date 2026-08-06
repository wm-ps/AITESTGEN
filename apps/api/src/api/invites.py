"""Invite issuing/acceptance — enterprise Sign-up (invite-only, AD-12 org-scoped).

No open self-service signup (`seed_dev_data.py`'s established constraint) —
this is the only other way a `PlatformUser` row gets created. The raw token
is the sole secret and is never persisted: only its sha256 (`token_hash`) is
stored, so a DB leak can't be replayed into an account. Revocation/audit is
the *point* of a DB-backed invite (over a signed stateless token) — a
pending invite is a row an admin can see and delete.
"""

import logging
import os
import secrets
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256

from domain import Invite, Organization, PlatformUser
from sqlmodel import Session, select

from api.auth import hash_password

logger = logging.getLogger(__name__)

INVITE_EXPIRY = timedelta(hours=72)
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@aitestgen.local")


def _hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _invite_link(token: str) -> str:
    return f"{FRONTEND_BASE_URL}/accept-invite?token={token}"


def send_invite_email(to_email: str, org_name: str, token: str) -> None:
    link = _invite_link(token)
    if not SMTP_HOST:
        # ponytail: dev fallback, no SMTP configured — log the link instead
        # of failing. Add real SMTP env vars (SMTP_HOST/USER/PASSWORD) to send.
        logger.info("invite link for %s (%s): %s", to_email, org_name, link)
        return

    message = EmailMessage()
    message["Subject"] = f"You're invited to join {org_name} on AITestGen"
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message.set_content(
        f"You've been invited to join {org_name} on AITestGen.\n\n"
        f"Accept your invite: {link}\n\n"
        f"This link expires in 72 hours."
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


def create_invite(
    session: Session, organization_id: uuid.UUID, invited_by_id: uuid.UUID, email: str, role: str
) -> tuple[Invite, str]:
    token = secrets.token_urlsafe(32)
    invite = Invite(
        organization_id=organization_id,
        invited_by_id=invited_by_id,
        email=email,
        role=role,
        token_hash=_hash_token(token),
        expires_at=datetime.now(UTC) + INVITE_EXPIRY,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite, token


class InviteAcceptError(Exception):
    """Raised for any invalid/expired/used/unknown token — main.py maps this
    to a single 400, deliberately not distinguishing the reasons (AC: don't
    let a caller probe which tokens exist vs. are merely expired)."""


def accept_invite(session: Session, token: str, name: str, password: str) -> PlatformUser:
    invite = session.exec(
        select(Invite).where(Invite.token_hash == _hash_token(token))
    ).first()
    if invite is None or invite.used_at is not None or invite.expires_at < datetime.now(UTC):
        raise InviteAcceptError("invalid or expired invite")

    user = PlatformUser(
        organization_id=invite.organization_id,
        email=invite.email,
        name=name,
        hashed_password=hash_password(password),
        role=invite.role,
    )
    session.add(user)
    invite.used_at = datetime.now(UTC)
    session.add(invite)
    session.commit()
    session.refresh(user)
    return user


def org_name(session: Session, organization_id: uuid.UUID) -> str:
    org = session.get(Organization, organization_id)
    assert org is not None
    return org.name
