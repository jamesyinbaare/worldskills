from uuid import UUID

from pydantic import BaseModel, Field


class ExpertSkillAreaOut(BaseModel):
    catalogSkillId: UUID
    name: str
    number: str | None = None
    familyId: UUID
    familyName: str | None = None
    active: bool


class ExpertSkillAreasOut(BaseModel):
    items: list[ExpertSkillAreaOut] = Field(default_factory=list)


class SetExpertSkillAreasRequest(BaseModel):
    catalogSkillIds: list[UUID] = Field(default_factory=list)
