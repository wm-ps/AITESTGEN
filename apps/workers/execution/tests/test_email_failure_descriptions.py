"""`_email_failure_descriptions` — the run-completed email's plain-language
failures: rule titles, the API's cached AI title for an unknown error (the
worker never calls the LLM), nothing for an unknown error with no cache
(the email keeps its shortened error), heal rejections suppressed as before,
and the shared root cause. Real Postgres."""

import random
import string
import uuid

import execution_worker.activities as activities_module
import pytest
from domain import FailureExplanationRecord, TestResult
from execution_worker.db import engine, init_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from workflows import HEAL_TYPECHECK_ERROR_PREFIX, clean_error, error_fingerprint, redact_for_llm


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _result(status: str, message: str | None) -> TestResult:
    return TestResult(
        id=uuid.uuid4(),
        test_run_id=uuid.uuid4(),
        test_asset_id=uuid.uuid4(),
        scenario_id=uuid.uuid4(),
        status=status,
        error_message=message,
    )


def _unknown(word: str) -> str:
    return f"Error: the {word} widget exploded"


def test_descriptions_and_root_cause() -> None:
    init_db()
    cached_word = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    uncached_word = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    with Session(engine) as session:
        session.add(
            FailureExplanationRecord(
                error_fingerprint=error_fingerprint(
                    redact_for_llm(clean_error(_unknown(cached_word)))
                ),
                status="done",
                title="A widget failed",
                detail="It likely crashed.",
            )
        )
        session.commit()

    click = _result("failed", "TimeoutError: locator.click: Timeout 15000ms exceeded.")
    cached = _result("failed", _unknown(cached_word))
    uncached = _result("failed", _unknown(uncached_word))
    healed = _result("failed", HEAL_TYPECHECK_ERROR_PREFIX + "error TS2304")
    sign_ins = [
        _result("errored", "failed to prepare the test project: auth.setup.ts failed (exit 1):")
        for _ in range(6)
    ]

    with Session(engine) as session:
        descriptions, root_cause = activities_module._email_failure_descriptions(
            session, [click, cached, uncached, healed, *sign_ins]
        )

    assert descriptions[click.id] == "Couldn't click an element on the page"
    assert descriptions[cached.id] == "A widget failed"
    assert uncached.id not in descriptions  # the email falls back to short_error
    assert healed.id not in descriptions  # heal rejections stay suppressed
    assert descriptions[sign_ins[0].id] == "Couldn't sign in to the app"
    assert (
        root_cause
        == "6 of 10 failed tests have the same cause — Vantage couldn't sign in to the app."
    )


def test_no_root_cause_for_mixed_failures() -> None:
    init_db()
    results = [
        _result("failed", "Error: expect(locator).toBeVisible() failed"),
        _result("failed", "Error: locator not found"),
        _result("failed", "Error: expect(received).toBe(expected)"),
    ]
    with Session(engine) as session:
        _, root_cause = activities_module._email_failure_descriptions(session, results)
    assert root_cause is None
