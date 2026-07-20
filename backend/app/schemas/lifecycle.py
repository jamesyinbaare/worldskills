"""Schemas for US-LCY-01 competitor lifecycle."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class WithdrawIn(BaseModel):
    reason: str | None = None


class WithdrawOut(BaseModel):
    competitorId: UUID
    status: str
    promotedCompetitorId: UUID | None = None


class ReplacementIn(BaseModel):
    refNo: str
    givenNames: str
    familyName: str
    dateOfBirth: date
    nationality: str | None = None
    enrolmentAttested: bool = False
    email: str | None = None
    mobile: str | None = None


class SubstituteIn(BaseModel):
    replacement: ReplacementIn


class SubstituteOut(BaseModel):
    withdrawnCompetitorId: UUID
    replacementCompetitorId: UUID
    eligible: bool
    status: str
    failedRules: list[str] = Field(default_factory=list)
