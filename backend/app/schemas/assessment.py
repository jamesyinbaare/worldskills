"""Schemas for US-ASM-01 assessment scoring."""

from uuid import UUID

from pydantic import BaseModel, Field


class CriterionMarkIn(BaseModel):
    criterionId: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=32)  # MEASUREMENT | JUDGEMENT
    value: int
    judgeId: UUID | None = None
    comment: str | None = None


class PenaltyIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    # Optional override; otherwise scheme deduction is used
    deduction: int | None = Field(default=None, ge=0)


class ScorePut(BaseModel):
    criterionMarks: list[CriterionMarkIn] = Field(default_factory=list)
    penalties: list[PenaltyIn] = Field(default_factory=list)
    # False = draft/autosave; True = finalise (requires all criteria)
    finalize: bool = False


class ScoreMarkOut(BaseModel):
    criterionId: str
    type: str
    value: int | None = None
    assessorId: UUID
    judgeId: UUID | None = None
    comment: str | None = None
    status: str


class PenaltyOut(BaseModel):
    code: str
    deduction: int


class BreakdownOut(BaseModel):
    marks: list[ScoreMarkOut]
    penalties: list[PenaltyOut]
    total: int


class ScorePutOut(BaseModel):
    total: int
    status: str
    breakdown: BreakdownOut


class AssessmentArtefactOut(BaseModel):
    artefactId: UUID
    deliverableCode: str
    filename: str
    contentType: str | None = None
    size: int
    scanStatus: str


class AssessmentViewOut(BaseModel):
    submissionId: UUID
    anonCode: str
    state: str
    blindMode: bool
    # Present only when blindMode is false
    competitorId: UUID | None = None
    givenNames: str | None = None
    familyName: str | None = None
    institutionId: UUID | None = None
    photoKey: str | None = None
    criteria: list[dict]
    penalties: list[dict]
    myMarks: list[ScoreMarkOut] = Field(default_factory=list)
    total: int | None = None
    artefacts: list[AssessmentArtefactOut] = Field(default_factory=list)
