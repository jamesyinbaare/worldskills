"""US-SCH-01 scheduling API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.rbac import Capability
from app.dependencies.auth import client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.scheduling import (
    AssignmentCreateIn,
    AssignmentOut,
    IncidentCreateIn,
    IncidentOut,
    SessionCreateIn,
    SessionDetailOut,
    SessionListItem,
    SessionOut,
    VenueOut,
)
from app.services import scheduling as scheduling_service

router = APIRouter(tags=["scheduling"])

ScheduleAdminDep = Annotated[User, Depends(require_capability(Capability.CONFIGURE_CYCLE))]


@router.get(
    "/competitions/{competition_id}/venues",
    response_model=list[VenueOut],
)
async def list_venues(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
) -> list[VenueOut]:
    return await scheduling_service.list_venues(session, competition_id, actor=actor)


@router.get(
    "/competitions/{competition_id}/schedule/sessions",
    response_model=list[SessionListItem],
)
async def list_sessions(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> list[SessionListItem]:
    return await scheduling_service.list_sessions(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
    )


@router.get(
    "/schedule/sessions/{session_id}",
    response_model=SessionDetailOut,
)
async def get_session(
    session_id: uuid.UUID,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
) -> SessionDetailOut:
    return await scheduling_service.get_session_detail(session, session_id, actor=actor)


@router.post(
    "/competitions/{competition_id}/schedule/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    competition_id: uuid.UUID,
    body: SessionCreateIn,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
    request: Request,
) -> SessionOut:
    ip, ua = client_meta(request)
    return await scheduling_service.create_session(
        session,
        competition_id,
        venue_id=body.venueId,
        starts_at=body.startsAt,
        ends_at=body.endsAt,
        workstations=body.workstations,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post(
    "/schedule/sessions/{session_id}/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_slot(
    session_id: uuid.UUID,
    body: AssignmentCreateIn,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
    request: Request,
) -> AssignmentOut:
    ip, ua = client_meta(request)
    return await scheduling_service.assign_slot(
        session,
        session_id,
        competitor_id=body.competitorId,
        workstation=body.workstation,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post(
    "/schedule/sessions/{session_id}/incidents",
    response_model=IncidentOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_incident(
    session_id: uuid.UUID,
    body: IncidentCreateIn,
    session: DBSessionDep,
    actor: ScheduleAdminDep,
    request: Request,
) -> IncidentOut:
    ip, ua = client_meta(request)
    return await scheduling_service.record_incident(
        session,
        session_id,
        summary=body.summary,
        severity=body.severity,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )
