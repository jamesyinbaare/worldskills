from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


SUPPORTED_LOCALES = {"en", "en-GH", "fr", "ak", "ee", "ga"}


class PeriodIn(BaseModel):
    start: date
    end: date


class CycleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    period: PeriodIn
    timeZone: str
    organisingBody: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None
    languages: list[str] = Field(min_length=1)

    @field_validator("timeZone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError("INVALID_TIMEZONE") from exc
        return v

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("AT_LEAST_ONE_LANGUAGE")
        for lang in v:
            if lang not in SUPPORTED_LOCALES:
                raise ValueError("UNSUPPORTED_LANGUAGE")
        return v


class CycleOut(BaseModel):
    cycleId: UUID
    status: str
    name: str | None = None
    period: PeriodIn | None = None
    timeZone: str | None = None
    languages: list[str] | None = None


class CycleListItem(BaseModel):
    cycleId: UUID
    name: str
    status: str
    period: PeriodIn
    timeZone: str
    languages: list[str]


class ValidationIssue(BaseModel):
    code: str
    entity: str
    message: str
    link: str


class ValidateOut(BaseModel):
    ok: bool
    issues: list[ValidationIssue]


class ActivateOut(BaseModel):
    status: str


class CloneOut(BaseModel):
    newCycleId: UUID


class CycleUpdateStructural(BaseModel):
    """Direct structural edit attempt — used to exercise CYCLE_LOCKED."""

    name: str | None = Field(default=None, min_length=3, max_length=120)
