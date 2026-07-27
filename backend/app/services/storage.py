"""Object storage (local filesystem or GCS) + injectable malware scan stub."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.config import settings
from app.core.errors import AppError

try:
    from google.cloud import storage as gcs_storage
    from google.cloud.exceptions import NotFound as GcsNotFound
except ImportError:  # pragma: no cover - optional until dependency installed
    gcs_storage = None
    GcsNotFound = Exception  # type: ignore[misc,assignment]

# Official EICAR antivirus test string (DoD: malware path tested with EICAR)
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScanResult(str, Enum):
    CLEAN = "clean"
    INFECTED = "infected"


@dataclass
class StoredObject:
    key: str
    path: Path | None
    size: int
    sha256: str


class MalwareScanner:
    def scan(self, data: bytes) -> ScanResult:
        if EICAR_SIGNATURE in data:
            return ScanResult.INFECTED
        return ScanResult.CLEAN


class InfectedScanner(MalwareScanner):
    def scan(self, data: bytes) -> ScanResult:
        _ = data
        return ScanResult.INFECTED


def _build_key(prefix: str, key_name: str) -> str:
    return f"{prefix.rstrip('/')}/{key_name}" if prefix else key_name


def _quarantine_prefix(prefix: str) -> str:
    return f"quarantine/{prefix.rstrip('/')}" if prefix else "quarantine"


@runtime_checkable
class ObjectStorage(Protocol):
    def put(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        quarantine_on_infect: bool = False,
    ) -> StoredObject: ...

    def put_raw(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        skip_scan: bool = False,
    ) -> tuple[StoredObject, ScanResult]: ...

    def append_chunk(self, key: str, data: bytes, *, expected_offset: int) -> int: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: str | Path | None = None, scanner: MalwareScanner | None = None) -> None:
        self.root = Path(root or settings.storage_root)
        self.scanner = scanner or MalwareScanner()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        quarantine_on_infect: bool = False,
    ) -> StoredObject:
        result = self.scanner.scan(data)
        infected = result == ScanResult.INFECTED

        key_name = filename or str(uuid.uuid4())
        if infected and quarantine_on_infect:
            prefix = _quarantine_prefix(prefix)
        elif infected:
            raise AppError("FILE_INFECTED", "Upload failed malware scan", status_code=400)

        key = _build_key(prefix, key_name)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        obj = StoredObject(key=key, path=path, size=len(data), sha256=digest)
        if infected:
            raise AppError(
                "FILE_INFECTED",
                "Upload failed malware scan; file quarantined — replace it",
                status_code=400,
            )
        return obj

    def put_raw(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        skip_scan: bool = False,
    ) -> tuple[StoredObject, ScanResult]:
        """Store bytes and return scan result without raising on infect (caller decides)."""
        result = ScanResult.CLEAN if skip_scan else self.scanner.scan(data)
        key_name = filename or str(uuid.uuid4())
        use_prefix = prefix
        if result == ScanResult.INFECTED:
            use_prefix = _quarantine_prefix(prefix)
        key = _build_key(use_prefix, key_name)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        return StoredObject(key=key, path=path, size=len(data), sha256=digest), result

    def append_chunk(self, key: str, data: bytes, *, expected_offset: int) -> int:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.stat().st_size if path.exists() else 0
        if current != expected_offset:
            raise AppError(
                "UPLOAD_OFFSET_MISMATCH",
                f"Expected offset {expected_offset}, have {current}",
                status_code=409,
            )
        with path.open("ab") as fh:
            fh.write(data)
        return current + len(data)

    def get(self, key: str) -> bytes:
        path = self.root / key
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", "Object not found", status_code=404)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            os.remove(path)


class GcsObjectStorage:
    """Google Cloud Storage backend with the same API as LocalObjectStorage."""

    def __init__(
        self,
        *,
        bucket: Any | None = None,
        scanner: MalwareScanner | None = None,
        documents_prefix: str | None = None,
    ) -> None:
        self.scanner = scanner or MalwareScanner()
        self._documents_prefix = (
            (documents_prefix if documents_prefix is not None else settings.gcs_documents_prefix) or ""
        ).strip().strip("/")
        self._bucket = bucket if bucket is not None else self._create_bucket()

    @staticmethod
    def _create_bucket() -> Any:
        if gcs_storage is None:
            raise AppError(
                "STORAGE_MISCONFIGURED",
                "google-cloud-storage is not installed",
                status_code=500,
            )
        if not settings.gcs_bucket_name:
            raise AppError(
                "STORAGE_MISCONFIGURED",
                "GCS bucket not configured (set GCS_BUCKET_NAME)",
                status_code=500,
            )
        project = settings.gcs_project_id or None
        if settings.gcs_credentials_path:
            client = gcs_storage.Client.from_service_account_json(
                settings.gcs_credentials_path,
                project=project,
            )
        else:
            client = gcs_storage.Client(project=project)
        return client.bucket(settings.gcs_bucket_name)

    def _object_name(self, key: str) -> str:
        key = key.lstrip("/")
        if self._documents_prefix:
            return f"{self._documents_prefix}/{key}"
        return key

    def _blob(self, key: str) -> Any:
        return self._bucket.blob(self._object_name(key))

    def put(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        quarantine_on_infect: bool = False,
    ) -> StoredObject:
        result = self.scanner.scan(data)
        infected = result == ScanResult.INFECTED

        key_name = filename or str(uuid.uuid4())
        if infected and quarantine_on_infect:
            prefix = _quarantine_prefix(prefix)
        elif infected:
            raise AppError("FILE_INFECTED", "Upload failed malware scan", status_code=400)

        key = _build_key(prefix, key_name)
        blob = self._blob(key)
        blob.upload_from_string(data, content_type="application/octet-stream")
        digest = hashlib.sha256(data).hexdigest()
        obj = StoredObject(key=key, path=None, size=len(data), sha256=digest)
        if infected:
            raise AppError(
                "FILE_INFECTED",
                "Upload failed malware scan; file quarantined — replace it",
                status_code=400,
            )
        return obj

    def put_raw(
        self,
        data: bytes,
        *,
        prefix: str = "",
        filename: str | None = None,
        skip_scan: bool = False,
    ) -> tuple[StoredObject, ScanResult]:
        result = ScanResult.CLEAN if skip_scan else self.scanner.scan(data)
        key_name = filename or str(uuid.uuid4())
        use_prefix = prefix
        if result == ScanResult.INFECTED:
            use_prefix = _quarantine_prefix(prefix)
        key = _build_key(use_prefix, key_name)
        blob = self._blob(key)
        blob.upload_from_string(data, content_type="application/octet-stream")
        digest = hashlib.sha256(data).hexdigest()
        return StoredObject(key=key, path=None, size=len(data), sha256=digest), result

    def append_chunk(self, key: str, data: bytes, *, expected_offset: int) -> int:
        blob = self._blob(key)
        try:
            existing = blob.download_as_bytes()
        except GcsNotFound:
            existing = b""
        current = len(existing)
        if current != expected_offset:
            raise AppError(
                "UPLOAD_OFFSET_MISMATCH",
                f"Expected offset {expected_offset}, have {current}",
                status_code=409,
            )
        combined = existing + data
        blob.upload_from_string(combined, content_type="application/octet-stream")
        return current + len(data)

    def get(self, key: str) -> bytes:
        blob = self._blob(key)
        try:
            return blob.download_as_bytes()
        except GcsNotFound:
            raise AppError("FILE_NOT_FOUND", "Object not found", status_code=404) from None

    def delete(self, key: str) -> None:
        blob = self._blob(key)
        try:
            blob.delete()
        except GcsNotFound:
            pass


def get_object_storage(scanner: MalwareScanner | None = None) -> ObjectStorage:
    """Return local or GCS storage based on STORAGE_BACKEND."""
    if settings.storage_backend.lower() == "gcs":
        return GcsObjectStorage(scanner=scanner)
    return LocalObjectStorage(scanner=scanner)
