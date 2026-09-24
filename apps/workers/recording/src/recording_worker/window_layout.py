"""Explicit, deterministic window layout for a recording session — there is
no window manager running under Xvfb (confirmed: only `xvfb`/`x11vnc`/
`nodejs` are installed; nothing else arbitrates window placement), so
nothing guarantees the target-app browser window and Codegen's own
Inspector window don't overlap unless this module positions them itself.

Identification never guesses, and never relies on "whichever window isn't
the other one" (that breaks the moment more than two windows legitimately
exist — e.g. the human opens a second tab/popup on the target site mid
-recording, which is normal, not an error):

- The Inspector's own top-level Chromium process is launched by Playwright
  with `--app=data:text/html` (confirmed live via `/proc` inspection of a
  running session earlier this conversation), and its page's own `<title>`
  is "Playwright Inspector" (confirmed directly in Playwright's bundled
  source, `.../driver/package/lib/vite/recorder/index.html:9`) — both
  signals are required to agree before anything is touched.
- The target-app's own top-level Chromium process has neither `--app=` nor
  a `--type=` flag (those mark internal helper processes — zygote,
  gpu-process, renderer, utility, crashpad handler — never the process that
  owns a session's top-level window; also confirmed live via the same
  `/proc` inspection).
- Both scans are restricted to this session's own process **tree**: every
  candidate must be a descendant of the `python -m playwright codegen`
  process this session itself spawned (`root_pid`), so a *different*,
  concurrently running session's windows are never at risk of being
  matched instead.

  Scoping by process *group* (the pgid `display.py`'s
  `join_process_group()` tracks for `killpg` teardown) was tried first and
  is wrong for this specific purpose: confirmed live that Chromium's own
  process tree (spawned by Playwright's Node driver, itself a child of the
  Python `codegen` process) is **not** a member of that process group at
  all — only `Xvfb`, `x11vnc`, and the two directly-spawned wrapper
  processes are. Both the target-app's and the Inspector's actual top-level
  Chromium processes are, however, confirmed live to be direct children of
  the same Node driver process (`ppid` matches it exactly) — a real process
  *tree* walk from `root_pid` finds them; pgid membership does not.

Best-effort throughout: a window-layout failure is logged clearly and never
aborts an otherwise-working recording session — this is cosmetic, not
functionally load-bearing.
"""

from __future__ import annotations

import asyncio
import logging
import os

from recording_worker.config import VIEWPORT_HEIGHT

logger = logging.getLogger(__name__)

INSPECTOR_TITLE = "Playwright Inspector"

# Codegen's Inspector is hardcoded by Playwright itself at this position and
# size (confirmed via /proc inspection of a running session). The target
# slot below is chosen so it can never overlap that box: full height, full
# width up to where the Inspector starts.
INSPECTOR_X = 1020
INSPECTOR_Y = 10
INSPECTOR_WIDTH = 600
INSPECTOR_HEIGHT = 600

TARGET_X = 0
TARGET_Y = 0
TARGET_WIDTH = INSPECTOR_X
TARGET_HEIGHT = VIEWPORT_HEIGHT

_SEARCH_TIMEOUT_SECONDS = 8.0
_POLL_INTERVAL_SECONDS = 0.25


