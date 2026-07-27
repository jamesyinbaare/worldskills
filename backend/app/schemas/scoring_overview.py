"""Schemas for admin / chief scoring overview and total resolution."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AssessorTotalOut(BaseModel):
    assessorId: UUID
    assessorName: str | None = None
    assessorEmail: str | None = None
    total: int
    markCount: int
    finalized: bool = False


class ScoringListItemOut(BaseModel):
    submissionId: UUID
    anonCode: str | None = None
    state: str
    skillId: UUID | None = None
    skillName: str | None = None
    stageId: UUID | None = None
    stageName: str | None = None
    exerciseTitle: str | None = None
    competitorId: UUID | None = None
    competitorRef: str | None = None
    competitorName: str | None = None
    blindMode: bool = True
    submissionTotal: int | None = None
    assessorCount: int = 0
    assessorTotals: list[AssessorTotalOut] = Field(default_factory=list)
    disagreement: bool = False
    openFlags: int = 0
    resultsReleased: bool = False


class CriterionAssessorMarkOut(BaseModel):
    assessorId: UUID
    assessorName: str | None = None
    type: str
    raw: int | None = None
    standardised: int | None = None
    status: str
    comment: str | None = None


class CriterionScoringOut(BaseModel):
    criterionId: str
    name: str
    type: str
    max: int | None = None
    marks: list[CriterionAssessorMarkOut] = Field(default_factory=list)
    standardisedValue: int | None = None
    disagreement: bool = False


class ScoringDetailOut(BaseModel):
    submissionId: UUID
    anonCode: str | None = None
    state: str
    skillId: UUID | None = None
    skillName: str | None = None
    stageId: UUID | None = None
    stageName: str | None = None
    exerciseTitle: str | None = None
    blindMode: bool = True
    competitorId: UUID | None = None
    competitorRef: str | None = None
    competitorName: str | None = None
    submissionTotal: int | None = None
    assessorTotals: list[AssessorTotalOut] = Field(default_factory=list)
    criteria: list[CriterionScoringOut] = Field(default_factory=list)
    disagreement: bool = False
    openFlags: int = 0
    resultsReleased: bool = False


class ResolveTotalIn(BaseModel):
    method: str = Field(min_length=1, max_length=32)  # AVERAGE | SELECT_ASSESSOR
    assessorId: UUID | None = None
    reason: str | None = None

    @field_validator("method")
    @classmethod
    def method_known(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in {"AVERAGE", "SELECT_ASSESSOR"}:
            raise ValueError("INVALID")
        return code

    @model_validator(mode="after")
    def select_needs_assessor(self) -> "ResolveTotalIn":
        if self.method == "SELECT_ASSESSOR" and self.assessorId is None:
            raise ValueError("assessorId required for SELECT_ASSESSOR")
        return self


class ResolveTotalOut(BaseModel):
    submissionId: UUID
    method: str
    assessorId: UUID | None = None
    total: int
    assessorTotals: list[AssessorTotalOut] = Field(default_factory=list)
    reason: str | None = None
