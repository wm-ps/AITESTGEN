"""A run on several browsers has one TestResult per test per browser, but its
counters are per test: a test counts once, as its worst outcome across its
browsers, so the numbers agree with the run's rows and `total_count`."""

import uuid

from domain import TestResult, count_tests, tally_result_counts


def _result(scenario: uuid.UUID, browser: str, status: str) -> TestResult:
    return TestResult(
        test_run_id=uuid.uuid4(),
        test_asset_id=uuid.uuid4(),
        scenario_id=scenario,
        browser=browser,
        status=status,
    )


def _tally(*rows: tuple[uuid.UUID, str, str]) -> dict[str, int]:
    return tally_result_counts([_result(*row) for row in rows])


def test_a_one_browser_run_counts_each_result() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    assert _tally((a, "chromium", "passed"), (b, "chromium", "failed")) == {
        "passed": 1,
        "failed": 1,
        "timed_out": 0,
        "errored": 0,
        "blocked": 0,
    }


def test_a_test_counts_once_across_its_browsers() -> None:
    a = uuid.uuid4()
    results = [_result(a, b, "passed") for b in ("chromium", "firefox", "webkit")]

    assert count_tests(results) == 1
    assert tally_result_counts(results)["passed"] == 1


def test_failing_on_any_browser_fails_the_test() -> None:
    a = uuid.uuid4()

    counts = _tally((a, "chromium", "passed"), (a, "firefox", "failed"), (a, "webkit", "passed"))

    assert (counts["passed"], counts["failed"]) == (0, 1)


def test_the_failure_kind_is_failed_then_timed_out_then_errored() -> None:
    a = uuid.uuid4()

    assert _tally((a, "chromium", "errored"), (a, "firefox", "timed_out"))["timed_out"] == 1
    assert _tally((a, "chromium", "errored"), (a, "firefox", "failed"))["failed"] == 1


def test_a_test_still_running_on_one_browser_is_not_counted_yet() -> None:
    a = uuid.uuid4()

    assert sum(_tally((a, "chromium", "passed"), (a, "firefox", "pending")).values()) == 0


def test_a_test_skipped_on_a_browser_is_skipped_not_passed() -> None:
    a = uuid.uuid4()

    counts = _tally((a, "chromium", "passed"), (a, "firefox", "blocked"))

    assert (counts["passed"], counts["blocked"]) == (0, 1)


def test_a_cancelled_test_is_in_no_bucket() -> None:
    a = uuid.uuid4()

    assert sum(_tally((a, "chromium", "passed"), (a, "firefox", "cancelled")).values()) == 0


def test_tests_are_counted_separately() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = [
        (a, "chromium", "passed"),
        (a, "firefox", "passed"),
        (b, "chromium", "passed"),
        (b, "firefox", "failed"),
    ]

    counts = _tally(*rows)

    assert (counts["passed"], counts["failed"]) == (1, 1)
    assert count_tests([_result(*row) for row in rows]) == 2
