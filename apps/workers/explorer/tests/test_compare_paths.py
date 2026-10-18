"""Repeat walk-throughs (missions.TASK_PASSES): which attempts count, and
what they say about the flow."""

from explorer_worker.missions import _compare_paths


class FakeJournal:
    def __init__(self) -> None:
        self.events: list[str] = []

    def event(self, kind: str, title: str, detail: str | None = None) -> None:
        self.events.append(title)


def test_same_path_with_retries_collapsed_is_stable() -> None:
    journal = FakeJournal()
    paths = [["Claim type", "Claim type", "Time"], ["Claim type", "Time"], ["Claim type", "Time"]]
    note = _compare_paths(journal, "Report", paths, ["final", "final", "final"])  # type: ignore[arg-type]
    assert note == "The flow was the same on all 3 attempts."


def test_stuck_attempt_is_not_repeatable_and_marks_nothing_conditional() -> None:
    journal = FakeJournal()
    paths = [["Claim type", "Property"], ["Claim type", "Property", "Time", "Review"]]
    note = _compare_paths(journal, "Report", paths, ["stuck", "final"])  # type: ignore[arg-type]
    assert "isn't repeatable" in note and "attempt 1 got stuck on Property" in note
    assert not any(e.startswith("Conditional") for e in journal.events)


def test_all_stuck_says_nothing() -> None:
    journal = FakeJournal()
    note = _compare_paths(journal, "Report", [["A"], ["A"]], ["stuck", "stuck"])  # type: ignore[arg-type]
    assert note == "" and journal.events == []


def test_send_button_is_recognised_however_it_is_labelled() -> None:
    from explorer_worker.pursue import _same_button

    assert _same_button("Send my report Icon Send my report", {"Send my report"})
    assert not _same_button("Continue", {"Send my report"})


def test_attempts_ending_on_different_screens_mark_nothing_conditional() -> None:
    journal = FakeJournal()
    paths = [
        ["Type", "Property"],
        ["Type", "Property", "Time", "Review"],
        ["Type", "Property", "Time", "Review"],
    ]
    note = _compare_paths(journal, "Report", paths, ["done", "final", "final"])  # type: ignore[arg-type]
    assert "isn't repeatable" in note and "The flow was the same on all 2 attempts." in note
    assert not any(e.startswith("Conditional") for e in journal.events)
