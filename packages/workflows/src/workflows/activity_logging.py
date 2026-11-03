"""One log line when every activity starts and one when it ends, with how
long it took — in every worker, through a single Temporal interceptor — so
a deployed run's logs show which stage took the time and which one failed.

Kept out of `workflows/__init__` on purpose: workflow code is sandboxed and
never needs this; only each worker's `Worker(..., interceptors=[...])`."""

import logging
import time
from typing import Any

from temporalio import activity
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
)

logger = logging.getLogger("activity")


def _subject(args: Any) -> str:
    """The run / item an activity is about, when its first argument is a
    plain id (most activities take `run_id: str`). Inputs that are objects
    are never logged: they may carry logins or test data."""
    first = args[0] if args else None
    return f" id={first}" if isinstance(first, str) and len(first) <= 64 else ""


class _LogEachActivity(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
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
