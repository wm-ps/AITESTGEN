"""Outgoing email for every Vantage service: SMTP settings, the branded
header every email starts with, and one `send_email`.

Callers decide what to do when SMTP isn't configured (`smtp_configured()`)
— invites and password resets log their link, the run-completed email logs
and skips — so `send_email` itself always sends, and raises on SMTP errors.
"""

import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@vantage.local")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Vantage")

# Reuses the exact web app brand (apps/web/src/components/Brand.tsx
# VantageBrand), pre-rasterized to a PNG and sent as a CID-attached inline
# image — not a data: URI or inline <svg>, both of which Gmail and legacy
# desktop Outlook strip. CID `add_related` is the one embedding method every
# major client (Gmail included) displays. The logo image already contains
# the "Vantage" wordmark, so no separate text cell is needed here.
LOGO_CID = "vantage-logo"
_LOGO_PNG = (Path(__file__).parent / "assets" / "vantage-logo-v2.png").read_bytes()
_LOGO_WIDTH, _LOGO_HEIGHT = 124, 24  # source is 315x61, scaled to email header size

EMAIL_HEADER = f"""\
          <img src="cid:{LOGO_CID}" width="{_LOGO_WIDTH}" height="{_LOGO_HEIGHT}" alt="Vantage" style="display:block;border:0;">"""


def smtp_configured() -> bool:
    return bool(SMTP_HOST)


def send_email(to_email: str, subject: str, text: str, html: str) -> None:
    """Sends one multipart (plain text + HTML) email with the logo attached
    for EMAIL_HEADER's `cid:` image. Raises on any SMTP/connection error."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    # Hang the logo off the html subpart so `cid:{LOGO_CID}` resolves.
    message.get_payload()[1].add_related(_LOGO_PNG, "image", "png", cid=f"<{LOGO_CID}>")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


__all__ = [
    "EMAIL_HEADER",
    "FRONTEND_BASE_URL",
    "LOGO_CID",
    "send_email",
    "smtp_configured",
]
