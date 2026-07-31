from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AgeRuleEmbed(BaseModel):
    maxAge: int = Field(ge=0)
    referenceDate: date | None = None
    openCategoryEnabled: bool


class CycleSkillAssociate(BaseModel):
    """Associate a catalog skill to a competition (revised US-SKL-01)."""

    skillId: UUID
    ageRule: AgeRuleEmbed
    capacity: int | None = None

    @field_validator("capacity")
    @classmethod
    def capacity_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("INVALID_CAPACITY")
        return v


class CycleSkillPatch(BaseModel):
    ageRule: AgeRuleEmbed | None = None
    capacity: int | None = None
    schoolQuota: int | None = None
    active: bool | None = None

    @field_validator("capacity")
    @classmethod
    def capacity_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("INVALID_CAPACITY")
        return v

    @field_validator("schoolQuota")
    @classmethod
    def school_quota_range(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 1000):
            raise ValueError("INVALID_SCHOOL_QUOTA")
        return v


class SkillCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    number: str | None = Field(default=None, max_length=32)
    familyId: str | None = Field(default=None, max_length=64)
    ageRuleId: UUID | None = None
    pathwayId: UUID | None = None
    schemeId: UUID | None = None
    capacity: int | None = None
    schoolQuota: int | None = None
    skillId: UUID | None = None
    ageRule: AgeRuleEmbed | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
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

    @field_validator("schoolQuota")
    @classmethod
    def school_quota_range(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 1000):
            raise ValueError("INVALID_SCHOOL_QUOTA")
        return v

    @model_validator(mode="after")
    def require_name_or_catalog(self) -> "SkillCreate":
        if self.skillId is not None:
            if self.ageRule is None:
                raise ValueError("ageRule is required when skillId is set")
            return self
        if not self.name:
            raise ValueError("REQUIRED")
        return self


class SkillOut(BaseModel):
    skillId: UUID
    cycleSkillId: UUID | None = None
    competitionId: UUID
    catalogSkillId: UUID | None = None
    name: str
    number: str | None = None
    familyId: str | None = None
    familyName: str | None = None
    description: str | None = None
    ageRuleId: UUID | None = None
    ageRule: AgeRuleEmbed | None = None
    pathwayId: UUID | None = None
    schemeId: UUID | None = None
    capacity: int | None = None
    schoolQuota: int | None = None
    active: bool
    hasPathway: bool = False
    hasCriteriaDocument: bool = False
    criteriaFileName: str | None = None
    criteriaScanStatus: str | None = None


class AvailableSkillOut(BaseModel):
    skillId: UUID
    name: str
    number: str | None = None
    familyName: str | None = None
    description: str | None = None
    active: bool = True
    hasCriteriaDocument: bool = False
    criteriaFileName: str | None = None
