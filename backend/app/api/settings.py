"""Public and admin system settings API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.errors import AppError
from app.core.rbac import is_admin_role
from app.dependencies.auth import CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.settings import SystemSettingsOut, SystemSettingsUpdate
from app.services import settings as settings_service

router = APIRouter(tags=["settings"])


async def require_admin_user(user: CurrentUserDep) -> User:
    if not is_admin_role(user.role):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)
    return user


AdminUserDep = Annotated[User, Depends(require_admin_user)]


@router.get("/settings", response_model=SystemSettingsOut)
async def get_public_settings(session: DBSessionDep) -> SystemSettingsOut:
    return await settings_service.get_settings_out(session)


@router.get("/admin/settings", response_model=SystemSettingsOut)
async def get_admin_settings(
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> SystemSettingsOut:
    return await settings_service.get_settings_out(session)


@router.patch("/admin/settings", response_model=SystemSettingsOut)
async def patch_admin_settings(
    payload: SystemSettingsUpdate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SystemSettingsOut:
    ip, ua = client_meta(request)
    out = await settings_service.update_settings(
        session,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
    await session.commit()
    return out
