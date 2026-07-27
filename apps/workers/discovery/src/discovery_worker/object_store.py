"""Object-storage abstraction for Page screenshot binaries (Story 2.2, Task 2).

Architecture (AD-8) fixes the *shape* — binary artifacts (screenshots,
DOM snapshots) referenced by an object-storage key, never stored inline in
Postgres — but names no formal Protocol port for the backend provider (unlike
`AIProvider`/`SecretsClient`). The provider choice is resolved by Story 2.8:
AWS S3 in production, MinIO unchanged for local dev/CI (S3-compatible,
trivial locally/in CI, no code-path difference for callers).

Backend is selected by configuration, not by caller-visible branching:
`AWS_S3_BUCKET` set -> boto3 against real S3; otherwise -> MinIO (local/CI
default, unchanged from Story 2.2). `put`/`get` keep the exact same
signature either way.

Lives inside `apps/workers/discovery` rather than a new top-level package —
Story 1.1's Structural Seed doesn't reserve one for object storage.
"""

import os
import uuid
from io import BytesIO
from typing import Any

import boto3
import urllib3
from botocore.config import Config as BotoConfig
from minio import Minio

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "discovery-evidence")

# Unset in local dev/CI on purpose — its presence is what selects the S3
# backend below (Story 2.8). Credentials are resolved by boto3's normal
# chain (env vars / IRSA / Pod Identity / instance profile), not read here.
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# minio's default http_client has no timeout at all (urllib3's own default) —
# a stalled connection to MinIO (container paused, Docker network blip) would
# otherwise block whatever thread calls `put`/`get` indefinitely. Observed
# live: this was blocking the crawler's asyncio event loop outright since
# `put` used to be called inline (2026-07-21); now that it's off-loaded via
# `asyncio.to_thread`, a bound still matters so a stuck call frees its thread
# instead of parking it forever. boto3 gets the same bound for the same
# reason (Story 2.8) — its defaults are no more trustworthy on a network blip.
_HTTP_CLIENT = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=30))
_S3_CONFIG = BotoConfig(connect_timeout=5, read_timeout=30)


class ObjectStore:
    def __init__(self, client: Minio | None = None) -> None:
        self._minio_client: Minio | None = None
        # boto3 ships no inline type stubs — `Any` reflects that honestly
        # rather than fighting pyright over an untyped SDK.
        self._s3_client: Any = None

        if AWS_S3_BUCKET:
            self._backend = "s3"
            self._bucket = AWS_S3_BUCKET
            self._s3_client = boto3.client("s3", region_name=AWS_REGION, config=_S3_CONFIG)
            return

        self._backend = "minio"
        self._bucket = MINIO_BUCKET
        self._minio_client = client or Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
            http_client=_HTTP_CLIENT,
        )
        if not self._minio_client.bucket_exists(MINIO_BUCKET):
            self._minio_client.make_bucket(MINIO_BUCKET)

    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        key = f"discovery-runs/{discovery_run_id}/{uuid.uuid4()}"
        if self._backend == "s3":
            self._s3_client.put_object(Bucket=self._bucket, Key=key, Body=data)
            return key
        assert self._minio_client is not None
        self._minio_client.put_object(self._bucket, key, BytesIO(data), length=len(data))
        return key

    def get(self, key: str) -> bytes:
        if self._backend == "s3":
            return self._s3_client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        assert self._minio_client is not None
        response = self._minio_client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
