"""Schemas for US-SHL-01 shortlisting."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ShortlistRankedItem(BaseModel):
    competitorId: UUID
    zoneId: UUID
    score: int
    rank: int
    outcome: str
    reason: str | None = None
    refNo: str | None = None


class ShortlistGenerateOut(BaseModel):
    shortlistId: UUID
    stageId: UUID
    state: str
    isFinalStage: bool
    byZone: dict[str, list[ShortlistRankedItem]]
    generatedAt: datetime


class ShortlistConfirmOut(BaseModel):
    shortlistId: UUID
    state: str
    advanced: list[UUID]
    waitlist: list[UUID]
    excluded: list[UUID] = Field(default_factory=list)
    finalists: list[ShortlistRankedItem] | None = None
    notified: int = 0
