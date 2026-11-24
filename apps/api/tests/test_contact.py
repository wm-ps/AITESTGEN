"""Public "Connect with our team" enquiry endpoint (api.contact). Mounted on
its own tiny app — no database, no SMTP server."""

import logging
from collections.abc import Iterator

import mailer
import pytest
from api import contact
from fastapi import FastAPI
from fastapi.testclient import TestClient

TEAM = "a@wavemaker.com,b@wavemaker.com,c@wavemaker.com"

VALID = {
    "name": "Sam Lee",
    "email": "sam@example.com",
    "company": "Acme",
    "role": "QA Lead",
    "interest": "pilot",
    "message": "We test a lot.\nCan we talk?",
}


@pytest.fixture(autouse=True)
def _fresh_limits() -> Iterator[None]:
    contact.reset_rate_limits()
    yield
    contact.reset_rate_limits()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    sent: list[tuple] = []
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(contact, "CONTACT_TEAM_EMAIL", TEAM)
    monkeypatch.setattr(
        mailer, "send_email", lambda *args, **kwargs: sent.append((*args, kwargs))
    )
    return sent


def make_client(peer: str = "203.0.113.5") -> TestClient:
    app = FastAPI()
    app.include_router(contact.router)
    return TestClient(app, client=(peer, 50000))


def test_enquiry_goes_to_every_team_address_with_reply_to_visitor(sent: list[tuple]) -> None:
    response = make_client().post("/contact", json=VALID)

    assert response.status_code == 202
    [(to, subject, text, html, kwargs)] = sent
    assert to == "a@wavemaker.com, b@wavemaker.com, c@wavemaker.com"
    assert subject == "New Vantage enquiry from Sam Lee (Acme)"
    assert kwargs == {"reply_to": "sam@example.com"}
    assert "Interested in: Pilot or proof of concept" in text
    assert "Role: QA Lead" in text
    assert f"cid:{mailer.LOGO_CID}" in html
    assert "We test a lot.<br>Can we talk?" in html


def test_user_values_are_html_escaped(sent: list[tuple]) -> None:
    payload = {**VALID, "message": "<script>x</script>", "company": "A&B"}
    make_client().post("/contact", json=payload)

    [(_to, _subject, _text, html, _kwargs)] = sent
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert "A&amp;B" in html


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"email": "not-an-email"},
        {"interest": "free-stuff"},
        {"company": "x" * 151},
        {"message": "x" * 2001},
        {"name": "Sam\r\nBcc: victim@example.com"},
        {"email": "sam@example.com\nBcc: victim@example.com"},
        {"company": "Acme\nX-Injected: 1"},
        {"unexpected": "field"},
    ],
)
def test_invalid_input_is_rejected_and_nothing_sent(sent: list[tuple], change: dict) -> None:
    response = make_client().post("/contact", json={**VALID, **change})

    assert response.status_code == 422
    assert sent == []


def test_missing_required_field_is_rejected(sent: list[tuple]) -> None:
    payload = {k: v for k, v in VALID.items() if k != "company"}
    assert make_client().post("/contact", json=payload).status_code == 422
    assert sent == []


def test_honeypot_looks_successful_but_sends_nothing_and_costs_no_slot(sent: list[tuple]) -> None:
    client = make_client()
    for _ in range(5):
        assert client.post("/contact", json={**VALID, "website": "http://spam"}).status_code == 202
    assert sent == []
    # The honeypot hits didn't use up this IP's real slots.
    assert client.post("/contact", json=VALID).status_code == 202


def test_per_ip_rate_limit(sent: list[tuple]) -> None:
    client = make_client()
    statuses = [client.post("/contact", json=VALID).status_code for _ in range(4)]

    assert statuses == [202, 202, 202, 429]
    assert len(sent) == 3
    # A different visitor is unaffected.
    assert make_client("198.51.100.7").post("/contact", json=VALID).status_code == 202


def test_global_rate_limit(sent: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contact, "GLOBAL_LIMIT", 2)
    assert make_client("198.51.100.1").post("/contact", json=VALID).status_code == 202
    assert make_client("198.51.100.2").post("/contact", json=VALID).status_code == 202
    assert make_client("198.51.100.3").post("/contact", json=VALID).status_code == 429


def test_forwarded_for_is_honoured_only_from_a_trusted_proxy(sent: list[tuple]) -> None:
    # Behind the ingress (private peer): each forwarded client gets its own limit.
    via_ingress = make_client("10.1.2.3")
    for visitor in ("198.51.100.10", "198.51.100.11"):
        for _ in range(3):
            response = via_ingress.post(
                "/contact", json=VALID, headers={"X-Forwarded-For": f"{visitor}, 10.9.9.9"}
            )
            assert response.status_code == 202

    # Straight from the internet: a spoofed header doesn't buy fresh slots.
    direct = make_client("203.0.113.50")
    statuses = [
        direct.post("/contact", json=VALID, headers={"X-Forwarded-For": f"192.0.2.{i}"}).status_code
        for i in range(4)
    ]
    assert statuses == [202, 202, 202, 429]


def test_smtp_failure_is_a_502_and_logs_no_visitor_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ConnectionRefusedError("smtp.test:587 refused for sam@example.com")

    monkeypatch.setattr(mailer, "send_email", boom)
    with caplog.at_level(logging.INFO):
        response = make_client().post("/contact", json=VALID)

    assert response.status_code == 502
    assert response.json() == {"detail": "We couldn't send your message."}
    assert "contact enquiry email failed: ConnectionRefusedError" in caplog.text
    assert "sam@example.com" not in caplog.text
    assert "Sam Lee" not in caplog.text


def test_without_smtp_the_enquiry_is_logged_not_sent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(mailer, "SMTP_HOST", None)
    calls: list = []
    monkeypatch.setattr(mailer, "send_email", lambda *a, **k: calls.append(a))
    with caplog.at_level(logging.INFO):
        response = make_client().post("/contact", json=VALID)

    assert response.status_code == 202
    assert calls == []
    assert "contact enquiry received (SMTP not configured)" in caplog.text
    assert "sam@example.com" not in caplog.text


def test_reply_to_header_is_set_on_the_real_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """mailer.send_email itself puts the visitor in Reply-To and every team
    address in To."""
    captured: list = []

    class FakeSMTP:
        def __init__(self, *_args: object) -> None: ...
        def __enter__(self) -> FakeSMTP:
            return self
        def __exit__(self, *_args: object) -> None: ...
        def starttls(self) -> None: ...
        def login(self, *_args: object) -> None: ...
        def send_message(self, message: object) -> None:
            captured.append(message)

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.send_email(
        "a@x.com, b@x.com", "Subject", "text", "<p>html</p>", reply_to="sam@example.com"
    )

    [message] = captured
    assert message["Reply-To"] == "sam@example.com"
    assert message["To"] == "a@x.com, b@x.com"
