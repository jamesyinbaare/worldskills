from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.rbac import Capability
from app.dependencies.auth import client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.shortlists import ShortlistConfirmOut, ShortlistGenerateOut
from app.services import shortlists as shortlist_service

router = APIRouter(prefix="/competitions", tags=["shortlists"])

ShortlistUserDep = Annotated[User, Depends(require_capability(Capability.APPROVE_SHORTLIST))]


@router.post("/{competition_id}/stages/{stage_id}:shortlist", response_model=ShortlistGenerateOut)
async def generate_shortlist(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    actor: ShortlistUserDep,
    request: Request,
) -> ShortlistGenerateOut:
    ip, ua = client_meta(request)
    return await shortlist_service.generate_shortlist(
        session, competition_id, stage_id, actor=actor, ip=ip, user_agent=ua
    )


@router.post(
    "/{competition_id}/stages/{stage_id}:confirm-shortlist",
    response_model=ShortlistConfirmOut,
)
async def confirm_shortlist(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    session: DBSessionDep,
    actor: ShortlistUserDep,
    request: Request,
) -> ShortlistConfirmOut:
    ip, ua = client_meta(request)
    return await shortlist_service.confirm_shortlist(
        session, competition_id, stage_id, actor=actor, ip=ip, user_agent=ua
    )
