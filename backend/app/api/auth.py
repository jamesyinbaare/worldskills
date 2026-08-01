from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.core.errors import AppError, FieldError
from app.core.security import (
    create_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_refresh_token_hash,
)
from app.dependencies.auth import CurrentUserDep, access_token_for_user, client_meta
from app.dependencies.database import DBSessionDep
from app.models import RefreshToken, User, UserRole
from app.schemas.auth import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterInstitutionRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.services import institutions as institutions_service
from app.services import users as users_service
from app.services.audit import write_audit_event
from app.services.registrations import _check_abuse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DBSessionDep, request: Request) -> TokenResponse:
    email = payload.email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not await users_service.authenticate_user_password(
        session, user, payload.password
    ):
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
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        must_change_password=user.must_change_password,
    )


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
    return TokenResponse(
        access_token=access_token_for_user(user),
        refresh_token=new_refresh,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        must_change_password=user.must_change_password,
        institution_id=str(user.institution_id) if user.institution_id else None,
    )


@router.post("/accept-invite", status_code=status.HTTP_204_NO_CONTENT)
async def accept_invite(
    body: AcceptInviteRequest,
    session: DBSessionDep,
    request: Request,
) -> None:
    ip, ua = client_meta(request)
    await users_service.accept_invite(
        session,
        token=body.token,
        password=body.password,
        password_confirm=body.password_confirm,
        ip=ip,
        user_agent=ua,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    session: DBSessionDep,
    user: CurrentUserDep,
    request: Request,
) -> None:
    ip, ua = client_meta(request)
    await users_service.change_password(
        session,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        new_password_confirm=body.new_password_confirm,
        ip=ip,
        user_agent=ua,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    session: DBSessionDep,
    request: Request,
) -> dict:
    """Self-service password reset via SMS (lookup by email or phone)."""
    ip, ua = client_meta(request)
    _check_abuse(body.captcha_token)
    return await users_service.request_password_reset(
        session,
        email=body.email,
        phone_number=body.phone_number,
        ip=ip,
        user_agent=ua,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: DBSessionDep,
    request: Request,
) -> RegisterResponse:
    """US-SEC-03 — Public competitor self-registration."""
    ip, ua = client_meta(request)
    _check_abuse(payload.captcha_token)

    if payload.role is not None and payload.role.upper() != UserRole.COMPETITOR.value:
        raise AppError(
            "FORBIDDEN",
            "Only COMPETITOR accounts may be created via public signup",
            status_code=403,
            fields=[FieldError("role", "FORBIDDEN")],
        )

    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid email",
            status_code=422,
            fields=[FieldError("email", "EMAIL_INVALID")],
        )

    full_name = payload.full_name.strip()
    if not full_name:
        raise AppError(
            "VALIDATION_ERROR",
            "Full name is required",
            status_code=422,
            fields=[FieldError("fullName", "REQUIRED")],
        )

    if payload.password != payload.password_confirm:
        raise AppError(
            "VALIDATION_ERROR",
            "Passwords do not match",
            status_code=422,
            fields=[FieldError("passwordConfirm", "INVALID")],
        )

    users_service.validate_password_policy(payload.password)
    phone_number = users_service.require_ghana_phone(payload.phone_number)
    await users_service.assert_phone_available(session, phone_number)

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            "DUPLICATE",
            "Email already registered",
            status_code=409,
            fields=[FieldError("email", "DUPLICATE")],
        )

    user = User(
        email=email,
        full_name=full_name,
        phone_number=phone_number,
        role=UserRole.COMPETITOR,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        must_change_password=False,
        last_login=datetime.utcnow(),
    )
    session.add(user)
    await session.flush()

    await write_audit_event(
        session,
        action="USER_SELF_REGISTERED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_role=UserRole.COMPETITOR.value,
        after={"email": email, "role": UserRole.COMPETITOR.value},
        ip=ip,
        user_agent=ua,
    )

    access = access_token_for_user(user)
    refresh = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(refresh),
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
    )
    await session.commit()

    return RegisterResponse(
        access_token=access,
        refresh_token=refresh,
        must_change_password=False,
        user={
            "id": str(user.id),
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role.value,
        },
    )


@router.post(
    "/register-institution",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_institution(
    payload: RegisterInstitutionRequest,
    session: DBSessionDep,
    request: Request,
) -> RegisterResponse:
    """US-SEC-04 — Claim an existing school as the primary INSTITUTION contact."""
    from app.services import settings as settings_service

    ip, ua = client_meta(request)
    if not await settings_service.institution_registration_enabled(session):
        raise AppError(
            "INSTITUTION_REGISTRATION_DISABLED",
            "Institution registration is currently disabled",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    _check_abuse(payload.captcha_token)

    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid email",
            status_code=422,
            fields=[FieldError("email", "EMAIL_INVALID")],
        )

    full_name = payload.full_name.strip()
    if not full_name:
        raise AppError(
            "VALIDATION_ERROR",
            "Full name is required",
            status_code=422,
            fields=[FieldError("fullName", "REQUIRED")],
        )

    if payload.password != payload.password_confirm:
        raise AppError(
            "VALIDATION_ERROR",
            "Passwords do not match",
            status_code=422,
            fields=[FieldError("passwordConfirm", "INVALID")],
        )

    users_service.validate_password_policy(payload.password)
    phone_number = users_service.require_ghana_phone(payload.phone_number)
    await users_service.assert_phone_available(session, phone_number)

    institution = await institutions_service.get_active_by_code(
        session, payload.school_code
    )

    claimed = (
        await session.execute(
            select(User).where(
                User.role == UserRole.INSTITUTION,
                User.institution_id == institution.id,
            )
        )
    ).scalar_one_or_none()
    if claimed is not None:
        raise AppError(
            "SCHOOL_ALREADY_CLAIMED",
            "This school already has a primary contact account",
            status_code=409,
            fields=[FieldError("schoolCode", "SCHOOL_ALREADY_CLAIMED")],
        )

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            "DUPLICATE",
            "Email already registered",
            status_code=409,
            fields=[FieldError("email", "DUPLICATE")],
        )

    user = User(
        email=email,
        full_name=full_name,
        phone_number=phone_number,
        role=UserRole.INSTITUTION,
        institution_id=institution.id,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        must_change_password=False,
        last_login=datetime.utcnow(),
    )
    session.add(user)
    await session.flush()

    await write_audit_event(
        session,
        action="INSTITUTION_CLAIMED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_role=UserRole.INSTITUTION.value,
        after={
            "email": email,
            "role": UserRole.INSTITUTION.value,
            "institutionId": str(institution.id),
            "schoolCode": institution.code,
        },
        ip=ip,
        user_agent=ua,
    )

    access = access_token_for_user(user)
    refresh = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token=hash_refresh_token(refresh),
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
    )
    await session.commit()

    return RegisterResponse(
        access_token=access,
        refresh_token=refresh,
        must_change_password=False,
        user={
            "id": str(user.id),
            "email": user.email,
            "fullName": user.full_name,
            "role": user.role.value,
            "institutionId": str(institution.id),
        },
    )
