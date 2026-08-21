"""US-SEC-03 — Public competitor self-registration."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, User, UserRole


@pytest.mark.asyncio
async def test_US_SEC_03_AC1_successful_signup(
    client: AsyncClient, session_manager: DBManager
) -> None:
    email = f"signup-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "fullName": "New Competitor",
            "phoneNumber": phone,
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["role"] == "COMPETITOR"
    assert body["user"]["email"] == email

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.role == UserRole.COMPETITOR
        assert user.is_active is True
        assert user.phone_number == phone
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "USER_SELF_REGISTERED",
                    AuditEvent.entity_id == str(user.id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_SEC_03_AC2_duplicate_email(client: AsyncClient) -> None:
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "fullName": "First",
        "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
        "password": "Competitor1!",
        "passwordConfirm": "Competitor1!",
        "captchaToken": "ok",
    }
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201, first.text
    second = await client.post(
        "/auth/register",
        json={
            **payload,
            "fullName": "Second",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
        },
    )
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "DUPLICATE"
    fields = body["error"].get("fields") or []
    assert any(f.get("name") == "email" and f.get("reason") == "DUPLICATE" for f in fields)


def test_map_user_unique_violation_email_and_phone() -> None:
    from sqlalchemy.exc import IntegrityError

    from app.core.errors import AppError
    from app.services.users import map_user_unique_violation, raise_user_unique_violation

    email_exc = IntegrityError(
        "INSERT",
        {},
        Exception(
            'duplicate key value violates unique constraint "ix_users_email"\n'
            "DETAIL:  Key (email)=(aboagyewahboateng@gmail.com) already exists."
        ),
    )
    mapped_email = map_user_unique_violation(email_exc)
    assert mapped_email is not None
    assert mapped_email.code == "DUPLICATE"
    assert mapped_email.status_code == 409
    assert mapped_email.fields[0].name == "email"

    phone_exc = IntegrityError(
        "INSERT",
        {},
        Exception(
            'duplicate key value violates unique constraint "ix_users_phone_number"\n'
            "DETAIL:  Key (phone_number)=(0551234567) already exists."
        ),
    )
    mapped_phone = map_user_unique_violation(phone_exc)
    assert mapped_phone is not None
    assert mapped_phone.fields[0].name == "phoneNumber"

    other = IntegrityError("INSERT", {}, Exception('unique constraint "other_table_key"'))
    assert map_user_unique_violation(other) is None

    with pytest.raises(AppError) as raised:
        raise_user_unique_violation(email_exc)
    assert raised.value.code == "DUPLICATE"

    with pytest.raises(IntegrityError):
        raise_user_unique_violation(other)


@pytest.mark.asyncio
async def test_register_duplicate_email_flush_race_returns_409(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-check misses, flush hits ix_users_email → still 409 DUPLICATE."""
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "fullName": "First",
        "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
        "password": "Competitor1!",
        "passwordConfirm": "Competitor1!",
        "captchaToken": "ok",
    }
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201, first.text

    from sqlalchemy.ext.asyncio import AsyncSession

    original_execute = AsyncSession.execute

    async def execute_hiding_email(self, statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        result = await original_execute(self, statement, *args, **kwargs)
        # Force the register pre-check to think email is free.
        compiled = str(statement)
        if "users" in compiled.lower() and "email" in compiled.lower():
            class _Empty:
                def scalar_one_or_none(self):
                    return None

            return _Empty()
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_hiding_email)

    second = await client.post(
        "/auth/register",
        json={
            **payload,
            "fullName": "Second",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
        },
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "DUPLICATE"
    fields = second.json()["error"].get("fields") or []
    assert any(f.get("name") == "email" and f.get("reason") == "DUPLICATE" for f in fields)


@pytest.mark.asyncio
async def test_US_SEC_03_AC3_password_mismatch_or_weak(client: AsyncClient) -> None:
    mismatch = await client.post(
        "/auth/register",
        json={
            "email": f"mm-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Weak",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "Competitor1!",
            "passwordConfirm": "Different1!",
            "captchaToken": "ok",
        },
    )
    assert mismatch.status_code == 422

    weak = await client.post(
        "/auth/register",
        json={
            "email": f"wk-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Weak",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "short",
            "passwordConfirm": "short",
            "captchaToken": "ok",
        },
    )
    assert weak.status_code == 422


@pytest.mark.asyncio
async def test_US_SEC_03_AC4_abuse_blocked(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={
            "email": f"abuse-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Abuse",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "invalid",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ABUSE_SUSPECTED"


@pytest.mark.asyncio
async def test_US_SEC_03_AC5_staff_roles_forbidden(client: AsyncClient) -> None:
    email = f"staff-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "fullName": "Would Be Admin",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
            "role": "ADMIN",
        },
    )
    assert resp.status_code == 403
    # Successful path without role still creates COMPETITOR
    ok = await client.post(
        "/auth/register",
        json={
            "email": f"ok-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Ok Comp",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
            "role": "COMPETITOR",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["user"]["role"] == "COMPETITOR"


@pytest.mark.asyncio
async def test_US_SEC_03_phone_required_and_valid(client: AsyncClient) -> None:
    missing = await client.post(
        "/auth/register",
        json={
            "email": f"nophone-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "No Phone",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
        },
    )
    assert missing.status_code == 422

    invalid = await client.post(
        "/auth/register",
        json={
            "email": f"badphone-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Bad Phone",
            "phoneNumber": "123",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_PHONE"


@pytest.mark.asyncio
async def test_US_SEC_03_duplicate_phone_rejected(client: AsyncClient) -> None:
    phone = "0559988776"
    first = await client.post(
        "/auth/register",
        json={
            "email": f"phone-a-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "First Phone",
            "phoneNumber": phone,
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
        },
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/auth/register",
        json={
            "email": f"phone-b-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Second Phone",
            "phoneNumber": "+233559988776",
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
        },
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "DUPLICATE"
    assert second.json()["error"]["fields"][0]["name"] == "phoneNumber"
