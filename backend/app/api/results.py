"""US-RES-01 results publication API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.rbac import Capability
from app.dependencies.auth import CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.results import (
    CompetitorResultsOut,
    CorrectResultIn,
    CorrectResultOut,
    PrepareResultsIn,
    PrepareResultsOut,
    PublicResultsOut,
    ReleaseResultsIn,
    ReleaseResultsOut,
)
from app.services import results as results_service

router = APIRouter(tags=["results"])

PublishUserDep = Annotated[User, Depends(require_capability(Capability.PUBLISH_RESULTS))]


@router.post("/cycles/{cycle_id}/results:prepare", response_model=PrepareResultsOut)
async def prepare_results(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
    body: PrepareResultsIn = PrepareResultsIn(),
) -> PrepareResultsOut:
    ip, ua = client_meta(request)
    return await results_service.prepare_results(
        session,
        cycle_id,
        actor=actor,
        skill_id=body.skillId,
        ip=ip,
        user_agent=ua,
    )


@router.post("/cycles/{cycle_id}/results:release", response_model=ReleaseResultsOut)
async def release_results(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
    body: ReleaseResultsIn = ReleaseResultsIn(),
) -> ReleaseResultsOut:
    ip, ua = client_meta(request)
    return await results_service.release_results(
        session,
        cycle_id,
        actor=actor,
        manual=body.manual,
        skill_id=body.skillId,
        ip=ip,
        user_agent=ua,
    )


@router.post("/results/{result_id}:correct", response_model=CorrectResultOut)
async def correct_result(
    result_id: uuid.UUID,
    body: CorrectResultIn,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
) -> CorrectResultOut:
    ip, ua = client_meta(request)
    return await results_service.correct_result(
        session,
        result_id,
        changes=body.changes,
        reason=body.reason,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.get("/public/cycles/{cycle_id}/results", response_model=PublicResultsOut)
async def public_results(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
) -> PublicResultsOut:
    return await results_service.get_public_results(session, cycle_id)


@router.get("/cycles/{cycle_id}/results/me", response_model=CompetitorResultsOut)
async def my_results(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    actor: CurrentUserDep,
) -> CompetitorResultsOut:
    return await results_service.get_competitor_results(session, cycle_id, actor=actor)
