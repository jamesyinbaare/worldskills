"""Admin competitor roster API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.rbac import Capability
from app.dependencies.auth import require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.competitors_admin import AdminCompetitorItem, SkillSmsSendIn, SkillSmsSendOut
from app.services import competition_sms
from app.services import competitors_admin as competitors_admin_service

router = APIRouter(tags=["competitors-admin"])

CycleAdminDep = Annotated[User, Depends(require_capability(Capability.CONFIGURE_CYCLE))]


@router.get(
    "/competitions/{competition_id}/competitors",
    response_model=list[AdminCompetitorItem],
)
async def list_competitors(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: CycleAdminDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[AdminCompetitorItem]:
    return await competitors_admin_service.list_admin_competitors(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
        status_filter=status,
    )


@router.get("/competitions/{competition_id}/competitors:export")
async def export_competitors(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: CycleAdminDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> Response:
    data, filename = await competitors_admin_service.export_admin_competitors_xlsx(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
        status_filter=status,
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/competitions/{competition_id}/skills/{skill_id}:sms",
    response_model=SkillSmsSendOut,
)
async def send_skill_sms(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    payload: SkillSmsSendIn,
    session: DBSessionDep,
    actor: CycleAdminDep,
) -> SkillSmsSendOut:
    summary = await competition_sms.send_skill_broadcast_sms(
        session,
        competition_id=competition_id,
        skill_id=skill_id,
        recipients=payload.recipients,
        template_key=payload.templateKey,
        message=payload.message,
        competitor_ids=payload.competitorIds,
        actor=actor,
        trigger="admin_skill_sms",
        commit=True,
    )
    return SkillSmsSendOut(
        competitorsConsidered=summary.competitors_considered,
        competitorSent=summary.competitor_sent,
        coachSent=summary.coach_sent,
        failed=summary.failed,
        skippedNoPhone=summary.skipped_no_phone,
        recipients=summary.recipients,
        templateKey=summary.template_key,
    )
