"""US-PUB-01 public portal API (unauthenticated, privacy-gated)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request

from app.dependencies.database import DBSessionDep
from app.schemas.public_portal import PublicCompetitorDirectoryOut, PublicCompetitorProfileOut
from app.services import public_portal as portal_service

router = APIRouter(tags=["public-portal"])


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"


@router.get(
    "/public/cycles/{cycle_id}/competitors",
    response_model=PublicCompetitorDirectoryOut,
)
async def list_public_competitors(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    request: Request,
    skill: uuid.UUID | None = Query(default=None),
    zone: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    format: str | None = Query(default=None, alias="format"),  # noqa: A002 — API query name
) -> PublicCompetitorDirectoryOut:
    return await portal_service.list_public_competitors(
        session,
        cycle_id,
        skill_id=skill,
        zone_id=zone,
        cursor=cursor,
        limit=limit,
        fmt=format,
        client_key=_client_key(request),
    )


@router.get(
    "/public/competitors/{competitor_key}",
    response_model=PublicCompetitorProfileOut,
)
async def get_public_competitor(
    competitor_key: str,
    session: DBSessionDep,
    request: Request,
) -> PublicCompetitorProfileOut:
    return await portal_service.get_public_competitor_profile(
        session,
        competitor_key,
        client_key=_client_key(request),
    )
