"""Forgot-password issuing/consumption — mirrors `api.invites`'s token design.

The raw token is the sole secret and is never persisted: only its sha256
(`token_hash`) is stored, same rationale as Invite. Reuses `invites.py`'s
SMTP config/`_hash_token` rather than re-declaring them.
"""

import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from domain import PasswordReset, PlatformUser
from sqlmodel import Session, select

from api.auth import hash_password
from api.invites import (
    _EMAIL_HEADER,
    FRONTEND_BASE_URL,
    _attach_logo,
    SMTP_FROM,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    _hash_token,
)

logger = logging.getLogger(__name__)

RESET_EXPIRY = timedelta(hours=1)


def _reset_link(token: str) -> str:
    return f"{FRONTEND_BASE_URL}/reset-password?token={token}"


def _reset_html(name: str, link: str) -> str:
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
          <p style="margin:0 0 16px;font-size:16px;color:#1a1a1a;">Hi {name},</p>
          <p style="margin:0 0 28px;font-size:14px;color:#555555;line-height:1.5;">We received a request to reset your password. Click below to choose a new one. This link expires in 1 hour and can only be used once. If you didn't request this, you can ignore this email.</p>
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:8px;background:#0f766e;">
              <a href="{link}" style="display:inline-block;padding:12px 28px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">Reset password</a>
            </td>
          </tr></table>
          <p style="margin:28px 0 0;font-size:12px;color:#999999;word-break:break-all;">Or paste this link into your browser: {link}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_reset_email(to_email: str, name: str, token: str) -> None:
    link = _reset_link(token)
    if not SMTP_HOST:
        # ponytail: dev fallback, no SMTP configured — log the link instead
        # of failing, same as invites.py's send_invite_email.
        logger.info("password reset link for %s: %s", to_email, link)
        return

    message = EmailMessage()
    message["Subject"] = "Reset your WaveQA password"
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = to_email
    message.set_content(
        f"Hi {name},\n\n"
        f"We received a request to reset your password.\n\n"
        f"Reset it here: {link}\n\n"
        f"This link expires in 1 hour and can only be used once. "
        f"If you didn't request this, you can ignore this email."
    )
    message.add_alternative(_reset_html(name, link), subtype="html")
    _attach_logo(message)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


def request_password_reset(session: Session, email: str) -> None:
    """Always a no-op-looking call from the outside — never reveals whether
    `email` belongs to an account (no user found = silently do nothing)."""
    user = session.exec(select(PlatformUser).where(PlatformUser.email == email)).first()
    if user is None:
        return
    token = secrets.token_urlsafe(32)
    reset = PasswordReset(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=datetime.now(UTC) + RESET_EXPIRY,
    )
    session.add(reset)
    session.commit()
    send_reset_email(user.email, user.name, token)


class PasswordResetError(Exception):
    """Raised for any invalid/expired/used token — main.py maps this to a
    single 400, same non-distinguishing rationale as InviteAcceptError."""


def _valid_reset(session: Session, token: str) -> tuple[PasswordReset, PlatformUser]:
    reset = session.exec(
        select(PasswordReset).where(PasswordReset.token_hash == _hash_token(token))
    ).first()
    if reset is None or reset.used_at is not None or reset.expires_at < datetime.now(UTC):
        raise PasswordResetError("invalid or expired reset link")
    user = session.get(PlatformUser, reset.user_id)
    assert user is not None
    return reset, user


def get_reset_target(session: Session, token: str) -> PlatformUser:
    _reset, user = _valid_reset(session, token)
    return user


def reset_password(session: Session, token: str, new_password: str) -> PlatformUser:
    reset, user = _valid_reset(session, token)
    user.hashed_password = hash_password(new_password)
    reset.used_at = datetime.now(UTC)
    session.add(user)
    session.add(reset)
    session.commit()
    session.refresh(user)
    return user
