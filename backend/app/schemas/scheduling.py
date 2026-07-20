"""Schemas for US-SCH-01 scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreateIn(BaseModel):
    venueId: UUID
    startsAt: datetime
    endsAt: datetime
    workstations: int = Field(..., ge=1)


class SessionOut(BaseModel):
    sessionId: UUID
    cycleId: UUID
    venueId: UUID
    startsAt: datetime
    endsAt: datetime
    workstations: int
    state: str


class AssignmentCreateIn(BaseModel):
    competitorId: UUID
    workstation: str = Field(..., min_length=1, max_length=64)


class AssignmentOut(BaseModel):
    assignmentId: UUID
    sessionId: UUID
    competitorId: UUID
    workstation: str
    readiness: str


class IncidentCreateIn(BaseModel):
    summary: str = Field(..., min_length=1)
    severity: str | None = None


class IncidentOut(BaseModel):
    incidentId: UUID
    sessionId: UUID
    cycleId: UUID
    summary: str
    severity: str | None = None
    recordedAt: datetime
