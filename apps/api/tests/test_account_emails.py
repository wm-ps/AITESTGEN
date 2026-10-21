"""Invite and password-reset emails after moving SMTP into the shared
`mailer` package — same fallback, same content. No database needed."""

import logging

import mailer
import pytest
from api.invites import send_invite_email
from api.password_reset import send_reset_email


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    sent: list[tuple] = []
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(
        "api.invites.send_email", lambda *args: sent.append(args)
    )
    monkeypatch.setattr(
        "api.password_reset.send_email", lambda *args: sent.append(args)
    )
    return sent


def test_without_smtp_both_emails_log_their_link(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(mailer, "SMTP_HOST", None)
    with caplog.at_level(logging.INFO):
        send_invite_email("new@example.com", "invite-token")
        send_reset_email("user@example.com", "Sam", "reset-token")

    assert "invite link for new@example.com: " in caplog.text
    assert "/accept-invite?token=invite-token" in caplog.text
    assert "password reset link for user@example.com: " in caplog.text
    assert "/reset-password?token=reset-token" in caplog.text


def test_invite_email_content(sent: list[tuple]) -> None:
    send_invite_email("new@example.com", "invite-token")

    [(to, subject, text, html)] = sent
    assert to == "new@example.com"
    assert subject == "You're invited to join Vantage"
    assert "Accept your invite: " in text and "/accept-invite?token=invite-token" in text
    assert "This link expires in 72 hours." in text
    assert ">Accept invite</a>" in html
    assert f"cid:{mailer.LOGO_CID}" in html


def test_reset_email_content(sent: list[tuple]) -> None:
    send_reset_email("user@example.com", "Sam", "reset-token")

    [(to, subject, text, html)] = sent
    assert to == "user@example.com"
    assert subject == "Reset your Vantage password"
    assert text.startswith("Hi Sam,\n\n")
    assert "/reset-password?token=reset-token" in text
    assert ">Reset password</a>" in html
    assert f"cid:{mailer.LOGO_CID}" in html
