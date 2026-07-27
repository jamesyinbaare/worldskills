"""Schemas for US-RES-01 results publication."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ResultsConfigOut(BaseModel):
    competitionId: UUID
    releaseAt: datetime
    audience: list[str]
    neutralStatus: str
    awardByRank: dict[str, str]
    defaultOutcome: str
    configured: bool = True


class ResultsConfigPut(BaseModel):
    releaseAt: datetime
    audience: list[str] = Field(min_length=1)
    neutralStatus: str = Field(default="IN_PROGRESS", min_length=1, max_length=64)
    awardByRank: dict[str, str] = Field(default_factory=lambda: {"1": "GOLD", "2": "SILVER", "3": "BRONZE"})
    defaultOutcome: str = Field(default="FINALIST", min_length=1, max_length=64)
    # When true (default), ensure certificate templates exist for awards + stage outcomes
    ensureTemplates: bool = True

    @field_validator("audience")
    @classmethod
    def audience_known(cls, v: list[str]) -> list[str]:
        allowed = {"PUBLIC", "COMPETITOR", "INSTITUTION"}
        cleaned: list[str] = []
        for item in v:
            code = str(item).strip().upper()
            if not code:
                continue
            if code not in allowed:
                raise ValueError("INVALID_AUDIENCE")
            if code not in cleaned:
                cleaned.append(code)
        if not cleaned:
            raise ValueError("REQUIRED")
        return cleaned

    @field_validator("neutralStatus", "defaultOutcome")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip().upper()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("awardByRank")
    @classmethod
    def award_keys(cls, v: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, val in (v or {}).items():
            key = str(k).strip()
            outcome = str(val).strip().upper()
            if not key or not outcome:
                continue
            out[key] = outcome
        return out


class CertificateTemplateOut(BaseModel):
    templateId: UUID
    competitionId: UUID
    outcome: str
    language: str
    body: str


class PrepareResultsIn(BaseModel):
    skillId: UUID | None = None
    stageId: UUID | None = None


class PrepareResultsOut(BaseModel):
    publicationId: UUID
    state: str
    skillId: UUID | None = None
    stageId: UUID | None = None
    entryCount: int
    releaseAt: datetime


class ReleaseResultsIn(BaseModel):
    manual: bool = False
    skillId: UUID | None = None
    stageId: UUID | None = None


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


class AdminResultItem(BaseModel):
    resultId: UUID
    publicationId: UUID
    competitionId: UUID
    skillId: UUID
    skillName: str
    stageId: UUID | None = None
    stageName: str | None = None
    competitorId: UUID
    competitorRef: str | None = None
    competitorName: str | None = None
    outcome: str
    score: int | None = None
    rank: int | None = None
    version: int
    publicationState: str
    releaseAt: datetime
    releasedAt: datetime | None = None
