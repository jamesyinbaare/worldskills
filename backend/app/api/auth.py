from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.core.errors import AppError
from app.core.security import (
    create_refresh_token,
    hash_refresh_token,
    verify_password,
    verify_refresh_token_hash,
)
from app.dependencies.auth import CurrentUserDep, access_token_for_user
from app.dependencies.database import DBSessionDep
from app.models import RefreshToken, User
from app.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DBSessionDep, request: Request) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", status_code=401)
    if not user.is_active:
        raise AppError("UNAUTHORIZED", "User is inactive", status_code=401)

    access = access_token_for_user(user)
    refresh = create_refresh_token()
    token_row = RefreshToken(
        user_id=user.id,
        token=hash_refresh_token(refresh),
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    user.last_login = datetime.utcnow()
    session.add(token_row)
    await session.commit()
    _ = request
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, session: DBSessionDep) -> TokenResponse:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )
    tokens = list(result.scalars().all())
    matched: RefreshToken | None = None
    for t in tokens:
        if verify_refresh_token_hash(payload.refresh_token, t.token):
            matched = t
            break
    if matched is None or matched.expires_at < datetime.utcnow():
        raise AppError("UNAUTHORIZED", "Invalid refresh token", status_code=401)

    user_result = await session.execute(select(User).where(User.id == matched.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found or inactive", status_code=401)

    matched.revoked_at = datetime.utcnow()
    new_refresh = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(new_refresh),
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
    )
    await session.commit()
    return TokenResponse(access_token=access_token_for_user(user), refresh_token=new_refresh)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
    )
