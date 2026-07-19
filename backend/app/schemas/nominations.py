from uuid import UUID

from pydantic import BaseModel, Field


class NominationCreate(BaseModel):
    institutionId: UUID
    skillId: UUID
    competitorRef: str = Field(min_length=1, max_length=64)


class NominationOut(BaseModel):
    nominationId: UUID
    status: str
    competitorId: UUID | None = None
    reason: str | None = None


class NominationRejectIn(BaseModel):
    reason: str | None = None
