from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.assignments import (
    AssignmentCreate,
    AssignmentOut,
    AssessorQueueOut,
    DelegateIn,
)
from app.services import assignments as assignment_service

router = APIRouter(prefix="/cycles", tags=["assignments"])


@router.post(
    "/{cycle_id}/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    cycle_id: uuid.UUID,
    payload: AssignmentCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> AssignmentOut:
    ip, ua = client_meta(request)
    assignment = await assignment_service.create_assignment(
        session, cycle_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return AssignmentOut(
        assignmentId=assignment.id,
        cycleId=assignment.cycle_id,
        expertId=assignment.expert_id,
        skillId=assignment.skill_id,
        zoneId=assignment.zone_id,
        coiFlags=assignment_service.coi_flags_out(assignment.coi_flags),
    )


@router.get("/{cycle_id}/assessors/{expert_id}/queue", response_model=AssessorQueueOut)
async def get_assessor_queue(
    cycle_id: uuid.UUID,
    expert_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> AssessorQueueOut:
    return await assignment_service.get_assessor_queue(session, cycle_id, expert_id)


@router.post(
    "/{cycle_id}/assignments/{assignment_id}:delegate",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def delegate_assignment(
    cycle_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: DelegateIn,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> AssignmentOut:
    ip, ua = client_meta(request)
    assignment = await assignment_service.delegate_assignment(
        session,
        cycle_id,
        assignment_id,
        payload.expertId,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    return AssignmentOut(
        assignmentId=assignment.id,
        cycleId=assignment.cycle_id,
        expertId=assignment.expert_id,
        skillId=assignment.skill_id,
        zoneId=assignment.zone_id,
        coiFlags=assignment_service.coi_flags_out(assignment.coi_flags),
    )
