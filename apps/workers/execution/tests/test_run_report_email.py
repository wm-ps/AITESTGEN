"""Run-completed email rendering — pure, no database or SMTP."""

import html as html_lib
from datetime import UTC, datetime, timedelta

import pytest
from execution_worker.run_report_email import (
    MAX_LISTED_FAILURES,
    FailedTest,
    RunCounts,
    RunEmail,
    build_email,
    format_duration,
    headline_of,
    outcome_of,
    pass_rate_of,
    short_error,
)

START = datetime(2026, 10, 19, 14, 2, tzinfo=UTC)


def _email(counts: RunCounts, **overrides) -> RunEmail:
    fields = dict(
        application_id="11111111-1111-1111-1111-111111111111",
        test_run_id="22222222-2222-2222-2222-222222222222",
        app_name="digi bank",
        run_number=12,
        counts=counts,
        started_at=START,
        completed_at=START + timedelta(minutes=4, seconds=32),
        target_url="https://bank.example.com",
        triggered_by_name="Sam",
        scheduled=False,
        report_available=True,
        base_url="https://vantage.example.com",
        failed_tests=[],
    )
    fields.update(overrides)
    return RunEmail(**fields)


@pytest.mark.parametrize(
    ("counts", "outcome", "rate", "headline", "subject_mark"),
    [
        (RunCounts(total=20, passed=20), "passed", 100, "All 20 tests passed", "✓"),
        (RunCounts(total=1, passed=1), "passed", 100, "The test passed", "✓"),
        # Blocked never started: out of the denominator, still all passed.
        (RunCounts(total=22, passed=20, blocked=2), "passed", 100, "All 20 tests passed", "✓"),
        (RunCounts(total=20, passed=18, failed=2), "failed", 90, "2 of 20 tests didn't pass", "✕"),
        (RunCounts(total=3, passed=0, timed_out=3), "failed", 0, "3 of 3 tests didn't pass", "✕"),
        # Errored next to a pass is still a failure, never "all passed".
        (RunCounts(total=5, passed=4, errored=1), "failed", 80, "1 of 5 tests didn't pass", "✕"),
        # Floored: 99.5% must not read as 100%.
        (
            RunCounts(total=200, passed=199, failed=1),
            "failed",
            99,
            "1 of 200 tests didn't pass",
            "✕",
        ),
        # Nothing passed and no assertion failure or timeout: couldn't run.
        (RunCounts(total=4, errored=4), "couldnt_run", 0, "Run couldn't complete", "!"),
        (RunCounts(total=3, blocked=3), "couldnt_run", None, "No tests ran", "!"),
        (RunCounts(), "couldnt_run", None, "No tests ran", "!"),
    ],
)
def test_outcome_pass_rate_headline_and_subject_agree(
    counts, outcome, rate, headline, subject_mark
) -> None:
    assert outcome_of(counts) == outcome
    assert pass_rate_of(counts) == rate
    assert headline_of(counts) == headline

    subject, text, html = build_email(_email(counts))
    assert subject == f"{subject_mark} Run #12 · digi bank — {headline}"
    assert html_lib.escape(headline) in html and headline in text
    if rate is None:
        assert "Pass rate not available" in html and "Pass rate not available" in text
    else:
        assert f"<strong>{rate}%</strong> pass rate" in html
        assert f"Pass rate: {rate}%" in text


def test_failed_run_lists_failures_first_with_journey_error_and_duration() -> None:
    failures = [
        FailedTest("Exports statements", "Statements", "errored", "Browser crashed", 1000),
        FailedTest(
            "Transfers funds",
            "Transfer funds",
            "timed_out",
            "Test timeout of 30000ms exceeded.",
            30_000,
        ),
        FailedTest(
            "Signs in",
            "Sign in",
            "failed",
            "\x1b[31mError: expect(locator).toBeVisible() failed\x1b[39m\n\nLocator: x\n  at y",
            12_400,
        ),
    ]
    subject, text, html = build_email(
        _email(
            RunCounts(total=20, passed=17, failed=1, timed_out=1, errored=1),
            failed_tests=failures,
        )
    )

    assert html.index("Signs in") < html.index("Transfers funds") < html.index("Exports statements")
    assert "Error: expect(locator).toBeVisible() failed" in html
    assert "\x1b" not in html and "Locator: x" not in html
    assert ">Sign in<" in html and "12s" in html and "30s" in html
    assert "- [Failed] Signs in (Sign in) · 12s" in text
    assert "    Error: expect(locator).toBeVisible() failed" in text


def test_failure_list_is_capped() -> None:
    failures = [FailedTest(f"Test {i:02}", None, "failed", None, None) for i in range(13)]
    _, text, html = build_email(
        _email(RunCounts(total=13, failed=13), failed_tests=failures)
    )
    assert html.count(">Failed</span>") == MAX_LISTED_FAILURES
    assert "+ 3 more tests not shown" in html and "+ 3 more tests not shown" in text
    assert "Test 09" in html and "Test 10" not in html


def test_every_database_value_is_escaped() -> None:
    evil = '<script>alert("x")</script>'
    _, text, html = build_email(
        _email(
            RunCounts(total=2, passed=1, failed=1),
            app_name=f"Shop {evil}",
            triggered_by_name=f"Mallory {evil}",
            target_url=f"https://x.test/?q={evil}",
            failed_tests=[
                FailedTest(f"Name {evil}", f"Journey {evil}", "failed", f"Err {evil}", 5)
            ],
        )
    )
    assert "<script>" not in html
    # title, banner, test name, journey, error, started by, target href + text
    assert html.count("&lt;script&gt;") == 8
    assert 'href="https://x.test/?q=&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"' in html
    # The plain-text part is never parsed as HTML, so it keeps the raw text.
    assert evil in text


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,hi", "not a url", None])
def test_only_http_target_urls_become_links(url) -> None:
    _, _, html = build_email(_email(RunCounts(total=1, passed=1), target_url=url))
    target_cell = html.split(">Target</td>")[1].split("</td>")[0]
    assert "<a " not in target_cell
    assert ("—" if url is None else url.replace(",", ",")) in target_cell


def test_links_go_through_vantage_routes() -> None:
    _, text, html = build_email(_email(RunCounts(total=1, passed=1)))
    run = (
        "https://vantage.example.com/applications/11111111-1111-1111-1111-111111111111"
        "/test-runs/22222222-2222-2222-2222-222222222222"
    )
    assert f'href="{run}/report"' in html and f'href="{run}"' in html
    assert f"View report: {run}/report" in text and f"Open in Vantage: {run}" in text
    assert "amazonaws" not in html


def test_no_report_means_no_report_button() -> None:
    _, text, html = build_email(_email(RunCounts(total=1, passed=1), report_available=False))
    assert "View report" not in html and "View report" not in text
    assert "The detailed report isn't available for this run." in html
    assert ">Open in Vantage</a>" in html


def test_scheduled_run_names_the_schedule() -> None:
    _, text, html = build_email(
        _email(RunCounts(total=1, passed=1), scheduled=True, triggered_by_name="Nightly")
    )
    assert "you created the schedule “Nightly”" in html
    assert "Started by: Schedule “Nightly”" in text and "Trigger: Scheduled" in text


def test_details_and_no_healing_language() -> None:
    _, text, html = build_email(_email(RunCounts(total=3, passed=3)))
    assert "19 Oct 2026, 14:02 UTC" in html and "4m 32s" in html
    assert "Started by: Sam" in text and "Trigger: Manual" in text
    for part in (html, text):
        assert "heal" not in part.lower() and "flaky" not in part.lower()


def test_subject_stays_on_one_line() -> None:
    subject, _, _ = build_email(_email(RunCounts(total=1, passed=1), app_name="Shop\r\nBcc: x@y"))
    assert "\n" not in subject and "\r" not in subject


def test_small_helpers() -> None:
    assert short_error(None) is None
    assert short_error("\n\n  first line  \nsecond") == "first line"
    assert len(short_error("x" * 500)) == 140
    assert format_duration(None) == "—"
    assert format_duration(400) == "<1s"
    assert format_duration(272_000) == "4m 32s"
    assert format_duration(3_720_000) == "1h 2m"


def test_failures_show_their_plain_description_and_the_root_cause() -> None:
    email = _email(
        RunCounts(total=3, failed=3),
        failed_tests=[
            FailedTest(
                "Submits a claim", None, "failed", "TimeoutError: locator.click: Timeout 15000ms", 10,
                description='Couldn\'t click the "Submit" button',
            ),
            FailedTest("Exports statements", None, "failed", "Error: something odd", 10),
        ],
        root_cause="3 of 3 failed tests have the same cause — Vantage couldn't sign in to the app.",
    )

    _, text, html = build_email(email)

    for body in (text, html_lib.unescape(html)):
        assert 'Couldn\'t click the "Submit" button' in body
        assert "TimeoutError" not in body  # replaced by its description
        assert "something odd" in body  # no description -> the existing short error
        assert "have the same cause — Vantage couldn't sign in to the app." in body
