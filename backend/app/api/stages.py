from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.stages import PathwayOut, PathwayPut, StageOut
from app.services import stages as stage_service

router = APIRouter(prefix="/cycles", tags=["stages"])


@router.put("/{cycle_id}/skills/{skill_id}/pathway", response_model=PathwayOut)
async def put_pathway(
    cycle_id: uuid.UUID,
    skill_id: uuid.UUID,
    payload: PathwayPut,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> PathwayOut:
    ip, ua = client_meta(request)
    stages, finalists = await stage_service.put_skill_pathway(
        session,
        cycle_id,
        skill_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    return PathwayOut(
        stages=[
            StageOut(
                stageId=s.id,
                order=s.order,
                type=s.stage_type,
                schemeId=s.scheme_id,
                opensAt=s.opens_at,
                closesAt=s.closes_at,
                branch=s.branch,
                quotaByZone=s.quota_by_zone,
                minScore=s.min_score,
                quota=s.quota,
            )
            for s in stages
        ],
        finalistsPerSkill=finalists,
    )
