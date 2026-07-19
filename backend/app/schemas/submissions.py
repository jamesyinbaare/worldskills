"""Schemas for US-SUB-02 submissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SubmissionOpen(BaseModel):
    """Optional; stage timed duration is taken from stage.submission_rules."""

    pass


class SubmissionOut(BaseModel):
    submissionId: UUID
    cycleId: UUID
    stageId: UUID | None = None
    competitorId: UUID
    state: str
    deadlineAt: datetime | None = None
    timedExpiresAt: datetime | None = None
    uploadLocked: bool = False
    late: bool = False
    hash: str | None = None
    receipt: str | None = None
    submittedAt: datetime | None = None


class ArtefactSessionCreate(BaseModel):
    deliverableCode: str = Field(min_length=1, max_length=64)
    filename: str = Field(min_length=1, max_length=255)
    contentType: str | None = Field(default=None, max_length=128)
    totalSize: int = Field(gt=0)


class ArtefactSessionOut(BaseModel):
    uploadId: str
    artefactId: UUID
    receivedBytes: int
    totalSize: int


class ArtefactUploadOut(BaseModel):
    artefactId: UUID
    uploadId: str | None = None
    scan: str
    receivedBytes: int | None = None
    complete: bool = True
    quarantined: bool = False


class FinaliseOut(BaseModel):
    state: str
    hash: str | None = None
    receipt: str | None = None
    late: bool = False
