"""US-SEC-02 — admin-provisioned staff accounts."""

from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.errors import AppError, FieldError
from app.core.rbac import is_admin_role
from app.core.security import (
    get_password_hash,
    hash_refresh_token,
    verify_refresh_token_hash,
)
from app.models import Institution, NotificationPreference, RefreshToken, User, UserRole
from app.schemas.users import (
    CredentialMode,
    CreateUserRequest,
    PatchUserRequest,
    ResetPasswordRequest,
)
from app.services.audit import write_audit_event
from app.services.notifications import emit
from app.services.sms.delivery_log import send_and_log_sms
from app.services.sms.phone import is_valid_ghana_phone, normalize_msisdn, to_local_ghana_phone


PROVISIONABLE_ROLES = {
    UserRole.ADMIN,
    UserRole.CHIEF_EXPERT,
    UserRole.EXPERT,
    UserRole.MODERATOR,
    UserRole.APPEALS_OFFICER,
}

_EXPERT_ROLES = {UserRole.EXPERT, UserRole.CHIEF_EXPERT}
_PRIVILEGED_ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits
MESSAGE_TYPE_PASSWORD_RESET = "PASSWORD_RESET"
RECIPIENT_USER = "user"

PROVISIONABLE_ROLES = {
    UserRole.ADMIN,
    UserRole.CHIEF_EXPERT,
    UserRole.EXPERT,
    UserRole.MODERATOR,
    UserRole.APPEALS_OFFICER,
}

_EXPERT_ROLES = {UserRole.EXPERT, UserRole.CHIEF_EXPERT}
_PRIVILEGED_ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def map_user_unique_violation(exc: IntegrityError) -> AppError | None:
    """Map users-table unique violations to a client-safe AppError.

    Returns None when the integrity error is not a known users unique constraint.
    """
    text = str(getattr(exc, "orig", None) or exc).lower()
    if "ix_users_email" in text:
        return AppError(
            "DUPLICATE",
            "Email already registered",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("email", "DUPLICATE")],
        )
    if "ix_users_phone_number" in text:
        return AppError(
            "DUPLICATE",
            "Phone number already registered",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("phoneNumber", "DUPLICATE")],
        )
    return None


def raise_user_unique_violation(exc: IntegrityError) -> None:
    """Raise a mapped AppError for known user unique violations; else re-raise."""
    mapped = map_user_unique_violation(exc)
    if mapped is not None:
        raise mapped from exc
    raise exc


def assert_can_create_role(actor: User, target_role: UserRole) -> None:
    if target_role not in PROVISIONABLE_ROLES:
        raise AppError(
            "ROLE_CREATE_DENIED",
            "This role cannot be provisioned via admin API",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("role", "ROLE_CREATE_DENIED")],
        )
    if target_role == UserRole.ADMIN and actor.role != UserRole.SUPER_ADMIN:
        raise AppError(
            "ROLE_CREATE_DENIED",
            "Only a super administrator can create administrator accounts",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("role", "ROLE_CREATE_DENIED")],
        )
    if not is_admin_role(actor.role):
        raise AppError("FORBIDDEN", "Insufficient role", status_code=403)


def assert_can_manage_user(actor: User, target: User) -> None:
    """Admins may manage users; only SUPER_ADMIN may manage ADMIN/SUPER_ADMIN."""
    if not is_admin_role(actor.role):
        raise AppError("FORBIDDEN", "Insufficient role", status_code=403)
    if target.role in _PRIVILEGED_ADMIN_ROLES and actor.role != UserRole.SUPER_ADMIN:
        raise AppError(
            "USER_MANAGE_DENIED",
            "Only a super administrator can manage administrator accounts",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("userId", "USER_MANAGE_DENIED")],
        )


def validate_password_policy(password: str) -> None:
    min_len = settings.password_min_length
    if len(password) < min_len:
        raise AppError(
            "PASSWORD_TOO_WEAK",
            f"Password must be at least {min_len} characters",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("password", "PASSWORD_TOO_WEAK")],
        )


def require_ghana_phone(raw: str | None, *, field: str = "phoneNumber") -> str:
    phone = (raw or "").strip()
    if not phone:
        raise AppError(
            "PHONE_REQUIRED",
            "A phone number is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError(field, "PHONE_REQUIRED")],
        )
    if not is_valid_ghana_phone(phone):
        raise AppError(
            "INVALID_PHONE",
            "Phone number must be a valid Ghana mobile number",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError(field, "INVALID_PHONE")],
        )
    return to_local_ghana_phone(phone)


