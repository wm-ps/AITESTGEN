"""Object-storage abstraction for Page screenshot binaries (Story 2.2, Task 2).

Architecture (AD-8) fixes the *shape* — binary artifacts (screenshots,
DOM snapshots) referenced by an object-storage key, never stored inline in
Postgres — but names no formal Protocol port for the backend provider (unlike
`AIProvider`/`SecretsClient`) and explicitly defers the specific provider
choice (Deferred section). MinIO (S3-compatible, self-hostable, trivial
locally/in CI) is this build's default adapter; swapping to real S3/GCS/Azure
Blob later only touches this module, since they all speak the same
object-key model.

Lives inside `apps/workers/discovery` rather than a new top-level package —
Story 1.1's Structural Seed doesn't reserve one for object storage.
"""

import os
import uuid
from io import BytesIO

from minio import Minio

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "discovery-evidence")


class ObjectStore:
    def __init__(self, client: Minio | None = None) -> None:
        self._client = client or Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        if not self._client.bucket_exists(MINIO_BUCKET):
            self._client.make_bucket(MINIO_BUCKET)

    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        key = f"discovery-runs/{discovery_run_id}/{uuid.uuid4()}"
        self._client.put_object(MINIO_BUCKET, key, BytesIO(data), length=len(data))
        return key

    def get(self, key: str) -> bytes:
        response = self._client.get_object(MINIO_BUCKET, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
