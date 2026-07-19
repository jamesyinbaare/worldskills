from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.cycles import (
    ActivateOut,
    CloneOut,
    CycleCreate,
    CycleListItem,
    CycleOut,
    CycleUpdateStructural,
    PeriodIn,
    ValidateOut,
)
from app.services import cycles as cycle_service

router = APIRouter(prefix="/cycles", tags=["cycles"])


@router.get("", response_model=list[CycleListItem])
async def list_cycles(session: DBSessionDep, _admin: AdminUserDep) -> list[CycleListItem]:
    items = await cycle_service.list_cycles(session)
    return [
        CycleListItem(
            cycleId=c.id,
            name=c.name,
            status=c.status.value,
            period=PeriodIn(start=c.period_start, end=c.period_end),
            timeZone=c.time_zone,
            languages=list(c.languages or []),
        )
        for c in items
    ]


@router.post("", response_model=CycleOut, status_code=status.HTTP_201_CREATED)
async def create_cycle(
    payload: CycleCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CycleOut:
    ip, ua = client_meta(request)
    cycle = await cycle_service.create_cycle(session, payload, actor=admin, ip=ip, user_agent=ua)
    return CycleOut(cycleId=cycle.id, status=cycle.status.value)


@router.get("/{cycle_id}", response_model=CycleOut)
async def get_cycle(cycle_id: uuid.UUID, session: DBSessionDep, _admin: AdminUserDep) -> CycleOut:
    cycle = await cycle_service.get_cycle(session, cycle_id)
    return CycleOut(
        cycleId=cycle.id,
        status=cycle.status.value,
        name=cycle.name,
        period=PeriodIn(start=cycle.period_start, end=cycle.period_end),
        timeZone=cycle.time_zone,
        languages=list(cycle.languages or []),
    )


@router.post("/{cycle_id}:clone", response_model=CloneOut, status_code=status.HTTP_201_CREATED)
async def clone_cycle(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CloneOut:
    ip, ua = client_meta(request)
    cycle = await cycle_service.clone_cycle(session, cycle_id, actor=admin, ip=ip, user_agent=ua)
    return CloneOut(newCycleId=cycle.id)


@router.post("/{cycle_id}:validate", response_model=ValidateOut)
async def validate_cycle(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> ValidateOut:
    ok, issues = await cycle_service.validate_cycle(session, cycle_id)
    return ValidateOut(ok=ok, issues=issues)


@router.post("/{cycle_id}:activate", response_model=ActivateOut)
async def activate_cycle(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ActivateOut:
    ip, ua = client_meta(request)
    cycle = await cycle_service.activate_cycle(session, cycle_id, actor=admin, ip=ip, user_agent=ua)
    return ActivateOut(status=cycle.status.value)


@router.patch("/{cycle_id}", response_model=CycleOut)
async def update_cycle(
    cycle_id: uuid.UUID,
    payload: CycleUpdateStructural,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> CycleOut:
    cycle = await cycle_service.update_cycle_structural(
        session, cycle_id, name=payload.name, actor=admin
    )
    return CycleOut(
        cycleId=cycle.id,
        status=cycle.status.value,
        name=cycle.name,
        period=PeriodIn(start=cycle.period_start, end=cycle.period_end),
        timeZone=cycle.time_zone,
        languages=list(cycle.languages or []),
    )
