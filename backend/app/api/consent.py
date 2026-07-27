from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from app.core.rbac import Capability
from app.dependencies.auth import CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.consent import (
    ConsentFormUploadOut,
    ConsentGrantIn,
    ConsentGrantOut,
    ConsentRequestIn,
    ConsentRequestOut,
    ConsentVerifyIn,
    ConsentVerifyOut,
    ConsentWithdrawOut,
)
from app.services import consent as consent_service

router = APIRouter(tags=["consent"])

ConsentAdminDep = Annotated[User, Depends(require_capability(Capability.CONFIGURE_CYCLE))]


@router.post("/competitors/{competitor_id}/consent-request", response_model=ConsentRequestOut)
async def create_consent_request(
    competitor_id: uuid.UUID,
    payload: ConsentRequestIn,
    session: DBSessionDep,
    request: Request,
) -> ConsentRequestOut:
    ip, ua = client_meta(request)
    return await consent_service.create_consent_request(
        session, competitor_id, payload, ip=ip, user_agent=ua
    )


@router.post("/consent/{token}:grant", response_model=ConsentGrantOut)
async def grant_consent(
    token: str,
    payload: ConsentGrantIn,
    session: DBSessionDep,
    request: Request,
) -> ConsentGrantOut:
    ip, ua = client_meta(request)
    return await consent_service.grant_consent(session, token, payload, ip=ip, user_agent=ua)


@router.post("/competitors/{competitor_id}/consent:withdraw", response_model=ConsentWithdrawOut)
async def withdraw_consent(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    request: Request,
) -> ConsentWithdrawOut:
    ip, ua = client_meta(request)
    return await consent_service.withdraw_consent(
        session, competitor_id, actor_role="GUARDIAN", ip=ip, user_agent=ua
    )


@router.get("/competitors/{competitor_id}/consent-form.pdf")
async def download_consent_form_pdf(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> Response:
    data, filename = await consent_service.download_consent_form_pdf(
        session, competitor_id, actor=user
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/competitors/{competitor_id}/consent-form/signed.pdf")
async def download_uploaded_consent_form(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
    download: bool = False,
) -> Response:
    data, filename = await consent_service.download_uploaded_consent_form(
        session, competitor_id, actor=user
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.post(
    "/competitors/{competitor_id}/consent-form",
    response_model=ConsentFormUploadOut,
)
async def upload_consent_form(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
    request: Request,
    file: UploadFile = File(...),
    scopes: list[str] = Form(default_factory=list),
    grantedBy: str | None = Form(default=None),
) -> ConsentFormUploadOut:
    ip, ua = client_meta(request)
    data = await file.read()
    return await consent_service.upload_signed_consent_form(
        session,
        competitor_id,
        actor=user,
        data=data,
        filename=file.filename,
        content_type=file.content_type,
        scopes=scopes,
        granted_by=grantedBy,
        ip=ip,
        user_agent=ua,
    )


@router.get("/admin/competitors/{competitor_id}/consent-form/signed.pdf")
async def admin_download_uploaded_consent_form(
    competitor_id: uuid.UUID,
    session: DBSessionDep,
    admin: ConsentAdminDep,
    download: bool = False,
) -> Response:
    data, filename = await consent_service.admin_download_uploaded_consent_form(
        session, competitor_id, actor=admin
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.post(
    "/admin/competitors/{competitor_id}/consent:verify",
    response_model=ConsentVerifyOut,
)
async def admin_verify_consent_form(
    competitor_id: uuid.UUID,
    payload: ConsentVerifyIn,
    session: DBSessionDep,
    admin: ConsentAdminDep,
    request: Request,
) -> ConsentVerifyOut:
    ip, ua = client_meta(request)
    return await consent_service.verify_consent_form(
        session,
        competitor_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
