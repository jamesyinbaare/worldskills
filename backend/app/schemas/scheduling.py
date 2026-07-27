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
    competitionId: UUID
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
    competitionId: UUID
    summary: str
    severity: str | None = None
    recordedAt: datetime


class VenueOut(BaseModel):
    venueId: UUID
    competitionId: UUID
    name: str
    capacity: int
    workstations: int
    active: bool
    zoneId: UUID | None = None


class SessionListItem(BaseModel):
    sessionId: UUID
    competitionId: UUID
    venueId: UUID
    venueName: str
    startsAt: datetime
    endsAt: datetime
    workstations: int
    state: str
    assignmentCount: int
    incidentCount: int


class AssignmentDetailOut(BaseModel):
    assignmentId: UUID
    sessionId: UUID
    competitorId: UUID
    competitorRef: str | None = None
    competitorName: str | None = None
    skillId: UUID | None = None
    skillName: str | None = None
    workstation: str
    readiness: str


class SessionDetailOut(BaseModel):
    sessionId: UUID
    competitionId: UUID
    venueId: UUID
    venueName: str
    startsAt: datetime
    endsAt: datetime
    workstations: int
    state: str
    assignments: list[AssignmentDetailOut] = Field(default_factory=list)
    incidents: list[IncidentOut] = Field(default_factory=list)
