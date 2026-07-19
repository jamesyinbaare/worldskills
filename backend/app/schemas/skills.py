from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    number: str | None = Field(default=None, max_length=32)
    familyId: str | None = Field(default=None, max_length=64)
    ageRuleId: UUID | None = None
    pathwayId: UUID | None = None
    schemeId: UUID | None = None
    capacity: int | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("capacity")
    @classmethod
    def capacity_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("INVALID_CAPACITY")
        return v


class SkillOut(BaseModel):
    skillId: UUID
    cycleId: UUID
    name: str
    number: str | None = None
    familyId: str | None = None
    ageRuleId: UUID | None = None
    pathwayId: UUID | None = None
    schemeId: UUID | None = None
    capacity: int | None = None
    active: bool
