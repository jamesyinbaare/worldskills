"""Schemas for US-APP-01 appeals and disqualification."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AppealLodgeIn(BaseModel):
    competitorId: UUID
    stageId: UUID
    reason: str


class AppealOut(BaseModel):
    appealId: UUID
    competitionId: UUID
    competitorId: UUID
    stageId: UUID
    state: str
    reason: str
    officerId: UUID | None = None
    rulingOutcome: str | None = None
    rulingReason: str | None = None
    remedy: str | None = None


class AppealListItem(BaseModel):
    appealId: UUID
    competitionId: UUID
    competitorId: UUID
    competitorRef: str | None = None
    competitorName: str | None = None
    stageId: UUID
    stageName: str | None = None
    skillId: UUID | None = None
    skillName: str | None = None
    state: str
    reason: str
    officerId: UUID | None = None
    rulingOutcome: str | None = None
    rulingReason: str | None = None
    remedy: str | None = None
    submittedAt: datetime | None = None


class AppealAssignIn(BaseModel):
    officerId: UUID


class AppealRuleIn(BaseModel):
    outcome: str  # UPHELD | DISMISSED
    reason: str | None = None
    remedy: str | None = None  # RE_SCORE | RE_RANK | REINSTATE


class DisqualifyIn(BaseModel):
    reason: str | None = None


class DisqualifyOut(BaseModel):
    competitorId: UUID
    status: str
    reason: str
    promotedCompetitorId: UUID | None = None
