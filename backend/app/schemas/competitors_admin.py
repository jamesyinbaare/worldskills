"""Admin competitor roster schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AdminCompetitorItem(BaseModel):
    competitorId: UUID
    refNo: str
    givenNames: str | None = None
    familyName: str | None = None
    skillId: UUID
    skillName: str
    institutionId: UUID | None = None
    institutionName: str | None = None
    status: str
    eligibilityStatus: str | None = None
    zoneId: UUID | None = None
    zoneName: str | None = None
    consentFormUploadedAt: datetime | None = None
    consentVerificationStatus: str | None = None
