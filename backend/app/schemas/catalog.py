"""Global family + skill catalog schemas (US-SKL-02)."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class FamilyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class FamilyOut(BaseModel):
    familyId: UUID
    name: str
    description: str | None = None
    active: bool


class CatalogSkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    number: str | None = Field(default=None, max_length=32)
    familyId: UUID
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class CatalogSkillPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    number: str | None = Field(default=None, max_length=32)
    familyId: UUID | None = None
    description: str | None = None
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped


class CatalogSkillOut(BaseModel):
    skillId: UUID
    name: str
    number: str | None = None
    familyId: UUID
    familyName: str | None = None
    description: str | None = None
    active: bool
