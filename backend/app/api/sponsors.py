"""Sponsor catalog HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import Sponsor
from app.schemas.sponsors import SponsorCreate, SponsorOut, SponsorPatch
from app.services import sponsors as sponsor_service

router = APIRouter(tags=["sponsors"])


def _sponsor_out(sponsor: Sponsor) -> SponsorOut:
    return SponsorOut(**sponsor_service.sponsor_out_kwargs(sponsor))


@router.get("/sponsors", response_model=list[SponsorOut])
async def list_sponsors(session: DBSessionDep, admin: AdminUserDep) -> list[SponsorOut]:
    _ = admin
    sponsors = await sponsor_service.list_sponsors(session)
    return [_sponsor_out(s) for s in sponsors]


@router.post("/sponsors", response_model=SponsorOut, status_code=status.HTTP_201_CREATED)
async def create_sponsor(
    payload: SponsorCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SponsorOut:
    ip, ua = client_meta(request)
    sponsor = await sponsor_service.create_sponsor(
        session, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _sponsor_out(sponsor)


@router.patch("/sponsors/{sponsor_id}", response_model=SponsorOut)
async def patch_sponsor(
    sponsor_id: uuid.UUID,
    payload: SponsorPatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SponsorOut:
    ip, ua = client_meta(request)
    sponsor = await sponsor_service.patch_sponsor(
        session, sponsor_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _sponsor_out(sponsor)


@router.post("/sponsors/{sponsor_id}/logo", response_model=SponsorOut)
async def upload_sponsor_logo(
    sponsor_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
    file: UploadFile = File(...),
) -> SponsorOut:
    ip, ua = client_meta(request)
    data = await file.read()
    sponsor = await sponsor_service.upload_sponsor_logo(
        session,
        sponsor_id,
        actor=admin,
        data=data,
        filename=file.filename or "logo.png",
        content_type=file.content_type,
        ip=ip,
        user_agent=ua,
    )
    return _sponsor_out(sponsor)


@router.delete("/sponsors/{sponsor_id}/logo", response_model=SponsorOut)
async def clear_sponsor_logo(
    sponsor_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SponsorOut:
    ip, ua = client_meta(request)
    sponsor = await sponsor_service.clear_sponsor_logo(
        session, sponsor_id, actor=admin, ip=ip, user_agent=ua
    )
    return _sponsor_out(sponsor)


@router.get("/sponsors/{sponsor_id}/logo")
async def download_sponsor_logo(
    sponsor_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> Response:
    _ = admin
    data, content_type, filename = await sponsor_service.download_sponsor_logo(
        session, sponsor_id
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/public/sponsors", response_model=list[SponsorOut])
async def list_public_sponsors(session: DBSessionDep) -> list[SponsorOut]:
    sponsors = await sponsor_service.list_active_sponsors(session)
    return [_sponsor_out(s) for s in sponsors]


@router.get("/public/sponsors/{sponsor_id}/logo")
async def download_public_sponsor_logo(
    sponsor_id: uuid.UUID,
    session: DBSessionDep,
) -> Response:
    data, content_type, filename = await sponsor_service.download_sponsor_logo(
        session, sponsor_id, active_only=True
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
