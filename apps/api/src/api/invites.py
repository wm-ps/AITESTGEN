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
from email.utils import formataddr
from hashlib import sha256
from pathlib import Path

from domain import Invite, PlatformUser
from sqlmodel import Session, select

from api.auth import hash_password

logger = logging.getLogger(__name__)

INVITE_EXPIRY = timedelta(hours=72)
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@vantage.local")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Vantage")


def _hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


# Reuses the exact web app brand (apps/web/src/components/Brand.tsx
# VantageMark), pre-rasterized to a PNG and sent as a CID-attached inline
# image — not a data: URI or inline <svg>, both of which Gmail and legacy
# desktop Outlook strip. CID `add_related` is the one embedding method every
# major client (Gmail included) displays. The "Vantage" wordmark next to it
# is plain HTML text, not an image — text renders natively, no CID needed.
_LOGO_CID = "vantage-mark"
_LOGO_PNG = (Path(__file__).parent / "assets" / "vantage-mark.png").read_bytes()

_EMAIL_HEADER = f"""\
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="width:64px;height:59px;"><img src="cid:{_LOGO_CID}" width="64" height="59" alt="Vantage" style="display:block;border:0;"></td>
            <td style="padding-left:12px;vertical-align:middle;font-size:28px;letter-spacing:-0.03em;font-weight:700;color:#0f766e;">
              Vantage
            </td>
          </tr></table>"""


def _attach_logo(message: EmailMessage) -> None:
    """Call after add_alternative(html) — hangs the CID image off the html
    subpart so `cid:{_LOGO_CID}` in _EMAIL_HEADER resolves."""
    html_part = message.get_payload()[1]
    html_part.add_related(_LOGO_PNG, "image", "png", cid=f"<{_LOGO_CID}>")


def _invite_link(token: str) -> str:
    return f"{FRONTEND_BASE_URL}/accept-invite?token={token}"


def _invite_html(link: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f5f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f6;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="background:#ffffff;border-bottom:1px solid #e8eaec;padding:24px 32px;">
{_EMAIL_HEADER}
        </td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 16px;font-size:16px;color:#1a1a1a;">You've been invited to join Vantage</p>
          <p style="margin:0 0 28px;font-size:14px;color:#555555;line-height:1.5;">Click below to accept your invite and set up your account. This link expires in 72 hours.</p>
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:8px;background:#0f766e;">
              <a href="{link}" style="display:inline-block;padding:12px 28px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">Accept invite</a>
            </td>
          </tr></table>
          <p style="margin:28px 0 0;font-size:12px;color:#999999;word-break:break-all;">Or paste this link into your browser: {link}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_invite_email(to_email: str, token: str) -> None:
    link = _invite_link(token)
    if not SMTP_HOST:
        # ponytail: dev fallback, no SMTP configured — log the link instead
        # of failing. Add real SMTP env vars (SMTP_HOST/USER/PASSWORD) to send.
        logger.info("invite link for %s: %s", to_email, link)
        return

    message = EmailMessage()
    message["Subject"] = "You're invited to join Vantage"
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = to_email
    message.set_content(
        f"You've been invited to join Vantage.\n\n"
        f"Accept your invite: {link}\n\n"
        f"This link expires in 72 hours."
    )
    message.add_alternative(_invite_html(link), subtype="html")
    _attach_logo(message)
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
