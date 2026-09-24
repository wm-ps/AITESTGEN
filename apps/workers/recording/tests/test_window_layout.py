from recording_worker.window_layout import (
    INSPECTOR_HEIGHT,
    INSPECTOR_WIDTH,
    INSPECTOR_X,
    INSPECTOR_Y,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    TARGET_X,
    TARGET_Y,
    _descendants_from_map,
    _find_chromium_role_pid,
    _rects_overlap,
)


def test_separate_rectangles_do_not_overlap() -> None:
    assert not _rects_overlap((0, 0, 100, 100), (200, 200, 100, 100))


def test_touching_edges_do_not_count_as_overlap() -> None:
    # Adjacent, sharing an edge — exactly the target/inspector relationship
    # this module's own fixed constants are chosen to produce.
    assert not _rects_overlap((0, 0, 100, 100), (100, 0, 100, 100))


def test_overlapping_rectangles_are_detected() -> None:
    assert _rects_overlap((0, 0, 100, 100), (50, 50, 100, 100))


def test_one_rectangle_inside_another_is_detected() -> None:
    assert _rects_overlap((0, 0, 200, 200), (50, 50, 10, 10))


def test_default_target_and_inspector_slots_do_not_overlap() -> None:
    target = (TARGET_X, TARGET_Y, TARGET_WIDTH, TARGET_HEIGHT)
    inspector = (INSPECTOR_X, INSPECTOR_Y, INSPECTOR_WIDTH, INSPECTOR_HEIGHT)
    assert not _rects_overlap(target, inspector)


def test_descendants_from_map_walks_full_tree() -> None:
    # Matches the real tree observed live: codegen(25) -> node driver(26) ->
    # target chrome(38) -> its zygotes(45,46) -> a utility helper(88), and
    # node driver(26) -> inspector chrome(126) too.
    children_by_ppid = {25: [26], 26: [38, 126], 38: [45, 46], 46: [88]}
    assert _descendants_from_map(25, children_by_ppid) == {26, 38, 126, 45, 46, 88}


def test_descendants_from_map_excludes_reparented_processes() -> None:
    # Crashpad handlers get reparented to pid 1 once their spawning parent
    # exits (confirmed live) — they must never count as this session's own
    # descendants just because they belong to the same Chromium instance.
    children_by_ppid = {25: [26], 26: [38], 1: [128]}
    assert _descendants_from_map(25, children_by_ppid) == {26, 38}


def test_find_chromium_role_pid_identifies_target_and_inspector(monkeypatch) -> None:
    cmdlines = {
        38: "/chrome-linux64/chrome --no-sandbox --user-data-dir=/tmp/x --remote-debugging-pipe --no-startup-window",
        126: "/chrome-linux64/chrome --no-sandbox --app=data:text/html, --window-size=600,600 --window-position=1020,10 about:blank",
        45: "/chrome-linux64/chrome --type=zygote --no-sandbox",
        128: "/chrome-linux64/chrome_crashpad_handler --monitor-self",
    }
    monkeypatch.setattr(
        "recording_worker.window_layout._process_cmdline",
        lambda pid: cmdlines.get(pid, ""),
    )
    descendants = set(cmdlines)
    assert _find_chromium_role_pid(descendants, want_app_flag=False) == 38
    assert _find_chromium_role_pid(descendants, want_app_flag=True) == 126


def test_find_chromium_role_pid_requires_no_startup_window_for_target(monkeypatch) -> None:
    # A process that merely lacks `--app=` is not enough on its own to be
    # matched as the target — it must also positively carry
    # `--no-startup-window`, the real, positive signal Playwright launches
    # the target-app browser with (not just "isn't the Inspector").
    cmdlines = {
        38: "/chrome-linux64/chrome --no-sandbox --user-data-dir=/tmp/x --remote-debugging-pipe",
        45: "/chrome-linux64/chrome --type=zygote --no-sandbox",
    }
    monkeypatch.setattr(
        "recording_worker.window_layout._process_cmdline",
        lambda pid: cmdlines.get(pid, ""),
    )
    assert _find_chromium_role_pid(set(cmdlines), want_app_flag=False) is None
