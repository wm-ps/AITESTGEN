"""Named config constants for Record and Play — every one of these was a
deliberate, cited decision in the approved plan, not a value invented here;
kept in one place so implementation never re-hardcodes them ad hoc.
"""

import os

# Xvfb screen size — must be large enough for Playwright's own Inspector
# window, which it launches at a *hardcoded* position/size of its own
# (--window-position=1020,10 --window-size=600,600, confirmed live via
# /proc inspection of a running session), independent of anything this
# service passes on Codegen's command line. That needs at least 1620x610
# to avoid clipping the Inspector's right/bottom edge — 1280x800 (this
# constant's original value) was ~340px too narrow. 1920x1080 matches
# discovery worker's own existing convention in this repo and leaves real
# margin for both the Inspector and the target-app browser window's normal
# Chrome UI (address bar/tabs) alongside it.
VIEWPORT_WIDTH = int(os.environ.get("RECORDING_VIEWPORT_WIDTH", "1920"))
VIEWPORT_HEIGHT = int(os.environ.get("RECORDING_VIEWPORT_HEIGHT", "1080"))

# Pre-connect token validity (mint -> first websocket connect).
TOKEN_EXPIRY_SECONDS = int(os.environ.get("RECORDING_TOKEN_EXPIRY_SECONDS", str(30 * 60)))

# A dropped vnc/control socket starts this grace timer before the session is
# torn down as abandoned — distinguishes a network blip/reconnect from an
# explicit Stop and Save (plan §3).
RECONNECT_GRACE_SECONDS = int(os.environ.get("RECORDING_RECONNECT_GRACE_SECONDS", "90"))

# Hard cap on total connected recording time — once hit, force through the
# same stop/save flow as an explicit Stop (plan §9).
MAX_RECORDING_SECONDS = int(os.environ.get("RECORDING_MAX_RECORDING_SECONDS", str(60 * 60)))

# Bounded wait for Codegen to exit cleanly (flushing its -o file) after
# SIGTERM before this service escalates to SIGKILL (plan §11).
STOP_GRACE_SECONDS = float(os.environ.get("RECORDING_STOP_GRACE_SECONDS", "10"))

# ponytail: a fixed-size in-memory pool (display numbers 100..100+N-1, each
# with its own pair of local ports) rather than a dynamically-scaling
# allocator or per-session k8s pods (round-2 decision: one long-running
# process, full per-session isolation within it, not one pod per session —
# that dynamic-provisioning capability doesn't exist in this repo today).
# Size this from measured per-session RSS/CPU once real usage exists (plan
# §9) — not guessed here.
MAX_CONCURRENT_SESSIONS = int(os.environ.get("RECORDING_MAX_CONCURRENT_SESSIONS", "4"))
BASE_DISPLAY_NUMBER = int(os.environ.get("RECORDING_BASE_DISPLAY_NUMBER", "100"))

# Base directory for each session's fully isolated working directory
# (Xvfb Xauthority, Codegen's -o output file — nothing shared across
# sessions, plan round-2 decision).
SESSION_WORK_ROOT = os.environ.get(
    "RECORDING_SESSION_WORK_ROOT", os.path.join(os.sep, "tmp", "recording-sessions")
)
