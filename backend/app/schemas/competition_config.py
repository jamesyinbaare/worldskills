from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AgeRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    maxAge: int = Field(ge=1, le=120)
    referenceDate: date | None = None
    openCategoryEnabled: bool = False

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class AgeRuleOut(BaseModel):
    ageRuleId: UUID
    competitionId: UUID
    name: str
    maxAge: int
    referenceDate: date | None = None
    openCategoryEnabled: bool


class PathwayConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class PathwayConfigOut(BaseModel):
    pathwayId: UUID
    competitionId: UUID
    name: str


class MarkingSchemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class MarkingSchemeOut(BaseModel):
    schemeId: UUID
    competitionId: UUID
    name: str
    documentFileName: str | None = None
    documentContentType: str | None = None
    documentScanStatus: str | None = None
    # Structured scoring config (may be null until rubric is saved)
    blindMode: bool | None = None
    criteria: list[dict] | None = None
    penalties: list[dict] | None = None
    hasRubricCriteria: bool = False


class RubricCriterionIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=32)
    max: int = Field(ge=1, le=1000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("type")
    @classmethod
    def type_ok(cls, v: str) -> str:
        allowed = {"MEASUREMENT", "JUDGEMENT"}
        upper = v.strip().upper()
        if upper not in allowed:
            raise ValueError("INVALID")
        return upper


class RubricPenaltyIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    deduction: int = Field(ge=0, le=1000)
    cap: int | None = Field(default=None, ge=0, le=1000)

    @field_validator("code")
    @classmethod
    def code_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class ExerciseRubricPut(BaseModel):
    blindMode: bool = False
    criteria: list[RubricCriterionIn] = Field(default_factory=list)
    penalties: list[RubricPenaltyIn] = Field(default_factory=list)


class ExerciseRubricOut(BaseModel):
    schemeId: UUID
    competitionId: UUID
    stageId: UUID
    exerciseId: UUID
    name: str
    blindMode: bool = False
    criteria: list[dict] = Field(default_factory=list)
    penalties: list[dict] = Field(default_factory=list)
    hasRubricCriteria: bool = False
