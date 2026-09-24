import pytest

from recording_worker.allocator import DisplayPortAllocator, ResourcePoolExhausted


def test_acquire_returns_distinct_displays_up_to_the_limit() -> None:
    allocator = DisplayPortAllocator(max_concurrent_sessions=3, base_display=100)
    allocated = [allocator.acquire() for _ in range(3)]
    assert [a.display for a in allocated] == [100, 101, 102]
    assert len({a.vnc_port for a in allocated}) == 3


def test_acquire_raises_once_the_pool_is_exhausted() -> None:
    allocator = DisplayPortAllocator(max_concurrent_sessions=1, base_display=100)
    allocator.acquire()
    with pytest.raises(ResourcePoolExhausted):
        allocator.acquire()


def test_release_frees_a_slot_for_reuse_without_disturbing_others() -> None:
    allocator = DisplayPortAllocator(max_concurrent_sessions=2, base_display=100)
    first = allocator.acquire()
    second = allocator.acquire()

    allocator.release(first.display)
    reused = allocator.acquire()

    assert reused.display == first.display
    with pytest.raises(ResourcePoolExhausted):
        allocator.acquire()
    # second's slot was never touched by releasing/reacquiring first's.
    assert second.display == 101


def test_release_of_an_unheld_display_is_a_no_op() -> None:
    allocator = DisplayPortAllocator(max_concurrent_sessions=1, base_display=100)
    allocator.release(100)
    allocator.acquire()
