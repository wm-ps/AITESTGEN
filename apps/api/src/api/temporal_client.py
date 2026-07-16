"""Temporal client wiring — Story 1.1 scaffold.

Confirms `apps/api` can start and confirm completion of a Temporal workflow.
No real trigger endpoint exists yet (not required until Epic 2/3) — see
`scripts/temporal_smoke_test.py` for the dev-only proof-of-life check.
"""

import os

from temporalio.client import Client
from workflows import GENERATION_TASK_QUEUE

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")

__all__ = ["GENERATION_TASK_QUEUE", "TEMPORAL_ADDRESS", "get_temporal_client"]


async def get_temporal_client() -> Client:
    return await Client.connect(TEMPORAL_ADDRESS)
