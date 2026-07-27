"""Admin competitor roster API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.rbac import Capability
from app.dependencies.auth import require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.competitors_admin import AdminCompetitorItem
from app.services import competitors_admin as competitors_admin_service

router = APIRouter(tags=["competitors-admin"])

CycleAdminDep = Annotated[User, Depends(require_capability(Capability.CONFIGURE_CYCLE))]


@router.get(
    "/competitions/{competition_id}/competitors",
    response_model=list[AdminCompetitorItem],
)
async def list_competitors(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: CycleAdminDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[AdminCompetitorItem]:
    return await competitors_admin_service.list_admin_competitors(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
        status_filter=status,
    )
