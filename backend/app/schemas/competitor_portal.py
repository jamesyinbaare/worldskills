"""Schemas for competitor self-serve portal discovery APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MyRegistrationOut(BaseModel):
    competitorId: UUID
    competitionId: UUID
    competitionName: str
    skillId: UUID
    skillName: str
    status: str
    zoneId: UUID | None = None
    consentParticipationAt: datetime | None = None
    consentPublicAt: datetime | None = None
    publicProfileVisible: bool = False
    consentFormUploadedAt: datetime | None = None
    hasCriteriaDocument: bool = False
    criteriaFileName: str | None = None


class MyStageSubmissionSummary(BaseModel):
    submissionId: UUID | None = None
    state: str | None = None
    uploadLocked: bool = False
    receipt: str | None = None


class MyStageOut(BaseModel):
    stageId: UUID
    order: int
    name: str
    type: str
    opensAt: datetime | None = None
    closesAt: datetime | None = None
    exerciseAvailable: bool
    exerciseTitle: str | None = None
    exerciseStatus: str | None = None
    windowStatus: str  # upcoming | open | closed | unknown
    submission: MyStageSubmissionSummary


class MyStagesOut(BaseModel):
    competitionId: UUID
    competitionName: str
    competitorId: UUID
    skillId: UUID
    skillName: str
    stages: list[MyStageOut]
