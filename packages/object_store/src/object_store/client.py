"""Object-storage abstraction for binary artifacts (screenshots, DOM snapshots)
referenced by an object-storage key, never stored inline in Postgres (AD-8).

Shared between apps/workers/discovery (writes screenshots via `put`) and
apps/api (reads them back via `presigned_get_url` for the journey-steps
endpoint) — originally lived inside apps/workers/discovery alone (Story 2.2)
since no caller outside it needed object storage yet; extracted here once
apps/api became a second consumer. `put_test_artifact` (Run All Tests
feature) is a second writer, `apps/workers/execution`, storing
failure-capture screenshots/traces under a `test-runs/` prefix rather than
`discovery-runs/` — same bucket, same client, just a different key prefix
per producer.

Backend is real AWS S3 (Story 2.8) — the local/CI MinIO backend from Story 2.2
was removed once local dev also moved to pointing at real S3 (see this repo's
docker-compose.yml and README).
"""

import os
import uuid
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# boto3's default has no read timeout at all - a stalled S3 response would
# otherwise block whatever thread calls `put`/`get` indefinitely. `put` is
# off-loaded via `asyncio.to_thread` in the crawler, so a stuck call frees its
# thread instead of parking it forever (Story 2.8).
_S3_CONFIG = BotoConfig(connect_timeout=5, read_timeout=30)


class ObjectStore:
    def __init__(self) -> None:
        self._bucket = AWS_S3_BUCKET
        # boto3 ships no inline type stubs - `Any` reflects that honestly
        # rather than fighting pyright over an untyped SDK.
        self._s3_client: Any = boto3.client("s3", region_name=AWS_REGION, config=_S3_CONFIG)

    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        key = f"discovery-runs/{discovery_run_id}/{uuid.uuid4()}"
        self._s3_client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def put_test_artifact(self, data: bytes, test_run_id: uuid.UUID) -> str:
        key = f"test-runs/{test_run_id}/{uuid.uuid4()}"
        self._s3_client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        return self._s3_client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        return self._s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
