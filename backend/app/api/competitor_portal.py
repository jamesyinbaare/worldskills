"""Competitor portal discovery APIs — my registrations and stages."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies.auth import CurrentUserDep
from app.dependencies.database import DBSessionDep
from app.schemas.competitor_portal import MyRegistrationOut, MyStagesOut
from app.services import competitor_portal as portal_service

router = APIRouter(tags=["competitor-portal"])


@router.get("/competitors/me/registrations", response_model=list[MyRegistrationOut])
async def list_my_registrations(
    session: DBSessionDep,
    user: CurrentUserDep,
) -> list[MyRegistrationOut]:
    return await portal_service.list_my_registrations(session, actor=user)


@router.get("/competitions/{competition_id}/me/stages", response_model=MyStagesOut)
async def get_my_stages(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> MyStagesOut:
    return await portal_service.get_my_stages(session, competition_id, actor=user)
