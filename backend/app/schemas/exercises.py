"""Schemas for US-SUB-01 Exercise (challenge / test project) per stage."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DeliverableItem(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str | None = None
    required: bool = True
    allowedTypes: list[str] = Field(default_factory=list)
    maxSizeBytes: int | None = Field(default=None, ge=1)


class ExercisePut(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    brief: str | None = None
    deliverables: list[DeliverableItem] = Field(default_factory=list)
    schemeId: UUID | None = None
    latePolicy: str | None = None  # block | flag-late
    timedDurationSeconds: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def title_strip(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("latePolicy")
    @classmethod
    def late_policy_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"block", "flag-late"}
        if v not in allowed:
            raise ValueError("INVALID")
        return v


class ExerciseOut(BaseModel):
    exerciseId: UUID
    stageId: UUID
    competitionId: UUID
    title: str
    brief: str | None = None
    deliverables: list[DeliverableItem]
    status: str
    schemeId: UUID | None = None
    latePolicy: str | None = None
    timedDurationSeconds: int | None = None
    packFileName: str | None = None
    packContentType: str | None = None
    packScanStatus: str | None = None
    hasRubricCriteria: bool = False
    blindMode: bool | None = None
    criteriaCount: int = 0