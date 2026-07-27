"""GCS object storage unit tests (mocked client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.services.storage import (
    GcsNotFound,
    GcsObjectStorage,
    InfectedScanner,
    ScanResult,
    get_object_storage,
)


class _FakeBlob:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self._store = store
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str | None = None) -> None:
        _ = content_type
        self._store[self.name] = data

    def download_as_bytes(self) -> bytes:
        if self.name not in self._store:
            raise GcsNotFound("missing")
        return self._store[self.name]

    def delete(self) -> None:
        if self.name not in self._store:
            raise GcsNotFound("missing")
        del self._store[self.name]


class _FakeBucket:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._store, name)


def test_gcs_put_get_delete() -> None:
    bucket = _FakeBucket()
    store = GcsObjectStorage(bucket=bucket, documents_prefix="world-skills")
    obj = store.put(b"hello", prefix="cycles/1/docs", filename="a.txt")
    assert obj.key == "cycles/1/docs/a.txt"
    assert obj.path is None
    assert obj.size == 5
    assert "world-skills/cycles/1/docs/a.txt" in bucket._store
    assert store.get(obj.key) == b"hello"
    store.delete(obj.key)
    with pytest.raises(AppError) as exc:
        store.get(obj.key)
    assert exc.value.code == "FILE_NOT_FOUND"


def test_gcs_append_chunk_and_offset_mismatch() -> None:
    bucket = _FakeBucket()
    store = GcsObjectStorage(bucket=bucket, documents_prefix="")
    key = "uploads/chunk.bin"
    assert store.append_chunk(key, b"ab", expected_offset=0) == 2
    assert store.append_chunk(key, b"cd", expected_offset=2) == 4
    assert store.get(key) == b"abcd"
    with pytest.raises(AppError) as exc:
        store.append_chunk(key, b"x", expected_offset=1)
    assert exc.value.code == "UPLOAD_OFFSET_MISMATCH"


def test_gcs_put_raw_quarantine_on_infect() -> None:
    bucket = _FakeBucket()
    store = GcsObjectStorage(bucket=bucket, scanner=InfectedScanner(), documents_prefix="pfx")
    stored, result = store.put_raw(b"virus", prefix="arts", filename="bad.bin")
    assert result == ScanResult.INFECTED
    assert stored.key.startswith("quarantine/")
    assert store.get(stored.key) == b"virus"


def test_gcs_put_raises_on_infect_without_quarantine() -> None:
    bucket = _FakeBucket()
    store = GcsObjectStorage(bucket=bucket, scanner=InfectedScanner(), documents_prefix="")
    with pytest.raises(AppError) as exc:
        store.put(b"virus")
    assert exc.value.code == "FILE_INFECTED"


def test_get_object_storage_selects_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "storage_backend", "gcs")
    monkeypatch.setattr(settings, "gcs_bucket_name", "test-bucket")
    monkeypatch.setattr(settings, "gcs_project_id", "proj")
    monkeypatch.setattr(settings, "gcs_credentials_path", "")

    fake_client = MagicMock()
    fake_bucket = _FakeBucket()
    fake_client.bucket.return_value = fake_bucket

    monkeypatch.setattr("app.services.storage.gcs_storage.Client", MagicMock(return_value=fake_client))
    store = get_object_storage()
    assert isinstance(store, GcsObjectStorage)
    obj = store.put(b"z", filename="z.bin")
    assert store.get(obj.key) == b"z"
