"""Temporal client wiring for the discovery worker (Story 2.5).

`InferenceActivity` starts `GenerationWorkflow` per candidate Journey — an
Activity holding its own Temporal client to start further workflows is a
normal, supported pattern (distinct from the workflow-side client
prohibition in AD-2, which is about the *workflow* process never doing I/O).
Mirrors `api/temporal_client.py`'s same `TEMPORAL_ADDRESS` convention.
"""

import os

from temporalio.client import Client

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def get_temporal_client() -> Client:
    return await Client.connect(TEMPORAL_ADDRESS)