async def _xdotool(display_env: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "xdotool",
        *args,
        env={**os.environ, "DISPLAY": display_env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return ""
    return stdout.decode(errors="replace").strip()


def _process_cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def _read_ppid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as f:
            stat = f.read()
    except OSError:
        return None
    # Format: "pid (comm) state ppid ..." — comm can itself contain spaces
    # or parentheses, so split on the *last* ')' rather than whitespace.
    after_comm = stat.rsplit(")", 1)[-1].split()
    if len(after_comm) < 2:
        return None
    try:
        return int(after_comm[1])
    except ValueError:
        return None


def _build_children_by_ppid() -> dict[int, list[int]]:
    children_by_ppid: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        ppid = _read_ppid(pid)
        if ppid is not None:
            children_by_ppid.setdefault(ppid, []).append(pid)
    return children_by_ppid


def _descendants_from_map(root_pid: int, children_by_ppid: dict[int, list[int]]) -> set[int]:
    descendants: set[int] = set()
    frontier = [root_pid]
    while frontier:
        pid = frontier.pop()
        for child in children_by_ppid.get(pid, []):
            if child not in descendants:
                descendants.add(child)
                frontier.append(child)
    return descendants


def _collect_descendant_pids(root_pid: int) -> set[int]:
    """Every live process descended from `root_pid` — a real process-tree
    walk, not a process-group membership check (confirmed live: Chromium's
    own tree, spawned by Playwright's Node driver, is not a member of this
    session's process group at all, even though it *is* a descendant of the
    `codegen` process this session spawned)."""
    return _descendants_from_map(root_pid, _build_children_by_ppid())


def _find_chromium_role_pid(descendant_pids: set[int], *, want_app_flag: bool) -> int | None:
    """This session's own top-level Chromium process (never a zygote/
    gpu-process/renderer/utility/crashpad helper).

    The Inspector is identified positively by `--app=` (confirmed live via
    `/proc` inspection). The target-app browser used to be identified only
    by the *absence* of `--app=` — an elimination, not a positive match.
    It's now identified positively too: Playwright launches it with
    `--no-startup-window` (confirmed present on the target's own cmdline
    and confirmed absent from the Inspector's, which instead ends in
    `about:blank` as its final argument, in this session's own `/proc`
    inspections). The absence of `--app=` is kept as a secondary check
    alongside it, not the primary signal on its own."""
    for pid in descendant_pids:
        cmdline = _process_cmdline(pid)
        if "/chrome" not in cmdline or "chrome_crashpad_handler" in cmdline:
            continue
        if "--type=" in cmdline:
            continue  # a helper process — never the one owning a top-level window
        if want_app_flag:
            if "--app=" in cmdline:
                return pid
        else:
            if "--no-startup-window" in cmdline and "--app=" not in cmdline:
                return pid
    return None


async def _find_window_ids_for_pid(display_env: str, pid: int) -> list[str]:
    output = await _xdotool(display_env, "search", "--onlyvisible", "--pid", str(pid))
    return [line for line in output.splitlines() if line.strip()]


async def _find_window_id_by_title(display_env: str, title: str) -> str | None:
    output = await _xdotool(display_env, "search", "--onlyvisible", "--name", f"^{title}$")
    ids = [line for line in output.splitlines() if line.strip()]
    return ids[0] if len(ids) == 1 else None


async def _get_geometry(display_env: str, window_id: str) -> tuple[int, int, int, int] | None:
    output = await _xdotool(display_env, "getwindowgeometry", "--shell", window_id)
    values: dict[str, int] = {}
    for line in output.splitlines():
        key, _, value = line.partition("=")
        try:
            values[key] = int(value)
        except ValueError:
            continue
    if not {"X", "Y", "WIDTH", "HEIGHT"} <= values.keys():
        return None
    return values["X"], values["Y"], values["WIDTH"], values["HEIGHT"]


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


async def layout_recording_windows(display_env: str, root_pid: int) -> None:
    """Positions the target-app browser window into a fixed slot that
    cannot overlap Codegen's own Inspector window, then verifies the
    result via real geometry queries. Never raises — a failure here should
    never abort an otherwise-working recording; every failure path logs a
    specific, actionable warning instead of guessing or staying silent.

    `root_pid` is the OS pid of the `python -m playwright codegen` process
    this session itself spawned — both Chromium instances (target-app and
    Inspector) are its descendants (via Playwright's own Node driver), even
    though neither is a member of this session's process *group*."""
    try:
        await _layout_recording_windows(display_env, root_pid)
    except Exception:
        logger.exception("window_layout: unexpected failure positioning session windows")


async def _layout_recording_windows(display_env: str, root_pid: int) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _SEARCH_TIMEOUT_SECONDS
    inspector_pid: int | None = None
    target_pid: int | None = None
    while loop.time() < deadline:
        descendants = _collect_descendant_pids(root_pid)
        inspector_pid = _find_chromium_role_pid(descendants, want_app_flag=True)
        target_pid = _find_chromium_role_pid(descendants, want_app_flag=False)
        if inspector_pid is not None and target_pid is not None:
            break
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    if inspector_pid is None or target_pid is None:
        logger.warning(
            "window_layout: could not identify both Chromium processes among "
            "descendants of pid %s (inspector_pid=%s, target_pid=%s) — skipping",
            root_pid,
            inspector_pid,
            target_pid,
        )
        return

    # Cross-check the Inspector two ways (process identity + its own known
    # page title) rather than trusting either signal alone.
    inspector_ids_by_pid = await _find_window_ids_for_pid(display_env, inspector_pid)
    inspector_id_by_title = await _find_window_id_by_title(display_env, INSPECTOR_TITLE)
    if not inspector_id_by_title or inspector_id_by_title not in inspector_ids_by_pid:
        logger.warning(
            "window_layout: Inspector process/title cross-check failed "
            "(windows for pid %s: %s, window titled %r: %s) — skipping",
            inspector_pid,
            inspector_ids_by_pid,
            INSPECTOR_TITLE,
            inspector_id_by_title,
        )
        return
    inspector_window_id = inspector_id_by_title

    target_ids = await _find_window_ids_for_pid(display_env, target_pid)
    if not target_ids:
        logger.warning(
            "window_layout: target-app browser (pid %s) has no window yet — skipping", target_pid
        )
        return
    if len(target_ids) > 1:
        logger.info(
            "window_layout: target-app browser has %d windows (the human likely "
            "opened a new tab/popup, which is expected) — positioning only the "
            "first, id %s",
            len(target_ids),
            target_ids[0],
        )
    target_window_id = sorted(target_ids, key=int)[0]

    if target_window_id == inspector_window_id:
        logger.warning(
            "window_layout: target and inspector resolved to the same window id "
            "(%s) — skipping",
            target_window_id,
        )
        return

    await _xdotool(display_env, "windowmove", target_window_id, str(TARGET_X), str(TARGET_Y))
    await _xdotool(display_env, "windowsize", target_window_id, str(TARGET_WIDTH), str(TARGET_HEIGHT))

    target_geom = await _get_geometry(display_env, target_window_id)
    inspector_geom = await _get_geometry(display_env, inspector_window_id)
    if target_geom is None or inspector_geom is None:
        logger.warning(
            "window_layout: could not verify geometry after positioning "
            "(target=%s, inspector=%s)",
            target_geom,
            inspector_geom,
        )
        return

    if _rects_overlap(target_geom, inspector_geom):
        logger.warning(
            "window_layout: target and inspector windows overlap after "
            "positioning — target=%s inspector=%s",
            target_geom,
            inspector_geom,
        )
        return

    logger.info(
        "window_layout: positioned and verified non-overlapping — target=%s inspector=%s",
        target_geom,
        inspector_geom,
    )
