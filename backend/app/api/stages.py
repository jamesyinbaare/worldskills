from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import Exercise
from app.schemas.stages import PathwayOut, PathwayPut, StageOut
from app.services import stages as stage_service

router = APIRouter(prefix="/competitions", tags=["stages"])


async def _stage_outs(session, stages) -> list[StageOut]:
    if not stages:
        return []
    stage_ids = [s.id for s in stages]
    result = await session.execute(select(Exercise).where(Exercise.stage_id.in_(stage_ids)))
    by_stage = {ex.stage_id: ex for ex in result.scalars().all()}
    outs: list[StageOut] = []
    for s in stages:
        ex = by_stage.get(s.id)
        outs.append(
            StageOut(
                stageId=s.id,
                order=s.order,
                type=s.stage_type,
                selectionMode=s.selection_mode or "PER_ZONE",
                schemeId=ex.scheme_id if ex else None,
                exerciseStatus=ex.status if ex else None,
                opensAt=s.opens_at,
                closesAt=s.closes_at,
                branch=s.branch,
                quotaByZone=s.quota_by_zone,
                minScore=s.min_score,
                quota=s.quota,
            )
        )
    return outs


@router.get("/{competition_id}/skills/{skill_id}/pathway", response_model=PathwayOut)
async def get_pathway(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> PathwayOut:
    _ = admin
    stages, finalists = await stage_service.get_skill_pathway(session, competition_id, skill_id)
    return PathwayOut(
        stages=await _stage_outs(session, stages),
        finalistsPerSkill=finalists or 0,
    )


@router.put("/{competition_id}/skills/{skill_id}/pathway", response_model=PathwayOut)
async def put_pathway(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    payload: PathwayPut,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> PathwayOut:
    ip, ua = client_meta(request)
    stages, finalists = await stage_service.put_skill_pathway(
        session,
        competition_id,
        skill_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    return PathwayOut(
        stages=await _stage_outs(session, stages),
        finalistsPerSkill=finalists,
    )
