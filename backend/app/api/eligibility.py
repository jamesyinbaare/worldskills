from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.eligibility import EligibilityOverrideIn, EligibilityOverrideOut, ScreenOut
from app.services import eligibility as eligibility_service

router = APIRouter(tags=["eligibility"])


@router.post("/competitors/{competitor_id}:screen", response_model=ScreenOut)
async def screen_competitor(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ScreenOut:
    ip, ua = client_meta(request)
    return await eligibility_service.screen_competitor(
        session, competitor_id, actor=admin, ip=ip, user_agent=ua
    )


@router.post("/competitors/{competitor_id}/eligibility:override", response_model=EligibilityOverrideOut)
async def override_eligibility(
    competitor_id: uuid.UUID,
    payload: EligibilityOverrideIn,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> EligibilityOverrideOut:
    ip, ua = client_meta(request)
    return await eligibility_service.override_eligibility(
        session, competitor_id, payload, actor=admin, ip=ip, user_agent=ua
    )
