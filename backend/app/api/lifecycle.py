"""US-LCY-01 competitor lifecycle API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.lifecycle import SubstituteIn, SubstituteOut, WithdrawIn, WithdrawOut
from app.services import lifecycle as lifecycle_service

router = APIRouter(tags=["lifecycle"])


@router.post("/competitors/{competitor_id}:withdraw", response_model=WithdrawOut)
async def withdraw_competitor(
    competitor_id: uuid.UUID,
    body: WithdrawIn,
    session: DBSessionDep,
    actor: CurrentUserDep,
    request: Request,
) -> WithdrawOut:
    ip, ua = client_meta(request)
    return await lifecycle_service.withdraw_competitor(
        session,
        competitor_id,
        reason=body.reason,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post("/competitors/{competitor_id}:substitute", response_model=SubstituteOut)
async def substitute_competitor(
    competitor_id: uuid.UUID,
    body: SubstituteIn,
    session: DBSessionDep,
    actor: CurrentUserDep,
    request: Request,
) -> SubstituteOut:
    ip, ua = client_meta(request)
    return await lifecycle_service.substitute_competitor(
        session,
        competitor_id,
        replacement=body.replacement,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )
