"""US-SUB-01 Exercise API — configure/publish challenge per stage."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import Response

from app.core.rbac import Capability
from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.schemas.exercises import DeliverableItem, ExerciseNotifyOut, ExerciseOut, ExercisePut
from app.schemas.competition_config import ExerciseRubricOut, ExerciseRubricPut
from app.services import competition_sms
from app.services import exercises as exercise_service

PublishUserDep = Annotated[object, Depends(require_capability(Capability.PUBLISH_TEST_PROJECT))]

router = APIRouter(prefix="/competitions", tags=["exercises"])


async def _out(session, ex) -> ExerciseOut:
    scheme = await exercise_service.load_scheme_for_exercise(session, ex)
    has, blind, count = exercise_service.rubric_meta(scheme)
    return ExerciseOut(
        exerciseId=ex.id,
        stageId=ex.stage_id,
        competitionId=ex.competition_id,
        title=ex.title,
        brief=ex.brief,
        deliverables=[DeliverableItem(**d) for d in (ex.deliverables or [])],
        status=ex.status,
        schemeId=ex.scheme_id,
        latePolicy=ex.late_policy,
        timedDurationSeconds=ex.timed_duration_seconds,
        packFileName=ex.pack_file_name,
        packContentType=ex.pack_content_type,
        packScanStatus=ex.pack_scan_status,
        hasRubricCriteria=has,
        blindMode=blind,
        criteriaCount=count,
        availabilityNotifiedAt=(
            ex.availability_notified_at.isoformat() if ex.availability_notified_at else None
        ),
    )


@router.get("/{competition_id}/stages/{stage_id}/exercise", response_model=ExerciseOut)
async def get_exercise(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> ExerciseOut:
    """Admins see drafts; registered competitors see PUBLISHED exercises only."""
    ex = await exercise_service.get_exercise_for_actor(
        session, competition_id, stage_id, actor=user
    )
    return await _out(session, ex)


@router.put("/{competition_id}/stages/{stage_id}/exercise", response_model=ExerciseOut)
async def put_exercise(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: ExercisePut,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ExerciseOut:
    ip, ua = client_meta(request)
    ex = await exercise_service.upsert_exercise(
        session, competition_id, stage_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return await _out(session, ex)


@router.get(
    "/{competition_id}/stages/{stage_id}/exercise/rubric",
    response_model=ExerciseRubricOut,
)
async def get_exercise_rubric(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> ExerciseRubricOut:
    _ = admin
    return await exercise_service.get_exercise_rubric(session, competition_id, stage_id)


@router.put(
    "/{competition_id}/stages/{stage_id}/exercise/rubric",
    response_model=ExerciseRubricOut,
)
async def put_exercise_rubric(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: ExerciseRubricPut,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ExerciseRubricOut:
    ip, ua = client_meta(request)
    return await exercise_service.put_exercise_rubric(
        session,
        competition_id,
        stage_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )


@router.post(
    "/{competition_id}/stages/{stage_id}/exercise:publish",
    response_model=ExerciseOut,
)
async def publish_exercise(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
    request: Request,
    _cap: PublishUserDep,
) -> ExerciseOut:
    ip, ua = client_meta(request)
    ex = await exercise_service.publish_exercise(
        session, competition_id, stage_id, actor=user, ip=ip, user_agent=ua
    )
    return await _out(session, ex)


@router.post(
    "/{competition_id}/stages/{stage_id}/exercise:unpublish",
    response_model=ExerciseOut,
)
async def unpublish_exercise(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
    request: Request,
    _cap: PublishUserDep,
) -> ExerciseOut:
    ip, ua = client_meta(request)
    ex = await exercise_service.unpublish_exercise(
        session, competition_id, stage_id, actor=user, ip=ip, user_agent=ua
    )
    return await _out(session, ex)


@router.post(
    "/{competition_id}/stages/{stage_id}/exercise:notify",
    response_model=ExerciseNotifyOut,
)
async def notify_exercise_available(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> ExerciseNotifyOut:
    """Manually notify competitors and coaches that the exercise is available."""
    summary = await competition_sms.notify_exercise_available(
        session,
        competition_id=competition_id,
        stage_id=stage_id,
        trigger="admin_notify",
        actor=admin,
        force=True,
        commit=True,
    )
    ex = await exercise_service.get_exercise(session, competition_id, stage_id)
    return ExerciseNotifyOut(
        competitorsConsidered=summary.competitors_considered,
        competitorSent=summary.competitor_sent,
        coachSent=summary.coach_sent,
        failed=summary.failed,
        skippedNotReady=summary.skipped_not_ready,
        skippedAlreadyNotified=summary.skipped_already_notified,
        availabilityNotifiedAt=(
            ex.availability_notified_at.isoformat() if ex.availability_notified_at else None
        ),
    )


@router.post("/{competition_id}/stages/{stage_id}/exercise/pack", response_model=ExerciseOut)
async def upload_pack(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
    file: UploadFile = File(...),
) -> ExerciseOut:
    ip, ua = client_meta(request)
    data = await file.read()
    ex = await exercise_service.upload_exercise_pack(
        session,
        competition_id,
        stage_id,
        actor=admin,
        data=data,
        filename=file.filename or "pack.pdf",
        content_type=file.content_type,
        ip=ip,
        user_agent=ua,
    )
    return await _out(session, ex)


@router.delete("/{competition_id}/stages/{stage_id}/exercise/pack", response_model=ExerciseOut)
async def delete_pack(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ExerciseOut:
    ip, ua = client_meta(request)
    ex = await exercise_service.delete_exercise_pack(
        session, competition_id, stage_id, actor=admin, ip=ip, user_agent=ua
    )
    return await _out(session, ex)


@router.get("/{competition_id}/stages/{stage_id}/exercise/pack")
async def download_pack(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> Response:
    data, filename, content_type = await exercise_service.download_exercise_pack(
        session, competition_id, stage_id, actor=user
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
