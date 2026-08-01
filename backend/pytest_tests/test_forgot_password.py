"""Self-service forgot-password via email or phone (SMS delivery)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash, verify_password
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import User, UserRole
from app.services.sms.types import SmsDeliveryResult


async def _seed_user(
    session_manager: DBManager,
    *,
    email: str,
    phone: str,
    password: str = "old-pass-1234",
) -> User:
    async with session_manager.session() as session:
        user = User(
            email=email,
            full_name="Reset Me",
            phone_number=phone,
            hashed_password=get_password_hash(password),
            role=UserRole.COMPETITOR,
            is_active=True,
            must_change_password=False,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    async with session_manager.session() as session:
        return (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()


def _fake_sms(provider_calls: list[tuple[str, str]] | None = None):
    class _Fake:
        async def send_sms(self, msisdn: str, message: str) -> SmsDeliveryResult:
            if provider_calls is not None:
                provider_calls.append((msisdn, message))
            return SmsDeliveryResult(sent=True)

    return _Fake()


def _temp_from_sms(message: str) -> str:
    match = re.search(r"password is:\s*(\S+?)\.", message)
    assert match, message
    return match.group(1)


@pytest.mark.asyncio
async def test_forgot_password_by_email_keeps_old_until_temp_used(
    client: AsyncClient,
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    provider_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.sms.delivery_log.get_sms_provider",
        lambda: _fake_sms(provider_calls),
    )

    email = f"forgot-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    await _seed_user(session_manager, email=email, phone=phone)

    resp = await client.post(
        "/auth/forgot-password",
        json={"email": email, "captchaToken": "ok"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert len(provider_calls) == 1
    assert provider_calls[0][0] == f"233{phone[1:]}"
    temp = _temp_from_sms(provider_calls[0][1])

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.must_change_password is False
        assert verify_password("old-pass-1234", user.hashed_password)
        assert user.pending_password_hash is not None
        assert user.pending_password_expires_at is not None
        assert verify_password(temp, user.pending_password_hash)

    login_new = await client.post(
        "/auth/login",
        json={"email": email, "password": temp},
    )
    assert login_new.status_code == 200, login_new.text
    assert login_new.json()["mustChangePassword"] is True

    login_old_after = await client.post(
        "/auth/login",
        json={"email": email, "password": "old-pass-1234"},
    )
    assert login_old_after.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_old_login_cancels_pending(
    client: AsyncClient,
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    provider_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.sms.delivery_log.get_sms_provider",
        lambda: _fake_sms(provider_calls),
    )

    email = f"cancel-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    await _seed_user(session_manager, email=email, phone=phone)

    await client.post(
        "/auth/forgot-password",
        json={"email": email, "captchaToken": "ok"},
    )
    temp = _temp_from_sms(provider_calls[0][1])

    login_old = await client.post(
        "/auth/login",
        json={"email": email, "password": "old-pass-1234"},
    )
    assert login_old.status_code == 200

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.pending_password_hash is None
        assert user.pending_password_expires_at is None

    login_temp = await client.post(
        "/auth/login",
        json={"email": email, "password": temp},
    )
    assert login_temp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_expired_pending_rejected(
    client: AsyncClient,
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    provider_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.services.sms.delivery_log.get_sms_provider",
        lambda: _fake_sms(provider_calls),
    )

    email = f"expired-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    await _seed_user(session_manager, email=email, phone=phone)

    await client.post(
        "/auth/forgot-password",
        json={"email": email, "captchaToken": "ok"},
    )
    temp = _temp_from_sms(provider_calls[0][1])

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.pending_password_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()

    login_temp = await client.post(
        "/auth/login",
        json={"email": email, "password": temp},
    )
    assert login_temp.status_code == 401

    login_old = await client.post(
        "/auth/login",
        json={"email": email, "password": "old-pass-1234"},
    )
    assert login_old.status_code == 200
    assert login_old.json()["mustChangePassword"] is False


@pytest.mark.asyncio
async def test_forgot_password_by_phone(
    client: AsyncClient,
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(
        "app.services.sms.delivery_log.get_sms_provider",
        lambda: _fake_sms(),
    )

    email = f"forgot-phone-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    await _seed_user(session_manager, email=email, phone=phone)

    resp = await client.post(
        "/auth/forgot-password",
        json={"phoneNumber": f"+233{phone[1:]}", "captchaToken": "ok"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.must_change_password is False
        assert verify_password("old-pass-1234", user.hashed_password)
        assert user.pending_password_hash is not None


@pytest.mark.asyncio
async def test_forgot_password_unknown_still_ok(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    resp = await client.post(
        "/auth/forgot-password",
        json={"email": f"missing-{uuid.uuid4().hex[:8]}@example.com", "captchaToken": "ok"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_forgot_password_requires_one_identifier(client: AsyncClient) -> None:
    both = await client.post(
        "/auth/forgot-password",
        json={
            "email": "a@example.com",
            "phoneNumber": "0551234567",
            "captchaToken": "ok",
        },
    )
    assert both.status_code == 422

    neither = await client.post(
        "/auth/forgot-password",
        json={"captchaToken": "ok"},
    )
    assert neither.status_code == 422


@pytest.mark.asyncio
async def test_forgot_password_sms_disabled_does_not_change_password(
    client: AsyncClient,
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", False)
    email = f"nosms-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    await _seed_user(session_manager, email=email, phone=phone)

    resp = await client.post(
        "/auth/forgot-password",
        json={"email": email, "captchaToken": "ok"},
    )
    assert resp.status_code == 200

    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "old-pass-1234"},
    )
    assert login.status_code == 200
    assert login.json()["mustChangePassword"] is False

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.pending_password_hash is None
