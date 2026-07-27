"""Unit tests for object_store.py's backend selection (Story 2.8).

Real-dependency verification (a live MinIO put/get round-trip) stays in
test_discovery_activity_integration.py, skipped when MinIO isn't reachable.
These tests only cover the S3-vs-MinIO branch itself, with both clients
faked — no network, no real AWS/MinIO required.
"""

import uuid

from discovery_worker import object_store as object_store_module
from discovery_worker.object_store import ObjectStore


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


class _FakeMinioClient:
    def __init__(self) -> None:
        self.puts: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return True

    def make_bucket(self, bucket: str) -> None:
        raise AssertionError("should not be called — bucket_exists returned True")

    def put_object(self, bucket: str, key: str, stream, length: int) -> None:
        self.puts[(bucket, key)] = stream.read()

    def get_object(self, bucket: str, key: str):
        return _FakeMinioResponse(self.puts[(bucket, key)])


class _FakeMinioResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


def test_defaults_to_minio_backend_when_no_s3_bucket_configured(monkeypatch):
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", None)
    fake_minio = _FakeMinioClient()

    store = ObjectStore(client=fake_minio)  # type: ignore[arg-type]

    assert store._backend == "minio"
    key = store.put(b"hello", uuid.uuid4())
    assert store.get(key) == b"hello"


def test_uses_s3_backend_when_aws_s3_bucket_configured(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(object_store_module, "AWS_S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(object_store_module.boto3, "client", lambda *a, **k: fake_s3)

    store = ObjectStore()

    assert store._backend == "s3"
    assert store._bucket == "prod-bucket"
    key = store.put(b"hello", uuid.uuid4())
    assert store.get(key) == b"hello"
