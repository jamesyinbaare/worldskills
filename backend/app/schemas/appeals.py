"""Schemas for US-APP-01 appeals and disqualification."""

from uuid import UUID

from pydantic import BaseModel


class AppealLodgeIn(BaseModel):
    competitorId: UUID
    stageId: UUID
    reason: str


class AppealOut(BaseModel):
    appealId: UUID
    cycleId: UUID
    competitorId: UUID
    stageId: UUID
    state: str
    reason: str
    officerId: UUID | None = None
    rulingOutcome: str | None = None
    rulingReason: str | None = None
    remedy: str | None = None


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
