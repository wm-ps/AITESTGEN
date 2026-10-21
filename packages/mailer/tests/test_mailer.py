import smtplib

import mailer
import pytest


class _FakeSMTP:
    sent: list = []
    fail_with: Exception | None = None

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        if _FakeSMTP.fail_with is not None:
            raise _FakeSMTP.fail_with
        _FakeSMTP.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch):
    _FakeSMTP.sent = []
    _FakeSMTP.fail_with = None
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def test_sends_text_and_html_with_the_inline_logo(fake_smtp) -> None:
    mailer.send_email("a@b.test", "Hello", "plain body", f"<p>html</p>{mailer.EMAIL_HEADER}")

    [message] = fake_smtp.sent
    assert message["To"] == "a@b.test"
    assert message["Subject"] == "Hello"
    assert "plain body" in message.get_body(("plain",)).get_content()
    html_part = message.get_body(("html",))
    assert "<p>html</p>" in html_part.get_content()
    [logo] = [p for p in message.walk() if p.get_content_type() == "image/png"]
    assert logo["Content-ID"] == f"<{mailer.LOGO_CID}>"
    assert f"cid:{mailer.LOGO_CID}" in html_part.get_content()


def test_raises_on_smtp_errors(fake_smtp) -> None:
    fake_smtp.fail_with = smtplib.SMTPRecipientsRefused({"a@b.test": (550, b"no")})
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        mailer.send_email("a@b.test", "Hello", "text", "<p>html</p>")


def test_smtp_configured_follows_smtp_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailer, "SMTP_HOST", None)
    assert not mailer.smtp_configured()
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")
    assert mailer.smtp_configured()
