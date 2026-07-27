"""US-INS-02 Institution catalog + Excel import."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.institutions import (
    InstitutionCreate,
    InstitutionImportResult,
    InstitutionLookupOut,
    InstitutionOut,
    InstitutionPatch,
)
from app.services import institutions as institutions_service

router = APIRouter(tags=["institutions"])


@router.get("/institutions/lookup", response_model=InstitutionLookupOut)
async def lookup_institution(
    session: DBSessionDep,
    code: str = Query(min_length=1),
) -> dict:
    """Public active-school lookup by code (US-SEC-04)."""
    return await institutions_service.lookup_by_code(session, code)


@router.get("/institutions:search", response_model=list[InstitutionLookupOut])
async def search_institutions(
    session: DBSessionDep,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=25, ge=1, le=50),
) -> list[dict]:
    """Public active-school search by name or code (registration school picker)."""
    return await institutions_service.search_active(session, q=q, limit=limit)


@router.get("/institutions", response_model=list[InstitutionOut])
async def list_institutions(
    session: DBSessionDep,
    _admin: AdminUserDep,
    q: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    region_id: uuid.UUID | None = Query(default=None, alias="regionId"),
) -> list[dict]:
    active_filter = active if active is not None else True
    return await institutions_service.list_institutions(
        session, q=q, active=active_filter, region_id=region_id
    )


@router.get("/institutions/import-template")
async def import_template(_admin: AdminUserDep) -> Response:
    data = institutions_service.build_import_template()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="institutions-import-template.xlsx"'},
    )


@router.post("/institutions", response_model=InstitutionOut, status_code=status.HTTP_201_CREATED)
async def create_institution(
    body: InstitutionCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> dict:
    ip, ua = client_meta(request)
    return await institutions_service.create_institution(
        session,
        actor=admin,
        code=body.code,
        name=body.name,
        region_id=uuid.UUID(body.region_id),
        active=body.active,
        ip=ip,
        user_agent=ua,
    )


@router.post("/institutions:import", response_model=InstitutionImportResult)
async def import_institutions(
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    ip, ua = client_meta(request)
    data = await file.read()
    return await institutions_service.import_institutions(
        session,
        actor=admin,
        data=data,
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        ip=ip,
        user_agent=ua,
    )


@router.patch("/institutions/{institution_id}", response_model=InstitutionOut)
async def patch_institution(
    institution_id: uuid.UUID,
    body: InstitutionPatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> dict:
    ip, ua = client_meta(request)
    return await institutions_service.patch_institution(
        session,
        actor=admin,
        institution_id=institution_id,
        code=body.code,
        name=body.name,
        region_id=uuid.UUID(body.region_id) if body.region_id else None,
        active=body.active,
        ip=ip,
        user_agent=ua,
    )
