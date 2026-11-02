"""A step that makes no move and isn't done ("the list is still loading, I'll
wait") looks again, up to IDLE_LOOKS times, instead of ending the walk — a
walk once stopped on a loading list and never reached the rest of the task."""

from explorer_worker.pursue import IDLE_LOOKS, waiting_for_screen


def test_no_move_and_not_done_looks_again_a_few_times() -> None:
    waiting = {"thought": "Still loading, I'll wait", "advance": None, "done": False}
    assert IDLE_LOOKS == 3
    assert all(waiting_for_screen(waiting, n) for n in range(IDLE_LOOKS))
    assert not waiting_for_screen(waiting, IDLE_LOOKS)  # then it ends, as before


def test_a_move_or_done_is_never_a_wait() -> None:
    assert not waiting_for_screen({"advance": "Open in studio", "done": False}, 0)
    assert not waiting_for_screen({"advance": None, "done": True}, 0)
