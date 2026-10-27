"""Email the person who started an Explorer run whenever it needs them, so
a paused run never sits unnoticed. Same SMTP settings as Vantage's invite
emails (apps/api/src/api/invites.py)."""

import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173")


def send_pause_email(to_email: str, app_name: str, heading: str, body: str) -> None:
    """Never raises: a mail problem must not stop the run."""
    link = FRONTEND_BASE_URL
    subject = f"Vantage Explorer needs you: {app_name}"
    host = os.environ.get("SMTP_HOST")
    if not host:
        # ponytail: dev fallback like invites.py — log instead of sending.
        logger.info("pause email for %s: %s — %s", to_email, heading, body)
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(
        (
            os.environ.get("SMTP_FROM_NAME", "Vantage"),
            os.environ.get("SMTP_FROM", "no-reply@vantage.local"),
        )
    )
    message["To"] = to_email
    message.set_content(f"{heading}\n\n{body}\n\nOpen Vantage: {link}\n")
    message.add_alternative(_html(app_name, heading, body, link), subtype="html")
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=20) as smtp:
            smtp.starttls()
            user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(message)
    except OSError, smtplib.SMTPException:
        logger.exception("could not send the pause email to %s", to_email)


def _html(app_name: str, heading: str, body: str, link: str) -> str:
    e = html.escape
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f5f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f6;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="border-bottom:1px solid #e8eaec;padding:20px 32px;font-size:15px;font-weight:700;color:#0f766e;">Vantage Explorer</td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 6px;font-size:12px;color:#777777;">{e(app_name)}</p>
          <p style="margin:0 0 16px;font-size:16px;color:#1a1a1a;font-weight:600;">{e(heading)}</p>
          <p style="margin:0 0 28px;font-size:14px;color:#555555;line-height:1.5;">{e(body)}</p>
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:8px;background:#0f766e;">
              <a href="{e(link)}" style="display:inline-block;padding:12px 28px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">Open Vantage</a>
            </td>
          </tr></table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
