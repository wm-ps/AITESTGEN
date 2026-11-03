"""Worker logging, the same in every worker:

- every log line carries the application it is about, `[app=<name>#<id8>]`
  (`<id8>` = the first 8 characters of the app's id, which tells two
  apps with the same name apart), so
  one app's story can be filtered out of a busy worker's log;
- one line when every activity starts and one when it ends, with how long it
  took, so a deployed run's logs show which stage took the time and which
  one failed.

How the app label is found, with no change to any activity: each activity
gets a fresh label (the interceptor), filled the first time that activity
loads an `Application` row (a SQLAlchemy load hook). Lines logged before
that (the activity's own "start" line) show `app=-`.

Kept out of `workflows/__init__` on purpose: workflow code is sandboxed and
never needs this; only each worker's `main()` does."""

import logging
import time
from contextvars import ContextVar
from typing import Any

from temporalio import activity
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
)

logger = logging.getLogger("activity")

LOG_FORMAT = "%(asctime)s %(levelname)s [app=%(app)s] %(name)s: %(message)s"

# A holder, not the label itself: work handed to a thread (`asyncio.to_thread`)
# runs in a copy of the context, and a label it sets must still reach the
# activity's own lines. The copy shares this same dict.
_SCOPE: ContextVar[dict[str, str | None] | None] = ContextVar("log_scope", default=None)


def start_log_scope() -> None:
    """A fresh app label for the work that follows (an activity, a session)."""
    _SCOPE.set({"app": None})


def label_app(name: str, external_id: object) -> None:
    scope = _SCOPE.get()
    if scope is None:
        return
    label = f"{name}#{str(external_id)[:8]}"
    if scope["app"] is None:
        scope["app"] = label
    elif scope["app"] != label:
        scope["app"] = "several apps"  # e.g. a clean-up sweep over every app


class _AppLabel(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        scope = _SCOPE.get()
        record.app = (scope or {}).get("app") or "-"
        return True


def configure_logging() -> None:
    """The worker's log setup: level, format and the app label."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.addFilter(_AppLabel())
    from domain import Application  # every worker has it; workflow code never runs this
    from sqlalchemy import event

    if not event.contains(Application, "load", _on_app_load):
        event.listen(Application, "load", _on_app_load)


def _on_app_load(app: Any, _context: Any) -> None:
    label_app(app.name, app.external_id)


def _subject(args: Any) -> str:
    """The run / item an activity is about, when its first argument is a
    plain id (most activities take `run_id: str`). Inputs that are objects
    are never logged: they may carry logins or test data."""
    first = args[0] if args else None
    return f" id={first}" if isinstance(first, str) and len(first) <= 64 else ""


class _LogEachActivity(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        start_log_scope()
        info = activity.info()
        where = f"{info.activity_type} workflow={info.workflow_id}{_subject(input.args)}"
        attempt = f" attempt={info.attempt}" if info.attempt > 1 else ""
        logger.info("start %s%s", where, attempt)
        started = time.monotonic()
        try:
            result = await self.next.execute_activity(input)
        except BaseException as exc:
            # Temporal itself logs the traceback; this line carries the timing.
            logger.warning(
                "failed %s after %.1fs: %s: %s",
                where,
                time.monotonic() - started,
                type(exc).__name__,
                (str(exc).splitlines() or [""])[0][:500],
            )
            raise
        logger.info("done %s in %.1fs", where, time.monotonic() - started)
        return result


class ActivityLogging(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _LogEachActivity(next)
