from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.core.security import verify_token
from app.dependencies.database import DBSessionDep
from app.models import Cycle, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    session: DBSessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AppError("UNAUTHORIZED", "Authentication required", status_code=401)

    payload = verify_token(credentials.credentials)
    if payload is None:
        raise AppError("UNAUTHORIZED", "Invalid or expired token", status_code=401)

    user_id = payload.get("sub")
    if not user_id:
        raise AppError("UNAUTHORIZED", "Invalid token claims", status_code=401)

    result = await session.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found or inactive", status_code=401)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    allowed = set(roles)
    if UserRole.ADMIN in allowed:
        allowed.add(UserRole.SUPER_ADMIN)

    async def _dep(user: CurrentUserDep) -> User:
        if user.role not in allowed:
            raise AppError("FORBIDDEN", "Insufficient role", status_code=403)
        return user

    return _dep


def require_capability(capability: Capability):
    async def _dep(user: CurrentUserDep) -> User:
        if not has_capability(user.role, capability):
            raise AppError("FORBIDDEN", f"Missing capability: {capability.value}", status_code=403)
        return user

    return _dep


AdminUserDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


async def get_cycle_scoped(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> Cycle:
    """Ensure cycle exists; non-admins still need auth (operational scoping added later)."""
    result = await session.execute(select(Cycle).where(Cycle.id == cycle_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)
    _ = user
    return cycle


def client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


def access_token_for_user(user: User) -> str:
    from app.core.security import create_access_token
    from app.config import settings

    return create_access_token(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "email": user.email,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def assert_can_configure(user: User) -> None:
    if not (is_admin_role(user.role) or has_capability(user.role, Capability.CONFIGURE_CYCLE)):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)
