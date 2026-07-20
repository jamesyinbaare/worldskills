"""Schemas for US-PUB-01 public competitor directory and profiles."""

from uuid import UUID

from pydantic import BaseModel, Field


class PublicCompetitorListItem(BaseModel):
    competitorId: UUID
    displayName: str | None = None
    photo: str | None = None
    institution: str | None = None
    skill: str | None = None
    stageStatus: str | None = None
    zone: str | None = None


class PublicCompetitorDirectoryOut(BaseModel):
    items: list[PublicCompetitorListItem]
    nextCursor: str | None = None


class PublicCompetitorProfileOut(BaseModel):
    """Only config-allowlisted public fields; sensitive keys never included."""

    competitorId: UUID
    public: bool = True
    # Legacy / US-REG-02 compatibility
    competitorRef: str | None = None
    displayName: str | None = None
    photo: str | None = None
    institution: str | None = None
    skill: str | None = None
    stageStatus: str | None = None
    zone: str | None = None


class PublicDirectoryQuery(BaseModel):
    skill: UUID | None = None
    zone: UUID | None = None
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1)
    format: str | None = None