async def assert_phone_available(
    session: AsyncSession,
    phone: str,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    """Reject if another user already owns this Ghana number (any stored format)."""
    target = normalize_msisdn(phone)
    rows = (
        await session.execute(
            select(User.id, User.phone_number).where(User.phone_number.is_not(None))
        )
    ).all()
    for user_id, stored in rows:
        if exclude_user_id is not None and user_id == exclude_user_id:
            continue
        if not stored or not str(stored).strip():
            continue
        try:
            if normalize_msisdn(str(stored)) == target:
                raise AppError(
                    "DUPLICATE",
                    "Phone number already registered",
                    status_code=status.HTTP_409_CONFLICT,
                    fields=[FieldError("phoneNumber", "DUPLICATE")],
                )
        except ValueError:
            continue


def generate_temporary_password() -> str:
    length = max(1, settings.temporary_password_length)
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


def _user_out(user: User) -> dict:
    return {
        "userId": str(user.id),
        "email": user.email,
        "fullName": user.full_name,
        "role": user.role.value,
        "institutionId": str(user.institution_id) if user.institution_id else None,
        "isActive": user.is_active,
        "mustChangePassword": user.must_change_password,
        "phoneNumber": user.phone_number,
    }


async def _load_institution(session: AsyncSession, institution_id: uuid.UUID) -> Institution:
    inst = (
        await session.execute(select(Institution).where(Institution.id == institution_id))
    ).scalar_one_or_none()
    if inst is None or not inst.active:
        raise AppError(
            "INSTITUTION_NOT_FOUND",
            "Institution not found or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("institutionId", "INSTITUTION_NOT_FOUND")],
        )
    return inst


def create_invite_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Return (full_token, secret_part) and store hash of secret on user."""
    secret = secrets.token_urlsafe(32)
    token = f"{user_id}.{secret}"
    return token, secret


def verify_invite_token(user: User, token: str) -> bool:
    if not user.invite_token_hash or not user.invite_expires_at:
        return False
    if user.invite_expires_at < datetime.utcnow():
        return False
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    try:
        token_user_id = uuid.UUID(parts[0])
    except ValueError:
        return False
    if token_user_id != user.id:
        return False
    return verify_refresh_token_hash(parts[1], user.invite_token_hash)


async def create_user(
    session: AsyncSession,
    *,
    actor: User,
    payload: CreateUserRequest,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    try:
        target_role = UserRole(payload.role)
    except ValueError as exc:
        raise AppError(
            "INVALID_ROLE",
            "Unknown role",
            status_code=422,
            fields=[FieldError("role", "INVALID_ROLE")],
        ) from exc

    assert_can_create_role(actor, target_role)

    email = _normalize_email(payload.email)
    phone_number = require_ghana_phone(payload.phone_number)
    await assert_phone_available(session, phone_number)

    institution_id: uuid.UUID | None = None
    if payload.institution_id:
        institution_id = uuid.UUID(payload.institution_id)
        await _load_institution(session, institution_id)

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            "EMAIL_ALREADY_EXISTS",
            "A user with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("email", "EMAIL_ALREADY_EXISTS")],
        )

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        role=target_role,
        phone_number=phone_number,
        is_active=True,
        institution_id=institution_id,
        created_by_id=actor.id,
        must_change_password=False,
    )
    session.add(user)
    await session.flush()

    response_temp: str | None = None
    invite_sent = False

    if payload.credential_mode == CredentialMode.TEMP_PASSWORD:
        temp = payload.temporary_password or generate_temporary_password()
        validate_password_policy(temp)
        user.hashed_password = get_password_hash(temp)
        user.must_change_password = True
        response_temp = temp
    else:
        user.hashed_password = None
        token, secret = create_invite_token(user.id)
        user.invite_token_hash = hash_refresh_token(secret)
        user.invite_expires_at = datetime.utcnow() + timedelta(hours=settings.invite_token_expire_hours)
        session.add(
            NotificationPreference(
                user_id=user.id,
                preferred_channel="EMAIL",
                fallback_channel=None,
                language="en",
                email=email,
                phone=phone_number,
                whatsapp=None,
                opt_out_non_essential=False,
                updated_at=datetime.utcnow(),
            )
        )
        await session.flush()
        invite_url = f"{settings.frontend_base_url.rstrip('/')}/accept-invite?token={token}"
        expires_at = user.invite_expires_at.isoformat() + "Z"
        result = await emit(
            session,
            event="USER_ACCOUNT_INVITE",
            recipient_id=user.id,
            context={
                "fullName": user.full_name,
                "inviteUrl": invite_url,
                "expiresAt": expires_at,
            },
            recipient_role=target_role.value,
            actor=actor,
            ip=ip,
            user_agent=user_agent,
        )
        if result.status not in {"SENT", "FALLBACK_SENT"}:
            raise AppError(
                "INVITE_DELIVERY_FAILED",
                "Could not send invitation email",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        invite_sent = True

    await write_audit_event(
        session,
        action="USER_CREATED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        after={"email": email, "role": target_role.value, "credentialMode": payload.credential_mode.value},
        ip=ip,
        user_agent=user_agent,
    )
    if invite_sent:
        await write_audit_event(
            session,
            action="USER_INVITE_SENT",
            entity_type="User",
            entity_id=str(user.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            after={"email": email},
            ip=ip,
            user_agent=user_agent,
        )

    await session.commit()
    await session.refresh(user)
    out = _user_out(user)
    out["temporaryPassword"] = response_temp
    out["inviteSent"] = invite_sent
    return out


async def list_users(
    session: AsyncSession,
    *,
    role: str | None,
    active: bool | None,
    q: str | None,
) -> list[dict]:
    stmt = select(User).order_by(User.created_at.desc())
    if role:
        roles = [r.strip() for r in role.split(",") if r.strip()]
        parsed: list[UserRole] = []
        for r in roles:
            try:
                parsed.append(UserRole(r))
            except ValueError:
                raise AppError(
                    "INVALID_ROLE",
                    "Unknown role filter",
                    status_code=422,
                    fields=[FieldError("role", "INVALID_ROLE")],
                ) from None
        stmt = stmt.where(User.role.in_(parsed))
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    if q:
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(term),
                User.full_name.ilike(term),
            )
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [_user_out(u) for u in rows]


async def patch_user(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    payload: PatchUserRequest,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=404)

    before = _user_out(user)

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.institution_id is not None:
        if user.role in _EXPERT_ROLES:
            if payload.institution_id == "":
                user.institution_id = None
            else:
                inst_id = uuid.UUID(payload.institution_id)
                await _load_institution(session, inst_id)
                user.institution_id = inst_id
        elif payload.institution_id:
            raise AppError(
                "INSTITUTION_NOT_APPLICABLE",
                "Institution applies only to expert roles",
                status_code=422,
                fields=[FieldError("institutionId", "INSTITUTION_NOT_APPLICABLE")],
            )
    if payload.is_active is not None:
        if not payload.is_active and user.id == actor.id:
            raise AppError(
                "CANNOT_DEACTIVATE_SELF",
                "You cannot deactivate your own account",
                status_code=422,
            )
        user.is_active = payload.is_active

    await session.flush()
    after = _user_out(user)
    action = "USER_DEACTIVATED" if payload.is_active is False else "USER_UPDATED"
    await write_audit_event(
        session,
        action=action,
        entity_type="User",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


async def resend_invite(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=404)
    if user.hashed_password:
        raise AppError(
            "INVITE_NOT_APPLICABLE",
            "User already has a password",
            status_code=422,
            fields=[FieldError("userId", "INVITE_NOT_APPLICABLE")],
        )

    token, secret = create_invite_token(user.id)
    user.invite_token_hash = hash_refresh_token(secret)
    user.invite_expires_at = datetime.utcnow() + timedelta(hours=settings.invite_token_expire_hours)

    prefs = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user.id)
        )
    ).scalar_one_or_none()
    if prefs is None:
        session.add(
            NotificationPreference(
                user_id=user.id,
                preferred_channel="EMAIL",
                language="en",
                email=user.email,
                opt_out_non_essential=False,
                updated_at=datetime.utcnow(),
            )
        )
        await session.flush()

    invite_url = f"{settings.frontend_base_url.rstrip('/')}/accept-invite?token={token}"
    expires_at = user.invite_expires_at.isoformat() + "Z"
    result = await emit(
        session,
        event="USER_ACCOUNT_INVITE",
        recipient_id=user.id,
        context={"fullName": user.full_name, "inviteUrl": invite_url, "expiresAt": expires_at},
        recipient_role=user.role.value,
        actor=actor,
        ip=ip,
        user_agent=user_agent,
    )
    if result.status not in {"SENT", "FALLBACK_SENT"}:
        raise AppError("INVITE_DELIVERY_FAILED", "Could not send invitation email", status_code=502)

    await write_audit_event(
        session,
        action="USER_INVITE_SENT",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        after={"email": user.email, "resent": True},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return {"userId": str(user.id), "inviteSent": True}


async def accept_invite(
    session: AsyncSession,
    *,
    token: str,
    password: str,
    password_confirm: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    if password != password_confirm:
        raise AppError(
            "PASSWORD_MISMATCH",
            "Passwords do not match",
            status_code=422,
            fields=[FieldError("passwordConfirm", "PASSWORD_MISMATCH")],
        )
    validate_password_policy(password)

    parts = token.split(".", 1)
    if len(parts) != 2:
        raise AppError("INVALID_INVITE", "Invalid or expired invitation", status_code=400)
    try:
        user_id = uuid.UUID(parts[0])
    except ValueError as exc:
        raise AppError("INVALID_INVITE", "Invalid or expired invitation", status_code=400) from exc

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not verify_invite_token(user, token):
        raise AppError("INVALID_INVITE", "Invalid or expired invitation", status_code=400)

    user.hashed_password = get_password_hash(password)
    user.must_change_password = False
    user.invite_token_hash = None
    user.invite_expires_at = None

    await write_audit_event(
        session,
        action="USER_INVITE_ACCEPTED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_role=user.role.value,
        after={"email": user.email},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()


async def _revoke_refresh_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    rows = (
        await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    now = datetime.utcnow()
    for row in rows:
        row.revoked_at = now


async def reset_password(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=404)

    assert_can_manage_user(actor, user)

    phone_for_sms: str | None = None
    if payload.send_via_sms:
        if not settings.sms_enabled:
            raise AppError(
                "SMS_DISABLED",
                "SMS delivery is not enabled",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("sendViaSms", "SMS_DISABLED")],
            )
        raw_phone = (payload.phone_number or user.phone_number or "").strip() or None
        if not raw_phone:
            raise AppError(
                "PHONE_REQUIRED",
                "A phone number is required to send the temporary password by SMS",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("phoneNumber", "PHONE_REQUIRED")],
            )
        phone_for_sms = require_ghana_phone(raw_phone)
        await assert_phone_available(session, phone_for_sms, exclude_user_id=user.id)

    temp = payload.temporary_password or generate_temporary_password()
    validate_password_policy(temp)

    user.hashed_password = get_password_hash(temp)
    user.must_change_password = True
    user.invite_token_hash = None
    user.invite_expires_at = None
    if phone_for_sms:
        user.phone_number = phone_for_sms

    await _revoke_refresh_tokens(session, user.id)

    sms_sent = False
    sms_error: str | None = None
    if payload.send_via_sms and phone_for_sms:
        message = (
            f"Your WorldSkills account temporary password is: {temp}. "
            "You must change it after signing in."
        )
        result, _ = await send_and_log_sms(
            session,
            phone=phone_for_sms,
            message=message,
            message_type=MESSAGE_TYPE_PASSWORD_RESET,
            trigger="admin_password_reset",
            recipient_role=RECIPIENT_USER,
            user_id=user.id,
            triggered_by_user_id=actor.id,
        )
        sms_sent = bool(result.sent)
        if not sms_sent:
            if result.error:
                logging.getLogger("app").warning(
                    "SMS delivery failed during password reset",
                    extra={"user_id": str(user.id), "detail": result.error},
                )
            sms_error = "Could not send the message. Please try again."

    await write_audit_event(
        session,
        action="USER_PASSWORD_RESET",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        after={
            "email": user.email,
            "mustChangePassword": True,
            "sendViaSms": payload.send_via_sms,
            "smsSent": sms_sent,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(user)
    out = _user_out(user)
    out["temporaryPassword"] = temp
    out["smsSent"] = sms_sent
    out["smsError"] = sms_error
    return out


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
    new_password_confirm: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    from app.core.security import verify_password

    if new_password != new_password_confirm:
        raise AppError(
            "PASSWORD_MISMATCH",
            "Passwords do not match",
            status_code=422,
            fields=[FieldError("newPasswordConfirm", "PASSWORD_MISMATCH")],
        )
    validate_password_policy(new_password)
    if not user.hashed_password or not verify_password(current_password, user.hashed_password):
        raise AppError(
            "INVALID_CREDENTIALS",
            "Current password is incorrect",
            status_code=401,
        )

    user.hashed_password = get_password_hash(new_password)
    user.must_change_password = False
    user.pending_password_hash = None
    user.pending_password_expires_at = None
    await write_audit_event(
        session,
        action="USER_PASSWORD_CHANGED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_role=user.role.value,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()


_FORGOT_PASSWORD_OK_MESSAGE = "A temporary password was sent by SMS."


def clear_pending_password(user: User) -> None:
    user.pending_password_hash = None
    user.pending_password_expires_at = None


async def authenticate_user_password(
    session: AsyncSession,
    user: User,
    plain_password: str,
) -> bool:
    """Verify current or pending reset password. Mutates user on success.

    - Current password: clears any pending reset.
    - Pending temp (unexpired): promotes to hashed_password, forces change,
      revokes refresh tokens.
    """
    from app.core.security import verify_password

    if user.hashed_password and verify_password(plain_password, user.hashed_password):
        if user.pending_password_hash is not None:
            clear_pending_password(user)
        return True

    pending = user.pending_password_hash
    expires = user.pending_password_expires_at
    if (
        pending
        and expires is not None
        and expires > datetime.utcnow()
        and verify_password(plain_password, pending)
    ):
        user.hashed_password = pending
        clear_pending_password(user)
        user.must_change_password = True
        await _revoke_refresh_tokens(session, user.id)
        return True

    return False


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str | None,
    phone_number: str | None,
    ip: str | None,
    user_agent: str | None,
) -> dict:
    """Self-service reset: look up by email or phone, SMS a temporary password.

    Always returns the same success payload (anti-enumeration). Stores a pending
    temporary password (current password stays valid) when SMS can be sent.
    """
    email_raw = (email or "").strip().lower() or None
    phone_raw = (phone_number or "").strip() or None
    if bool(email_raw) == bool(phone_raw):
        raise AppError(
            "VALIDATION_ERROR",
            "Provide either an email address or a phone number",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("email", "REQUIRED"), FieldError("phoneNumber", "REQUIRED")],
        )

    user: User | None = None
    if email_raw:
        user = (
            await session.execute(select(User).where(User.email == email_raw))
        ).scalar_one_or_none()
    else:
        assert phone_raw is not None
        if not is_valid_ghana_phone(phone_raw):
            # Invalid format — do not leak; same generic response
            return {"ok": True, "message": _FORGOT_PASSWORD_OK_MESSAGE}
        local = to_local_ghana_phone(phone_raw)
        target_msisdn = normalize_msisdn(local)
        candidates = (
            await session.execute(
                select(User).where(User.phone_number.is_not(None))
            )
        ).scalars().all()
        for candidate in candidates:
            stored = (candidate.phone_number or "").strip()
            if not stored:
                continue
            try:
                if normalize_msisdn(stored) == target_msisdn:
                    user = candidate
                    break
            except ValueError:
                continue

    if (
        user is None
        or not user.is_active
        or not settings.sms_enabled
        or not (user.phone_number or "").strip()
    ):
        return {"ok": True, "message": _FORGOT_PASSWORD_OK_MESSAGE}

    phone_for_sms = require_ghana_phone(user.phone_number)
    temp = generate_temporary_password()
    validate_password_policy(temp)

    ttl = max(1, settings.password_reset_pending_ttl_minutes)
    user.pending_password_hash = get_password_hash(temp)
    user.pending_password_expires_at = datetime.utcnow() + timedelta(minutes=ttl)
    user.phone_number = phone_for_sms

    message = (
        f"Your WorldSkills temporary password is: {temp}. "
        "Sign in with it to replace your current password, then change it when prompted."
    )
    result, _ = await send_and_log_sms(
        session,
        phone=phone_for_sms,
        message=message,
        message_type=MESSAGE_TYPE_PASSWORD_RESET,
        trigger="self_service_forgot_password",
        recipient_role=RECIPIENT_USER,
        user_id=user.id,
        triggered_by_user_id=None,
    )

    if not result.sent:
        # Do not leave an undelivered pending temporary password.
        await session.rollback()
        return {"ok": True, "message": _FORGOT_PASSWORD_OK_MESSAGE}

    await write_audit_event(
        session,
        action="USER_PASSWORD_RESET_REQUESTED",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_role=user.role.value,
        after={"channel": "SMS", "lookup": "email" if email_raw else "phone"},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return {"ok": True, "message": _FORGOT_PASSWORD_OK_MESSAGE}


async def list_institutions(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(Institution).where(Institution.active.is_(True)).order_by(Institution.name)
        )
    ).scalars().all()
    return [
        {"institutionId": str(i.id), "name": i.name, "active": i.active}
        for i in rows
    ]
