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
        self.puts: list[tuple[str, str, bytes, str]] = []
        self.presign_calls: list[tuple[str, dict, int]] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:  # noqa: N803 (boto3 kwarg casing)
        self.puts.append((Bucket, Key, Body, ContentType))

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803
        for bucket, key, body, _content_type in self.puts:
            if bucket == Bucket and key == Key:
                return {"Body": _FakeBody(body)}
        raise KeyError(Key)

    def generate_presigned_url(self, operation: str, Params: dict, ExpiresIn: int) -> str:  # noqa: N803
        self.presign_calls.append((operation, Params, ExpiresIn))
        return f"https://presigned.example/{Params['Key']}"


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

    key = store.put_test_artifact(b"screenshot-bytes", test_run_id, content_type="image/png")

    assert key.startswith(f"test-runs/{test_run_id}/")
    assert store.get(key) == b"screenshot-bytes"


def test_put_sets_content_type_on_the_s3_object(monkeypatch):
    # Regression: previously neither `put` nor `put_test_artifact` passed
    # `ContentType` to `put_object`, so every object was served back by S3 as
    # the default `binary/octet-stream` — a downloaded screenshot/trace would
    # fail to open even though its bytes were correct.
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()
    store.put(b"hello", uuid.uuid4())
    store.put_test_artifact(b"trace-bytes", uuid.uuid4(), content_type="application/zip")

    assert fake_s3.puts[0][3] == "image/png"
    assert fake_s3.puts[1][3] == "application/zip"


def test_presigned_get_url_overrides_response_content_type_and_filename(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()
    store.presigned_get_url(
        "test-runs/abc/def", response_content_type="image/png", filename="screenshot.png"
    )

    operation, params, _expires = fake_s3.presign_calls[0]
    assert operation == "get_object"
    assert params["ResponseContentType"] == "image/png"
    assert params["ResponseContentDisposition"] == 'inline; filename="screenshot.png"'


def test_presigned_get_url_omits_overrides_when_not_requested(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()
    store.presigned_get_url("discovery-runs/abc/def")

    _operation, params, _expires = fake_s3.presign_calls[0]
    assert "ResponseContentType" not in params
    assert "ResponseContentDisposition" not in params
