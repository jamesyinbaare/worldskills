from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PeriodIn(BaseModel):
    start: date
    end: date


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    period: PeriodIn
    timeZone: str
    description: str | None = Field(default=None, max_length=20000)
    organisingBody: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None
    # Accepted for API compatibility; ignored — product is English-only.
    languages: list[str] | None = None

    @field_validator("timeZone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError("INVALID_TIMEZONE") from exc
        return v


class CompetitionOut(BaseModel):
    competitionId: UUID
    status: str
    name: str | None = None
    period: PeriodIn | None = None
    timeZone: str | None = None
    languages: list[str] | None = None
    description: str | None = None


class CompetitionListItem(BaseModel):
    competitionId: UUID
    name: str
    status: str
    period: PeriodIn
    timeZone: str
    languages: list[str]


class OpenCompetitionOut(BaseModel):
    competitionId: UUID
    name: str
    status: str
    description: str | None = None
    window: dict[str, str] | None = None


class PublicSkillOut(BaseModel):
    skillId: UUID
    name: str
    number: str | None = None
    familyName: str | None = None
    description: str | None = None
    hasCriteriaDocument: bool = False
    criteriaFileName: str | None = None


class PublicCompetitionOut(BaseModel):
    competitionId: UUID
    name: str
    description: str | None = None
    period: PeriodIn
    timeZone: str
    window: dict[str, str] | None = None
    skills: list[PublicSkillOut] = Field(default_factory=list)


class CompetitionPublicProfileUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=20000)


class ValidationIssue(BaseModel):
    code: str
    entity: str
    message: str
    link: str
    # blocking → prevents activation; advisory → warning only (e.g. pending exercises)
    severity: str = "blocking"


class ValidateOut(BaseModel):
    """ok is True when there are no blocking issues (advisory warnings allowed)."""

    ok: bool
    issues: list[ValidationIssue]


class ActivateOut(BaseModel):
    status: str


class CloneOut(BaseModel):
    newCompetitionId: UUID


class CompetitionUpdateStructural(BaseModel):
    """Direct structural competition edit (e.g. rename)."""

    name: str | None = Field(default=None, min_length=3, max_length=120)

