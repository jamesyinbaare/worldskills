from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Request, Response

from app.core.errors import AppError
from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import UserRole
from app.schemas.registrations import (
    RegistrationCreate,
    RegistrationFormAdminOut,
    RegistrationFormAdminUpdate,
    RegistrationFormOut,
    RegistrationOut,
    RegistrationWindowOut,
    RegistrationWindowUpdate,
)
from app.services import registrations as registration_service

router = APIRouter(prefix="/competitions", tags=["registrations"])

_ALLOWED_REG_ROLES = {UserRole.COMPETITOR, UserRole.INSTITUTION}


def _assert_registration_actor(user) -> None:
    if user.role not in _ALLOWED_REG_ROLES:
        raise AppError(
            "FORBIDDEN",
            "Only COMPETITOR or INSTITUTION may access registration",
            status_code=403,
        )


@router.get("/{competition_id}/registration-window", response_model=RegistrationWindowOut | None)
async def get_registration_window(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> RegistrationWindowOut | None:
    return await registration_service.get_registration_window(session, competition_id)


@router.put("/{competition_id}/registration-window", response_model=RegistrationWindowOut)
async def put_registration_window(
    competition_id: uuid.UUID,
    payload: RegistrationWindowUpdate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> RegistrationWindowOut:
    ip, ua = client_meta(request)
    return await registration_service.upsert_registration_window(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )


@router.get("/{competition_id}/registration-form-admin", response_model=RegistrationFormAdminOut | None)
async def get_registration_form_admin(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> RegistrationFormAdminOut | None:
    return await registration_service.get_registration_form_admin(session, competition_id)


@router.put("/{competition_id}/registration-form-admin", response_model=RegistrationFormAdminOut)
async def put_registration_form_admin(
    competition_id: uuid.UUID,
    payload: RegistrationFormAdminUpdate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> RegistrationFormAdminOut:
    ip, ua = client_meta(request)
    return await registration_service.upsert_registration_form_admin(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )


@router.get("/{competition_id}/registration-form", response_model=RegistrationFormOut)
async def get_registration_form(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> RegistrationFormOut:
    _assert_registration_actor(user)
    return await registration_service.get_registration_form(session, competition_id)


@router.post("/{competition_id}/registrations", response_model=RegistrationOut, status_code=201)
async def create_registration(
    competition_id: uuid.UUID,
    payload: RegistrationCreate,
    session: DBSessionDep,
    request: Request,
    response: Response,
    user: CurrentUserDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RegistrationOut:
    """Auth-required registration — binds Competitor.userId for COMPETITOR actors (US-REG-01)."""
    _assert_registration_actor(user)
    ip, ua = client_meta(request)
    out, code = await registration_service.create_registration(
        session,
        competition_id,
        payload,
        idempotency_key=idempotency_key,
        actor=user,
        ip=ip,
        user_agent=ua,
    )
    response.status_code = code
    return out
