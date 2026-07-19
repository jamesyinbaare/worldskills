"""Local filesystem object storage + injectable malware scan stub."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.config import settings
from app.core.errors import AppError

# Official EICAR antivirus test string (DoD: malware path tested with EICAR)
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScanResult(str, Enum):
    CLEAN = "clean"
    INFECTED = "infected"


@dataclass
class StoredObject:
    key: str
    path: Path
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
            prefix = f"quarantine/{prefix.rstrip('/')}" if prefix else "quarantine"
        elif infected:
            raise AppError("FILE_INFECTED", "Upload failed malware scan", status_code=400)

        key = f"{prefix.rstrip('/')}/{key_name}" if prefix else key_name
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
            use_prefix = f"quarantine/{prefix.rstrip('/')}" if prefix else "quarantine"
        key = f"{use_prefix.rstrip('/')}/{key_name}" if use_prefix else key_name
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
