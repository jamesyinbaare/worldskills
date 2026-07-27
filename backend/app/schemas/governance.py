"""Schemas for US-AUD-01 audit query and DSAR."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEventOut(BaseModel):
    eventId: UUID
    competitionId: UUID | None = None
    actorId: UUID | None = None
    actorRole: str | None = None
    action: str
    entityType: str
    entityId: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None
    timestamp: datetime
    signatureValid: bool | None = None


class AuditListOut(BaseModel):
    events: list[AuditEventOut]


class DsarCreateIn(BaseModel):
    subjectId: UUID
    type: str = Field(..., min_length=1, max_length=32)  # ACCESS | ERASURE | WITHDRAW


class DsarJobOut(BaseModel):
    jobId: UUID
    status: str
    requestType: str | None = None
    export: dict[str, Any] | None = None
    resultSummary: str | None = None
    completedAt: datetime | None = None
