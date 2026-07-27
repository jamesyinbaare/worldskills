from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.nominations import NominationCreate, NominationOut, NominationRejectIn
from app.services import nominations as nomination_service

router = APIRouter(tags=["nominations"])


@router.post(
    "/competitions/{competition_id}/nominations",
    response_model=NominationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_nomination(
    competition_id: uuid.UUID,
    payload: NominationCreate,
    session: DBSessionDep,
    user: CurrentUserDep,
    request: Request,
) -> NominationOut:
    ip, ua = client_meta(request)
    nomination = await nomination_service.create_nomination(
        session, competition_id, payload, actor=user, ip=ip, user_agent=ua
    )
    return NominationOut(
        nominationId=nomination.id,
        status=nomination.status.value,
        competitorId=nomination.competitor_id,
    )


@router.post("/nominations/{nomination_id}:approve", response_model=NominationOut)
async def approve_nomination(
    nomination_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> NominationOut:
    ip, ua = client_meta(request)
    nomination = await nomination_service.approve_nomination(
        session, nomination_id, actor=admin, ip=ip, user_agent=ua
    )
    return NominationOut(
        nominationId=nomination.id,
        status=nomination.status.value,
        competitorId=nomination.competitor_id,
    )


@router.post("/nominations/{nomination_id}:reject", response_model=NominationOut)
async def reject_nomination(
    nomination_id: uuid.UUID,
    payload: NominationRejectIn,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> NominationOut:
    ip, ua = client_meta(request)
    nomination = await nomination_service.reject_nomination(
        session, nomination_id, reason=payload.reason, actor=admin, ip=ip, user_agent=ua
    )
    return NominationOut(
        nominationId=nomination.id,
        status=nomination.status.value,
        competitorId=nomination.competitor_id,
        reason=nomination.reason,
    )
