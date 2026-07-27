"""US-APP-01 appeals and disqualification API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.rbac import Capability
from app.dependencies.auth import CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.appeals import (
    AppealAssignIn,
    AppealListItem,
    AppealLodgeIn,
    AppealOut,
    AppealRuleIn,
    DisqualifyIn,
    DisqualifyOut,
)
from app.services import appeals as appeals_service

router = APIRouter(tags=["appeals"])

AppealsOfficerDep = Annotated[User, Depends(require_capability(Capability.RULE_ON_APPEAL))]


@router.get(
    "/competitions/{competition_id}/appeals",
    response_model=list[AppealListItem],
)
async def list_appeals(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: AppealsOfficerDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> list[AppealListItem]:
    return await appeals_service.list_appeals(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
        state=state,
    )


@router.post(
    "/competitions/{competition_id}/appeals",
    response_model=AppealOut,
    status_code=status.HTTP_201_CREATED,
)
async def lodge_appeal(
    competition_id: uuid.UUID,
    body: AppealLodgeIn,
    session: DBSessionDep,
    actor: CurrentUserDep,
    request: Request,
) -> AppealOut:
    ip, ua = client_meta(request)
    return await appeals_service.lodge_appeal(
        session,
        competition_id,
        competitor_id=body.competitorId,
        stage_id=body.stageId,
        reason=body.reason,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post("/appeals/{appeal_id}:assign", response_model=AppealOut)
async def assign_appeal(
    appeal_id: uuid.UUID,
    body: AppealAssignIn,
    session: DBSessionDep,
    actor: AppealsOfficerDep,
    request: Request,
) -> AppealOut:
    ip, ua = client_meta(request)
    return await appeals_service.assign_appeal(
        session,
        appeal_id,
        officer_id=body.officerId,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post("/appeals/{appeal_id}:rule", response_model=AppealOut)
async def rule_appeal(
    appeal_id: uuid.UUID,
    body: AppealRuleIn,
    session: DBSessionDep,
    actor: AppealsOfficerDep,
    request: Request,
) -> AppealOut:
    ip, ua = client_meta(request)
    return await appeals_service.rule_appeal(
        session,
        appeal_id,
        outcome=body.outcome,
        reason=body.reason,
        remedy=body.remedy,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.post("/competitors/{competitor_id}:disqualify", response_model=DisqualifyOut)
async def disqualify_competitor(
    competitor_id: uuid.UUID,
    body: DisqualifyIn,
    session: DBSessionDep,
    actor: AppealsOfficerDep,
    request: Request,
) -> DisqualifyOut:
    ip, ua = client_meta(request)
    return await appeals_service.disqualify_competitor(
        session,
        competitor_id,
        reason=body.reason,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )
