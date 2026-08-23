from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AssignmentCreate(BaseModel):
    expertId: UUID
    skillId: UUID | None = None
    cycleSkillId: UUID | None = None
    zoneId: UUID | None = None

    @model_validator(mode="after")
    def require_skill(self) -> "AssignmentCreate":
        if self.cycleSkillId is None and self.skillId is None:
            raise ValueError("skillId or cycleSkillId required")
        return self

    @property
    def resolved_skill_id(self) -> UUID:
        return self.cycleSkillId or self.skillId  # type: ignore[return-value]


class CoiFlagOut(BaseModel):
    institutionId: UUID
    reason: str
    competitorIds: list[UUID] = Field(default_factory=list)


class AssignmentOut(BaseModel):
    assignmentId: UUID
    competitionId: UUID
    expertId: UUID
    skillId: UUID
    cycleSkillId: UUID | None = None
    zoneId: UUID | None = None
    coiFlags: list[CoiFlagOut]


class AssignmentListOut(BaseModel):
    items: list[AssignmentOut]


class MyAssignmentOut(BaseModel):
    """Expert portal discovery — named assignment for dropdowns/cards."""

    assignmentId: UUID
    competitionId: UUID
    competitionName: str
    skillId: UUID
    skillName: str
    zoneId: UUID | None = None
    zoneName: str


class DelegateIn(BaseModel):
    expertId: UUID


class QueueSubmissionOut(BaseModel):
    submissionId: UUID
    competitorId: UUID | None = None
    anonCode: str | None = None
    state: str


class AssessorQueueOut(BaseModel):
    submissions: list[QueueSubmissionOut]
    # Spec alias US-ASM-01
    items: list[QueueSubmissionOut] | None = None
