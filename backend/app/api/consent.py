from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.consent import (
    ConsentGrantIn,
    ConsentGrantOut,
    ConsentRequestIn,
    ConsentRequestOut,
    ConsentWithdrawOut,
)
from app.services import consent as consent_service

router = APIRouter(tags=["consent"])


@router.post("/competitors/{competitor_id}/consent-request", response_model=ConsentRequestOut)
async def create_consent_request(
    competitor_id: uuid.UUID,
    payload: ConsentRequestIn,
    session: DBSessionDep,
    request: Request,
) -> ConsentRequestOut:
    ip, ua = client_meta(request)
    return await consent_service.create_consent_request(
        session, competitor_id, payload, ip=ip, user_agent=ua
    )


@router.post("/consent/{token}:grant", response_model=ConsentGrantOut)
async def grant_consent(
    token: str,
    payload: ConsentGrantIn,
    session: DBSessionDep,
    request: Request,
) -> ConsentGrantOut:
    ip, ua = client_meta(request)
    return await consent_service.grant_consent(session, token, payload, ip=ip, user_agent=ua)


@router.post("/competitors/{competitor_id}/consent:withdraw", response_model=ConsentWithdrawOut)
async def withdraw_consent(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    request: Request,
) -> ConsentWithdrawOut:
    ip, ua = client_meta(request)
    return await consent_service.withdraw_consent(
        session, competitor_id, actor_role="GUARDIAN", ip=ip, user_agent=ua
    )
