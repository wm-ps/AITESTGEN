"""Public "Connect with our team" enquiries from the signed-out Landing and
Product pages (`ContactDialog` in the web app's MarketingChrome.tsx).

Flow: web form → `POST /contact` → shared `mailer.send_email` → the team
inbox(es) in `CONTACT_TEAM_EMAIL`. No database row, no worker. Mounted in
main.py with one include_router line.

Spam guards: strict field validation (no CR/LF in anything that reaches a
header), a hidden `website` honeypot, and an in-memory per-IP + global
rate limit.
"""

import html
import ipaddress
import logging
import os
import re
import threading
import time
from collections import deque
from typing import Annotated, Literal

import mailer
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

logger = logging.getLogger(__name__)

router = APIRouter()

CONTACT_TEAM_EMAIL = os.environ.get(
    "CONTACT_TEAM_EMAIL",
    "harsha.gelli@wavemaker.com,pavan.kumar@wavemaker.com,sailaja.poranki@wavemaker.com",
)


def team_recipients() -> list[str]:
    return [addr.strip() for addr in CONTACT_TEAM_EMAIL.split(",") if addr.strip()]


# Same values and labels as the dialog's INTERESTS list.
INTEREST_LABELS: dict[str, str] = {
    "demo": "Product demo",
    "pilot": "Pilot or proof of concept",
    "pricing": "Pricing and licensing",
    "enterprise": "Enterprise deployment",
    "partnership": "Partnership",
    "other": "Something else",
}
Interest = Literal["demo", "pilot", "pricing", "enterprise", "partnership", "other"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Any control character (CR/LF included) — blocks email header injection
# through name/email/company, which reach the Subject and Reply-To headers.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# The free-text message may keep line breaks and tabs, nothing else.
_MESSAGE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

Line = Annotated[str, StringConstraints(strip_whitespace=True)]


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[Line, StringConstraints(min_length=1, max_length=100)]
    email: Annotated[Line, StringConstraints(min_length=3, max_length=254)]
    company: Annotated[Line, StringConstraints(min_length=1, max_length=150)]
    role: Annotated[Line, StringConstraints(max_length=100)] = ""
    interest: Interest
    message: Annotated[Line, StringConstraints(max_length=2000)] = ""
    # Honeypot: hidden from people, so only a bot fills it.
    website: Annotated[str, StringConstraints(max_length=500)] = ""

    @field_validator("name", "email", "company", "role")
    @classmethod
    def _single_line(cls, value: str) -> str:
        if _CONTROL_RE.search(value):
            raise ValueError("must be a single line of text")
        return value

    @field_validator("message")
    @classmethod
    def _plain_message(cls, value: str) -> str:
        if _MESSAGE_CONTROL_RE.search(value):
            raise ValueError("contains characters that aren't allowed")
        return value

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError("must be a valid email address")
        return value


# --- Rate limiting ---

PER_IP_LIMIT, PER_IP_WINDOW = 3, 10 * 60
GLOBAL_LIMIT, GLOBAL_WINDOW = 30, 60 * 60

# ponytail: per-process, in-memory sliding windows — each API replica (and
# each restart) keeps its own counts, so the real ceiling is limit × replicas.
# A shared limit needs Redis or a Postgres counter table; add a CAPTCHA if
# spam still gets through.
_lock = threading.Lock()
_per_ip: dict[str, deque[float]] = {}
_global: deque[float] = deque()


def reset_rate_limits() -> None:
    with _lock:
        _per_ip.clear()
        _global.clear()


def _prune(hits: deque[float], window: float, now: float) -> None:
    while hits and now - hits[0] >= window:
        hits.popleft()


def _take_slot(ip: str) -> bool:
    """Records one enquiry for `ip`; False (nothing recorded) if either the
    per-IP or the global window is already full."""
    now = time.monotonic()
    with _lock:
        _prune(_global, GLOBAL_WINDOW, now)
        ip_hits = _per_ip.setdefault(ip, deque())
        _prune(ip_hits, PER_IP_WINDOW, now)
        if len(ip_hits) >= PER_IP_LIMIT or len(_global) >= GLOBAL_LIMIT:
            return False
        ip_hits.append(now)
        _global.append(now)
        # Drop idle IPs so the dict can't grow without bound.
        for stale in [k for k, v in _per_ip.items() if not v]:
            del _per_ip[stale]
        return True


# X-Forwarded-For is only believed when the direct peer is our own
# ingress/proxy — from anyone else it is attacker-controlled.
TRUSTED_PROXY_CIDRS = os.environ.get(
    "TRUSTED_PROXY_CIDRS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8"
)


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [
        ipaddress.ip_network(cidr.strip(), strict=False)
        for cidr in TRUSTED_PROXY_CIDRS.split(",")
        if cidr.strip()
    ]


def _is_trusted(addr: str, networks: list) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    networks = _trusted_networks()
    if not _is_trusted(peer, networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    # Right to left: each trusted hop appended the address it saw; the first
    # untrusted one is the real client.
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _is_trusted(hop, networks):
            return hop
    return peer


# --- Email ---


def _rows(enquiry: ContactRequest) -> list[tuple[str, str]]:
    return [
        ("Name", enquiry.name),
        ("Work email", enquiry.email),
        ("Company", enquiry.company),
        ("Role", enquiry.role or "—"),
        ("Interested in", INTEREST_LABELS[enquiry.interest]),
    ]


def _contact_html(enquiry: ContactRequest) -> str:
    rows = "\n".join(
        f"""\
            <tr>
              <td style="padding:6px 16px 6px 0;font-size:13px;color:#777777;white-space:nowrap;vertical-align:top;">{html.escape(label)}</td>
              <td style="padding:6px 0;font-size:14px;color:#1a1a1a;">{html.escape(value)}</td>
            </tr>"""
        for label, value in _rows(enquiry)
    )
    message = html.escape(enquiry.message).replace("\n", "<br>") if enquiry.message else "—"
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f5f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f6;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="background:#ffffff;border-bottom:1px solid #e8eaec;padding:24px 32px;">
{mailer.EMAIL_HEADER}
        </td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 20px;font-size:16px;font-weight:600;color:#1a1a1a;">New enquiry from the Vantage website</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
{rows}
          </table>
          <p style="margin:0 0 8px;font-size:13px;color:#777777;">How can we help?</p>
          <p style="margin:0 0 28px;font-size:14px;color:#1a1a1a;line-height:1.5;">{message}</p>
          <p style="margin:0;font-size:12px;color:#999999;">Reply to this email to answer {html.escape(enquiry.name)} directly.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _contact_text(enquiry: ContactRequest) -> str:
    lines = [f"{label}: {value}" for label, value in _rows(enquiry)]
    return (
        "New enquiry from the Vantage website\n\n"
        + "\n".join(lines)
        + f"\n\nHow can we help?\n{enquiry.message or '—'}\n\n"
        + f"Reply to this email to answer {enquiry.name} directly."
    )


def send_contact_email(enquiry: ContactRequest) -> None:
    if not mailer.smtp_configured():
        # ponytail: dev fallback, no SMTP configured — log that an enquiry
        # arrived (no visitor details) instead of failing, same as
        # invites/password reset. Set SMTP_HOST etc. to actually send.
        logger.info(
            "contact enquiry received (SMTP not configured): interest=%s", enquiry.interest
        )
        return
    mailer.send_email(
        ", ".join(team_recipients()),
        f"New Vantage enquiry from {enquiry.name} ({enquiry.company})",
        _contact_text(enquiry),
        _contact_html(enquiry),
        reply_to=enquiry.email,
    )


@router.post("/contact", status_code=202)
def submit_contact(payload: ContactRequest, request: Request) -> dict[str, str]:
    """Public — no session. A filled honeypot gets the same 202 as a real
    enquiry, so a bot can't tell it was dropped."""
    if payload.website:
        return {"status": "ok"}
    if not _take_slot(client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many enquiries. Please try again later.")
    try:
        send_contact_email(payload)
    except Exception as exc:
        # Only the error type — never the visitor's details or SMTP settings.
        logger.error("contact enquiry email failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="We couldn't send your message.") from None
    return {"status": "ok"}
