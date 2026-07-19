from uuid import UUID

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    expertId: UUID
    skillId: UUID
    zoneId: UUID


class CoiFlagOut(BaseModel):
    institutionId: UUID
    reason: str
    competitorIds: list[UUID] = Field(default_factory=list)


class AssignmentOut(BaseModel):
    assignmentId: UUID
    cycleId: UUID
    expertId: UUID
    skillId: UUID
    zoneId: UUID
    coiFlags: list[CoiFlagOut]


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
