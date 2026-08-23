from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.rbac import Capability
from app.dependencies.auth import CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.assessment import AssessmentViewOut, ScorePut, ScorePutOut
from app.schemas.assignments import AssessorQueueOut, MyAssignmentOut
from app.schemas.moderation import ModerationAnalyseOut, ModerationApplyIn, ModerationApplyOut
from app.schemas.scoring_overview import (
    ResolveTotalIn,
    ResolveTotalOut,
    ScoringDetailOut,
    ScoringListItemOut,
)
from app.services import assessment as assessment_service
from app.services import assignments as assignment_service
from app.services import moderation as moderation_service
from app.services import scoring_overview as scoring_overview_service

router = APIRouter(tags=["assessment"])

ScorerDep = Annotated[User, Depends(require_capability(Capability.SCORE_SUBMISSION))]
ModeratorDep = Annotated[User, Depends(require_capability(Capability.MODERATE_SCORE))]


def _attachment_filename(filename: str) -> str:
    safe = filename.replace('"', "").replace("\r", "").replace("\n", "") or "download"
    return safe


@router.get("/assessors/me/assignments", response_model=list[MyAssignmentOut])
async def list_my_assignments(
    session: DBSessionDep,
    user: CurrentUserDep,
) -> list[MyAssignmentOut]:
    """Expert portal discovery — competitions/skills/zones assigned to the signed-in assessor."""
    return await assignment_service.list_my_assignments(session, actor=user)


@router.get("/assessors/{expert_id}/queue", response_model=AssessorQueueOut)
async def get_assessor_queue_spec(
    expert_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
    competition_id: uuid.UUID = Query(..., alias="competitionId"),
) -> AssessorQueueOut:
    """US-ASM-01 queue — experts may fetch their own; admins may fetch any."""
    from app.core.rbac import is_admin_role

    if user.id != expert_id and not is_admin_role(user.role):
        from app.core.errors import AppError

        raise AppError("FORBIDDEN", "Cannot view another assessor's queue", status_code=403)
    return await assignment_service.get_assessor_queue(session, competition_id, expert_id)


@router.get(
    "/competitions/{competition_id}/scoring",
    response_model=list[ScoringListItemOut],
)
async def list_scoring_overview(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: ModeratorDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    stageId: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ScoringListItemOut]:
    return await scoring_overview_service.list_scoring_overview(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        stage_id=stageId,
    )


@router.get("/submissions/{submission_id}/scoring", response_model=ScoringDetailOut)
async def get_scoring_detail(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: ModeratorDep,
) -> ScoringDetailOut:
    return await scoring_overview_service.get_scoring_detail(
        session, submission_id, actor=actor
    )


@router.post(
    "/submissions/{submission_id}/scoring:resolve-total",
    response_model=ResolveTotalOut,
)
async def resolve_submission_total(
    submission_id: uuid.UUID,
    payload: ResolveTotalIn,
    session: DBSessionDep,
    actor: ModeratorDep,
    request: Request,
) -> ResolveTotalOut:
    ip, ua = client_meta(request)
    return await scoring_overview_service.resolve_submission_total(
        session,
        submission_id,
        payload,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.get("/submissions/{submission_id}/assessment", response_model=AssessmentViewOut)
async def get_assessment(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: ScorerDep,
    request: Request,
) -> AssessmentViewOut:
    ip, ua = client_meta(request)
    return await assessment_service.get_assessment_view(
        session, submission_id, actor=actor, ip=ip, user_agent=ua
    )


@router.get("/submissions/{submission_id}/artefacts/{artefact_id}/download")
async def download_assessment_artefact(
    submission_id: uuid.UUID,
    artefact_id: uuid.UUID,
    session: DBSessionDep,
    actor: ScorerDep,
    request: Request,
) -> Response:
    ip, ua = client_meta(request)
    data, filename, content_type = await assessment_service.download_assessment_artefact(
        session,
        submission_id,
        artefact_id,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )
    safe_name = _attachment_filename(filename)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.put("/submissions/{submission_id}/scores", response_model=ScorePutOut)
async def put_scores(
    submission_id: uuid.UUID,
    payload: ScorePut,
    session: DBSessionDep,
    actor: ScorerDep,
    request: Request,
) -> ScorePutOut:
    ip, ua = client_meta(request)
    return await assessment_service.put_scores(
        session, submission_id, payload, actor=actor, ip=ip, user_agent=ua
    )


@router.post(
    "/submissions/{submission_id}/moderation:analyse",
    response_model=ModerationAnalyseOut,
)
async def analyse_moderation(
    submission_id: uuid.UUID,
    session: DBSessionDep,
    actor: ModeratorDep,
    request: Request,
) -> ModerationAnalyseOut:
    ip, ua = client_meta(request)
    return await moderation_service.analyse_moderation(
        session, submission_id, actor=actor, ip=ip, user_agent=ua
    )


@router.post("/submissions/{submission_id}/moderation", response_model=ModerationApplyOut)
async def apply_moderation(
    submission_id: uuid.UUID,
    payload: ModerationApplyIn,
    session: DBSessionDep,
    actor: ModeratorDep,
    request: Request,
) -> ModerationApplyOut:
    ip, ua = client_meta(request)
    return await moderation_service.apply_moderation(
        session, submission_id, payload, actor=actor, ip=ip, user_agent=ua
    )
