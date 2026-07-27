"""Schemas for institution portal discovery APIs."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class InstitutionRegistrationOut(BaseModel):
    competitorId: UUID
    competitorRef: str
    competitionId: UUID
    competitionName: str
    competitionStatus: str
    skillId: UUID
    skillName: str
    status: str
    givenNames: str | None = None
    familyName: str | None = None
    gender: str | None = None


class InstitutionCompetitionWindowOut(BaseModel):
    opensAt: str
    closesAt: str


class InstitutionCompetitionOut(BaseModel):
    competitionId: UUID
    name: str
    status: str
    period: dict[str, str]
    description: str | None = None
    window: InstitutionCompetitionWindowOut | None = None


class NominationQuotaOut(BaseModel):
    skillId: UUID
    skillName: str
    max: int
    used: int
    remaining: int
    configured: bool = True


class NominationQuotasOut(BaseModel):
    competitionId: UUID
    institutionId: UUID
    quotas: list[NominationQuotaOut]


class SchoolQuotaSkillIn(BaseModel):
    skillId: UUID
    maxNominations: int = Field(ge=0, le=1000)


class CompetitionSchoolQuotasUpsert(BaseModel):
    limits: list[SchoolQuotaSkillIn] = Field(default_factory=list)


class CompetitionSchoolQuotasOut(BaseModel):
    competitionId: UUID
    quotas: list[NominationQuotaOut]


# Legacy per-institution shapes kept for older clients/tests during transition
class NominationLimitSkillIn(BaseModel):
    skillId: UUID
    maxNominations: int = Field(ge=0, le=1000)


class InstitutionNominationLimitsUpsert(BaseModel):
    zoneId: UUID
    limits: list[NominationLimitSkillIn] = Field(default_factory=list)


class InstitutionNominationLimitsOut(BaseModel):
    competitionId: UUID
    institutionId: UUID
    zoneId: UUID | None = None
    limits: list[NominationQuotaOut]


class InstitutionCompetitionMembershipOut(BaseModel):
    institutionId: UUID
    institutionName: str
    institutionCode: str
    zoneId: UUID
    zoneName: str
    configuredSkillCount: int
