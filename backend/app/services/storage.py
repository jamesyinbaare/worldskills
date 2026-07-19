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
        # Stub: always clean in default/dev; injectable/subclassable for tests.
        _ = data
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

    def put(self, data: bytes, *, prefix: str = "", filename: str | None = None) -> StoredObject:
        result = self.scanner.scan(data)
        if result == ScanResult.INFECTED:
            raise AppError("FILE_INFECTED", "Upload failed malware scan", status_code=400)

        key_name = filename or str(uuid.uuid4())
        key = f"{prefix.rstrip('/')}/{key_name}" if prefix else key_name
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        return StoredObject(key=key, path=path, size=len(data), sha256=digest)

    def get(self, key: str) -> bytes:
        path = self.root / key
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", "Object not found", status_code=404)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            os.remove(path)
