from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.assignments import (
    AssignmentCreate,
    AssignmentListOut,
    AssignmentOut,
    AssessorQueueOut,
    DelegateIn,
)
from app.services import assignments as assignment_service

router = APIRouter(prefix="/competitions", tags=["assignments"])


def _assignment_out(assignment) -> AssignmentOut:
    return AssignmentOut(
        assignmentId=assignment.id,
        competitionId=assignment.competition_id,
        expertId=assignment.expert_id,
        skillId=assignment.skill_id,
        cycleSkillId=assignment.skill_id,
        zoneId=assignment.zone_id,
        coiFlags=assignment_service.coi_flags_out(assignment.coi_flags),
    )


@router.get("/{competition_id}/assignments", response_model=AssignmentListOut)
async def list_assignments(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
    cycleSkillId: uuid.UUID | None = Query(default=None),
) -> AssignmentListOut:
    items = await assignment_service.list_assignments(
        session, competition_id, cycle_skill_id=cycleSkillId
    )
    return AssignmentListOut(items=[_assignment_out(a) for a in items])


@router.post(
    "/{competition_id}/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    competition_id: uuid.UUID,
    payload: AssignmentCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> AssignmentOut:
    ip, ua = client_meta(request)
    assignment = await assignment_service.create_assignment(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _assignment_out(assignment)


@router.get("/{competition_id}/assessors/{expert_id}/queue", response_model=AssessorQueueOut)
async def get_assessor_queue(
    competition_id: uuid.UUID,
    expert_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> AssessorQueueOut:
    return await assignment_service.get_assessor_queue(session, competition_id, expert_id)


@router.post(
    "/{competition_id}/assignments/{assignment_id}:delegate",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def delegate_assignment(
    competition_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: DelegateIn,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> AssignmentOut:
    ip, ua = client_meta(request)
    assignment = await assignment_service.delegate_assignment(
        session,
        competition_id,
        assignment_id,
        payload.expertId,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    return _assignment_out(assignment)
