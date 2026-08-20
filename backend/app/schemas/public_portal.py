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


class ProgressionCounts(BaseModel):
    advanced: int = 0
    waitlisted: int = 0
    excluded: int = 0


class ProgressionStageOut(BaseModel):
    stageId: UUID
    stage: str
    order: int
    status: str  # IN_PROGRESS (embargo/neutral) | RELEASED
    counts: ProgressionCounts | None = None


class ProgressionZoneOut(BaseModel):
    zoneId: UUID
    zoneName: str
    stages: list[ProgressionStageOut]


class SkillProgressionOut(BaseModel):
    skillId: UUID
    skillName: str
    byZone: list[ProgressionZoneOut]


class PublicStatsCompetitionOut(BaseModel):
    competitionId: UUID
    name: str


class PublicStatsTotalsOut(BaseModel):
    competitorsRegistered: int = 0
    skillAreas: int = 0
    expertsAssigned: int = 0


class PublicStatsExpertOut(BaseModel):
    expertId: UUID
    fullName: str


class PublicStatsSkillOut(BaseModel):
    competitionId: UUID
    skillId: UUID
    name: str
    number: str | None = None
    competitorsRegistered: int = 0
    capacity: int | None = None
    experts: list[PublicStatsExpertOut] = Field(default_factory=list)


class PublicStatsOut(BaseModel):
    generatedAt: str
    competitions: list[PublicStatsCompetitionOut] = Field(default_factory=list)
    totals: PublicStatsTotalsOut = Field(default_factory=PublicStatsTotalsOut)
    skills: list[PublicStatsSkillOut] = Field(default_factory=list)
