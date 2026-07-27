from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.users import (
    CreateUserRequest,
    CreateUserResponse,
    PatchUserRequest,
    UserOut,
)
from app.services import users as users_service

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    session: DBSessionDep,
    _admin: AdminUserDep,
    role: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    q: str | None = Query(default=None),
) -> list[dict]:
    return await users_service.list_users(session, role=role, active=active, q=q)


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> dict:
    ip, ua = client_meta(request)
    return await users_service.create_user(
        session, actor=admin, payload=body, ip=ip, user_agent=ua
    )


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserRequest,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> dict:
    ip, ua = client_meta(request)
    return await users_service.patch_user(
        session, actor=admin, user_id=user_id, payload=body, ip=ip, user_agent=ua
    )


@router.post("/users/{user_id}/resend-invite", status_code=status.HTTP_200_OK)
async def resend_invite(
    user_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> dict:
    ip, ua = client_meta(request)
    return await users_service.resend_invite(
        session, actor=admin, user_id=user_id, ip=ip, user_agent=ua
    )
