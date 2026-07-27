"""US-AUD-01 audit query and DSAR API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.errors import AppError, FieldError
from app.core.rbac import is_admin_role
from app.dependencies.auth import CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.governance import AuditListOut, DsarCreateIn, DsarJobOut
from app.services import governance as governance_service

router = APIRouter(tags=["governance"])


async def require_admin_user(user: CurrentUserDep) -> User:
    if not is_admin_role(user.role):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)
    return user


AdminUserDep = Annotated[User, Depends(require_admin_user)]


@router.get("/admin/audit", response_model=AuditListOut)
async def list_audit(
    session: DBSessionDep,
    _admin: AdminUserDep,
    entity: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditListOut:
    actor_id: uuid.UUID | None = None
    if actor and actor.strip():
        try:
            actor_id = uuid.UUID(actor.strip())
        except ValueError as exc:
            raise AppError(
                "VALIDATION_ERROR",
                "actor must be a UUID",
                status_code=422,
                fields=[FieldError("actor", "UUID_PARSING")],
            ) from exc
    return await governance_service.list_audit_events(
        session,
        entity=entity.strip() if entity and entity.strip() else None,
        actor=actor_id,
        from_ts=from_,
        to_ts=to,
        limit=limit,
    )


@router.delete("/admin/audit/{event_id}")
async def delete_audit_event(
    event_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> None:
    ip, ua = client_meta(request)
    await governance_service.refuse_audit_mutation(
        session,
        event_id=event_id,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )


@router.post(
    "/governance/dsar",
    response_model=DsarJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_dsar(
    body: DsarCreateIn,
    session: DBSessionDep,
    actor: CurrentUserDep,
    request: Request,
) -> DsarJobOut:
    ip, ua = client_meta(request)
    return await governance_service.create_and_process_dsar(
        session,
        subject_id=body.subjectId,
        request_type=body.type,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.get("/governance/dsar/{job_id}", response_model=DsarJobOut)
async def get_dsar(
    job_id: uuid.UUID,
    session: DBSessionDep,
    actor: CurrentUserDep,
) -> DsarJobOut:
    return await governance_service.get_dsar_job(session, job_id, actor=actor)
