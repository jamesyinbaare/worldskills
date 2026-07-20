"""Schemas for US-RES-01 results publication."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PrepareResultsIn(BaseModel):
    skillId: UUID | None = None


class PrepareResultsOut(BaseModel):
    publicationId: UUID
    state: str
    skillId: UUID | None = None
    entryCount: int
    releaseAt: datetime


class ReleaseResultsIn(BaseModel):
    manual: bool = False
    skillId: UUID | None = None


class ReleaseResultsOut(BaseModel):
    publicationId: UUID
    releasedAt: datetime
    state: str = "RELEASED"
    certificateCount: int = 0


class CorrectResultIn(BaseModel):
    changes: dict = Field(default_factory=dict)
    reason: str


class CorrectResultOut(BaseModel):
    resultId: UUID
    version: int
    publicationId: UUID
    outcome: str
    certificateId: UUID | None = None


class PublicResultItem(BaseModel):
    resultId: UUID
    competitorId: UUID
    skillId: UUID
    outcome: str
    score: int | None = None
    rank: int | None = None
    certificateId: UUID | None = None
    refNo: str | None = None


class PublicResultsOut(BaseModel):
    state: str
    status: str | None = None
    releasedAt: datetime | None = None
    results: list[PublicResultItem] = Field(default_factory=list)


class CompetitorResultsOut(BaseModel):
    state: str
    status: str | None = None
    result: PublicResultItem | None = None
    certificate: str | None = None
