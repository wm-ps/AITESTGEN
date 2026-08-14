"""Unit tests for client.py (Story 2.8 made S3 the only backend; the MinIO
branch this once covered was removed once local dev also moved to real S3).

Real-dependency verification (a live S3 put/get round-trip) stays in
apps/workers/discovery/tests/test_discovery_activity_integration.py.
"""

import uuid

from object_store import client as object_store_module
from object_store.client import ObjectStore


class _FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str, bytes]] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803 (boto3 kwarg casing)
        self.puts.append((Bucket, Key, Body))

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803
        for bucket, key, body in self.puts:
            if bucket == Bucket and key == Key:
                return {"Body": _FakeBody(body)}
        raise KeyError(Key)


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def test_put_then_get_round_trips_through_s3_backend(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()

    assert store._bucket == "prod-bucket"
    key = store.put(b"hello", uuid.uuid4())
    assert store.get(key) == b"hello"


def test_put_test_artifact_uses_test_runs_prefix(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()
    test_run_id = uuid.uuid4()

    key = store.put_test_artifact(b"screenshot-bytes", test_run_id)

    assert key.startswith(f"test-runs/{test_run_id}/")
    assert store.get(key) == b"screenshot-bytes"
