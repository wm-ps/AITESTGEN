"""Every Explorer event reaches the worker log (not only phases), at a level
you can search for, with anything typed into a secret-looking field masked —
so a deployed run can be diagnosed from its logs alone."""

import logging
import uuid

import pytest
from explorer_worker import journal


class _NoDb:
    def __enter__(self) -> _NoDb:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def add(self, row: object) -> None:
        pass

    def commit(self) -> None:
        pass


def test_every_event_kind_is_logged_with_its_level(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(journal, "Session", lambda engine: _NoDb())
    log = journal.Journal(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger="explorer_worker.journal"):
        log.event(
            "thought", "Left out: Create a lead", "Breaking it on purpose didn't make it fail"
        )
        log.event("error", "Couldn't sign in", "The login screen was still showing")
        log.event("health", "Slow screen", "Took 9.1s to settle")
    by_title = {r.getMessage().split(": ", 1)[1].split(" — ")[0]: r for r in caplog.records}
    assert "didn't make it fail" in by_title["Left out: Create a lead"].getMessage()
    assert by_title["Left out: Create a lead"].levelno == logging.INFO
    assert by_title["Couldn't sign in"].levelno == logging.ERROR
    assert by_title["Slow screen"].levelno == logging.WARNING


def test_secret_entries_are_masked_in_the_log() -> None:
    masked = journal._masked("Email = ana@x.com; Password = Hunter2!; Shipping address = 1 Main St")
    assert "Hunter2!" not in masked
    assert "Password = ***" in masked
    assert "ana@x.com" in masked and "1 Main St" in masked
    assert journal._masked("PIN: 4321") == "PIN: ***"
