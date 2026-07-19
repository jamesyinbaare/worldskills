from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Request, Response

from app.dependencies.auth import client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.registrations import RegistrationCreate, RegistrationFormOut, RegistrationOut
from app.services import registrations as registration_service

router = APIRouter(prefix="/cycles", tags=["registrations"])


@router.get("/{cycle_id}/registration-form", response_model=RegistrationFormOut)
async def get_registration_form(cycle_id: uuid.UUID, session: DBSessionDep) -> RegistrationFormOut:
    return await registration_service.get_registration_form(session, cycle_id)


@router.post("/{cycle_id}/registrations", response_model=RegistrationOut, status_code=201)
async def create_registration(
    cycle_id: uuid.UUID,
    payload: RegistrationCreate,
    session: DBSessionDep,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RegistrationOut:
    """Public registration endpoint — CAPTCHA / rate-limit gates abuse (US-REG-01-AC5)."""
    ip, ua = client_meta(request)
    out, code = await registration_service.create_registration(
        session,
        cycle_id,
        payload,
        idempotency_key=idempotency_key,
        actor_role="ANONYMOUS",
        ip=ip,
        user_agent=ua,
    )
    response.status_code = code
    return out
