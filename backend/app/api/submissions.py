from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.core.errors import AppError
from app.core.rbac import Capability
from app.dependencies.auth import client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.submissions import (
    ArtefactSessionCreate,
    ArtefactSessionOut,
    ArtefactUploadOut,
    FinaliseOut,
    SubmissionOut,
)
from app.services import submissions as submission_service

router = APIRouter(tags=["submissions"])

CompetitorUserDep = Annotated[User, Depends(require_capability(Capability.REGISTER_SUBMIT))]


def _submission_out(sub) -> SubmissionOut:
    return SubmissionOut(
        submissionId=sub.id,
        competitionId=sub.competition_id,
        stageId=sub.stage_id,
        competitorId=sub.competitor_id,
        state=sub.state,
        deadlineAt=sub.deadline_at,
        timedExpiresAt=sub.timed_expires_at,
        uploadLocked=sub.upload_locked,
        late=sub.late,
        hash=sub.content_hash,
        receipt=sub.receipt,
        submittedAt=sub.submitted_at,
    )


@router.post(
    "/competitions/{competition_id}/stages/{stage_id}/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def open_submission(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    actor: CompetitorUserDep,
    request: Request,
) -> SubmissionOut:
    ip, ua = client_meta(request)
    sub = await submission_service.open_submission(
        session, competition_id=competition_id, stage_id=stage_id, actor=actor, ip=ip, user_agent=ua
    )
    # Idempotent reopen returns 200 semantics via same body; keep 201 for create-or-get
    return _submission_out(sub)


@router.post("/submissions/{submission_id}/artefacts", status_code=status.HTTP_202_ACCEPTED)
async def upload_artefact(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: CompetitorUserDep,
    request: Request,
    response: Response,
    deliverable_code: str = Header(..., alias="X-Deliverable-Code"),
    filename: str = Header(..., alias="X-Filename"),
    content_type: str | None = Header(default=None, alias="X-Content-Type"),
) -> ArtefactUploadOut:
    ip, ua = client_meta(request)
    data = await request.body()
    if not data:
        raise AppError("VALIDATION_ERROR", "Empty body", status_code=422)
    artefact = await submission_service.upload_artefact(
        session,
        submission_id,
        actor=actor,
        deliverable_code=deliverable_code,
        filename=filename,
        content_type=content_type,
        data=data,
        ip=ip,
        user_agent=ua,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return ArtefactUploadOut(
        artefactId=artefact.id,
        scan=artefact.scan_status,
        complete=artefact.complete,
        quarantined=artefact.quarantined,
        receivedBytes=artefact.received_bytes,
    )


@router.post(
    "/submissions/{submission_id}/artefacts/sessions",
    response_model=ArtefactSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def init_artefact_session(
    submission_id: uuid.UUID,
    payload: ArtefactSessionCreate,
    session: DBSessionDep,
    actor: CompetitorUserDep,
) -> ArtefactSessionOut:
    artefact = await submission_service.init_resumable_upload(
        session,
        submission_id,
        actor=actor,
        deliverable_code=payload.deliverableCode,
        filename=payload.filename,
        content_type=payload.contentType,
        total_size=payload.totalSize,
    )
    assert artefact.upload_id is not None
    assert artefact.total_size is not None
    return ArtefactSessionOut(
        uploadId=artefact.upload_id,
        artefactId=artefact.id,
        receivedBytes=artefact.received_bytes,
        totalSize=artefact.total_size,
    )


@router.put(
    "/submissions/{submission_id}/artefacts/sessions/{upload_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def append_artefact_chunk(
    submission_id: uuid.UUID,
    upload_id: str,
    session: DBSessionDep,
    actor: CompetitorUserDep,
    request: Request,
    content_range: str | None = Header(default=None, alias="Content-Range"),
) -> ArtefactUploadOut:
    ip, ua = client_meta(request)
    data = await request.body()
    artefact = await submission_service.append_resumable_chunk(
        session,
        submission_id,
        upload_id,
        actor=actor,
        data=data,
        content_range=content_range,
        ip=ip,
        user_agent=ua,
    )
    return ArtefactUploadOut(
        artefactId=artefact.id,
        uploadId=artefact.upload_id,
        scan=artefact.scan_status,
        receivedBytes=artefact.received_bytes,
        complete=artefact.complete,
        quarantined=artefact.quarantined,
    )


@router.post("/submissions/{submission_id}:finalise", response_model=FinaliseOut)
async def finalise_submission(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: CompetitorUserDep,
    request: Request,
) -> FinaliseOut:
    ip, ua = client_meta(request)
    sub = await submission_service.finalise_submission(
        session, submission_id, actor=actor, ip=ip, user_agent=ua
    )
    return FinaliseOut(
        state=sub.state,
        hash=sub.content_hash,
        receipt=sub.receipt,
        late=sub.late,
    )


@router.post("/submissions/{submission_id}:expire-timer", response_model=FinaliseOut)
async def expire_timer(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: CompetitorUserDep,
    request: Request,
) -> FinaliseOut:
    ip, ua = client_meta(request)
    sub = await submission_service.expire_timer(
        session, submission_id, actor=actor, ip=ip, user_agent=ua
    )
    return FinaliseOut(
        state=sub.state,
        hash=sub.content_hash,
        receipt=sub.receipt,
        late=sub.late,
    )
