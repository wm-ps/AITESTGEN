"""Local-disk staging area for one TestRun's assembled Playwright project.

New operational concern with no precedent in this codebase — neither
discovery nor generation ever writes a runnable npm project to disk.
`PrepareTestRunActivity` assembles the project once per `TestRun` (before
any `ExecuteTestActivity` runs, so there's no first-caller race to guard
with a file lock), `ExecuteTestActivity` calls run against it directly, and
`FinalizeTestRunActivity` removes it. `sweep_stale_project_dirs` is the
backstop for a `TestRun` whose `FinalizeTestRunActivity` itself never ran
(worker crash, an exhausted-retries infra failure) — called once at worker
startup so a crashed run's directory doesn't leak forever.
"""

import os
import shutil
import time
import uuid
from pathlib import Path

PROJECT_CACHE_ROOT = Path(
    os.environ.get("EXECUTION_PROJECT_CACHE_DIR", "/tmp/aitestgen-execution")
)

# A TestRun's own activities (prepare -> N execute -> finalize) should
# never legitimately take longer than this; a directory older than this at
# worker startup is from a run that crashed before cleaning up after itself.
STALE_AFTER_SECONDS = 6 * 60 * 60


def project_dir_for(test_run_id: uuid.UUID) -> Path:
    return PROJECT_CACHE_ROOT / str(test_run_id)


def cleanup_project_dir(test_run_id: uuid.UUID) -> None:
    shutil.rmtree(project_dir_for(test_run_id), ignore_errors=True)


def sweep_stale_project_dirs() -> None:
    if not PROJECT_CACHE_ROOT.exists():
        return
    now = time.time()
    for child in PROJECT_CACHE_ROOT.iterdir():
        if child.is_dir() and (now - child.stat().st_mtime) > STALE_AFTER_SECONDS:
            shutil.rmtree(child, ignore_errors=True)
