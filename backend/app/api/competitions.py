from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import Response

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.competitions import (
    ActivateOut,
    CloneOut,
    CompetitionCreate,
    CompetitionListItem,
    CompetitionOut,
    CompetitionPublicProfileUpdate,
    CompetitionUpdateStructural,
    OpenCompetitionOut,
    PeriodIn,
    PublicCompetitionOut,
    ValidateOut,
)
from app.services import competitions as competition_service
from app.services import skills as skill_service

router = APIRouter(prefix="/competitions", tags=["competitions"])


def _cycle_out(cycle) -> CompetitionOut:
    return CompetitionOut(
        competitionId=cycle.id,
        status=cycle.status.value,
        name=cycle.name,
        period=PeriodIn(start=cycle.period_start, end=cycle.period_end),
        timeZone=cycle.time_zone,
        languages=list(cycle.languages or []),
        description=cycle.description,
    )


@router.get(":open-for-registration", response_model=list[OpenCompetitionOut])
async def list_open_for_registration(
    session: DBSessionDep,
) -> list[OpenCompetitionOut]:
    """Public list of ACTIVE cycles with an open registration window."""
    items = await competition_service.list_open_for_registration(session)
    return [OpenCompetitionOut(**item) for item in items]


@router.get("", response_model=list[CompetitionListItem])
async def list_competitions(session: DBSessionDep, _admin: AdminUserDep) -> list[CompetitionListItem]:
    items = await competition_service.list_competitions(session)
    return [
        CompetitionListItem(
            competitionId=c.id,
            name=c.name,
            status=c.status.value,
            period=PeriodIn(start=c.period_start, end=c.period_end),
            timeZone=c.time_zone,
            languages=list(c.languages or []),
        )
        for c in items
    ]


@router.post("", response_model=CompetitionOut, status_code=status.HTTP_201_CREATED)
async def create_competition(
    payload: CompetitionCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CompetitionOut:
    ip, ua = client_meta(request)
    cycle = await competition_service.create_competition(session, payload, actor=admin, ip=ip, user_agent=ua)
    return _cycle_out(cycle)


@router.get("/{competition_id}/public", response_model=PublicCompetitionOut)
async def get_public_competition(competition_id: uuid.UUID, session: DBSessionDep) -> PublicCompetitionOut:
    """Public competition about page — only when registration is open."""
    item = await competition_service.get_public_competition(session, competition_id)
    return PublicCompetitionOut(**item)


@router.get("/{competition_id}/public/skills/{skill_id}/criteria-document")
async def download_public_skill_criteria_document(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    session: DBSessionDep,
) -> Response:
    """Public criteria download while registration is open (no auth)."""
    data, filename, content_type = (
        await skill_service.download_public_skill_criteria_document(
            session, competition_id, skill_id
        )
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.patch("/{competition_id}/public-profile", response_model=CompetitionOut)
async def update_competition_public_profile(
    competition_id: uuid.UUID,
    payload: CompetitionPublicProfileUpdate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CompetitionOut:
    """Update public about text — allowed while ACTIVE."""
    ip, ua = client_meta(request)
    cycle = await competition_service.update_competition_public_profile(
        session,
        competition_id,
        description=payload.description,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    return _cycle_out(cycle)


@router.get("/{competition_id}", response_model=CompetitionOut)
async def get_competition(competition_id: uuid.UUID, session: DBSessionDep, _admin: AdminUserDep) -> CompetitionOut:
    cycle = await competition_service.get_competition(session, competition_id)
    return _cycle_out(cycle)


@router.post("/{competition_id}:clone", response_model=CloneOut, status_code=status.HTTP_201_CREATED)
async def clone_competition(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CloneOut:
    ip, ua = client_meta(request)
    cycle = await competition_service.clone_competition(session, competition_id, actor=admin, ip=ip, user_agent=ua)
    return CloneOut(newCompetitionId=cycle.id)


@router.post("/{competition_id}:validate", response_model=ValidateOut)
async def validate_competition(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> ValidateOut:
    ok, issues = await competition_service.validate_competition(session, competition_id)
    return ValidateOut(ok=ok, issues=issues)


@router.post("/{competition_id}:activate", response_model=ActivateOut)
async def activate_competition(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ActivateOut:
    ip, ua = client_meta(request)
    cycle = await competition_service.activate_competition(session, competition_id, actor=admin, ip=ip, user_agent=ua)
    return ActivateOut(status=cycle.status.value)


@router.post("/{competition_id}:deactivate", response_model=ActivateOut)
async def deactivate_competition(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ActivateOut:
    ip, ua = client_meta(request)
    cycle = await competition_service.deactivate_competition(
        session, competition_id, actor=admin, ip=ip, user_agent=ua
    )
    return ActivateOut(status=cycle.status.value)


@router.patch("/{competition_id}", response_model=CompetitionOut)
async def update_cycle(
    competition_id: uuid.UUID,
    payload: CompetitionUpdateStructural,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> CompetitionOut:
    cycle = await competition_service.update_competition_structural(
        session, competition_id, name=payload.name, actor=admin
    )
    return _cycle_out(cycle)
