from uuid import UUID

from pydantic import BaseModel, Field


class ScreenOut(BaseModel):
    competitorId: UUID
    eligible: bool
    status: str
    failedRules: list[str] = Field(default_factory=list)
    category: str | None = None
    ageAtReference: int | None = None


class EligibilityOverrideIn(BaseModel):
    value: bool
    reason: str | None = None
    category: str | None = None  # COMPETITIVE | OPEN when forcing eligible


class EligibilityOverrideOut(BaseModel):
    competitorId: UUID
    eligible: bool
    status: str
    reason: str
    category: str | None = None
