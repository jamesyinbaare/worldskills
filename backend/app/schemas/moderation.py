"""Schemas for US-ASM-02 moderation."""

from uuid import UUID

from pydantic import BaseModel, Field


class ModerationApplyIn(BaseModel):
    criterionId: str = Field(min_length=1, max_length=64)
    method: str = Field(min_length=1, max_length=32)  # STANDARDISE | MANUAL
    value: int | None = None
    reason: str | None = None


class ModerationFlagOut(BaseModel):
    criterionId: str
    spread: int | None = None
    rawMarks: list[int] = Field(default_factory=list)
    flagged: bool
    state: str
    standardisedValue: int | None = None
    method: str | None = None
    reason: str | None = None


class ModerationAnalyseOut(BaseModel):
    submissionId: UUID
    tolerance: int
    flags: list[ModerationFlagOut]


class ModerationApplyOut(BaseModel):
    submissionId: UUID
    criterionId: str
    method: str
    standardisedValue: int
    rawMarks: list[int]
    total: int
    reason: str | None = None
