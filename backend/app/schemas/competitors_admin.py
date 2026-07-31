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
    hasMobile: bool = False
    hasCoachPhone: bool = False


class SkillSmsSendIn(BaseModel):
    """Send templated SMS to selected (or all) competitors for a skill."""

    # Empty / omitted → all competitors registered for the skill
    competitorIds: list[UUID] | None = None
    # competitors | coaches | both
    recipients: str = "both"
    # custom | exercise_reminder | schedule_update | general_notice
    templateKey: str = "custom"
    # Required for custom; optional override for presets
    message: str | None = None


class SkillSmsSendOut(BaseModel):
    competitorsConsidered: int
    competitorSent: int
    coachSent: int
    failed: int
    skippedNoPhone: int = 0
    recipients: str
    templateKey: str
