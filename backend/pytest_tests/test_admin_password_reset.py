"""Admin-assisted password reset for existing users."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash, hash_refresh_token
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, RefreshToken, User, UserRole


async def _create_staff(
    session_manager: DBManager,
    *,
    role: UserRole = UserRole.MODERATOR,
    password: str = "old-pass-1234",
    email: str | None = None,
) -> User:
    async with session_manager.session() as session:
        user = User(
            email=email or f"staff-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Staff User",
            hashed_password=get_password_hash(password),
            role=role,
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


@pytest.mark.asyncio
async def test_admin_reset_password_generates_temp_and_forces_change(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager, password="old-pass-1234")

    login_old = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "old-pass-1234"},
    )
    assert login_old.status_code == 200, login_old.text

    resp = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mustChangePassword"] is True
    assert body["temporaryPassword"]
    assert len(body["temporaryPassword"]) == 8
    assert body.get("smsSent") is False

    login_old_again = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "old-pass-1234"},
    )
    assert login_old_again.status_code == 401

    login_new = await client.post(
        "/auth/login",
        json={"email": user.email, "password": body["temporaryPassword"]},
    )
    assert login_new.status_code == 200, login_new.text
    assert login_new.json()["mustChangePassword"] is True

    async with session_manager.session() as session:
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "USER_PASSWORD_RESET",
                    AuditEvent.entity_id == str(user.id),
                )
            )
        ).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_admin_reset_password_custom_temp_and_policy(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager)

    weak = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"temporaryPassword": "short"},
    )
    assert weak.status_code == 422, weak.text
    assert weak.json()["error"]["code"] == "PASSWORD_TOO_WEAK"

    ok = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"temporaryPassword": "custom-temp-99"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["temporaryPassword"] == "custom-temp-99"

    login = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "custom-temp-99"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_admin_reset_password_revokes_refresh_tokens(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager, password="session-pass-12")
    login = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "session-pass-12"},
    )
    assert login.status_code == 200, login.text
    refresh = login.json()["refresh_token"]

    refresh_ok = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refresh_ok.status_code == 200, refresh_ok.text
    refresh = refresh_ok.json()["refresh_token"]

    reset = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={},
    )
    assert reset.status_code == 200, reset.text

    refresh_fail = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refresh_fail.status_code == 401

    async with session_manager.session() as session:
        tokens = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.user_id == user.id)
            )
        ).scalars().all()
        assert tokens
        assert all(t.revoked_at is not None for t in tokens)


@pytest.mark.asyncio
async def test_admin_reset_password_clears_invite_token(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        user = User(
            email=f"invite-reset-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Invite Pending",
            hashed_password=None,
            role=UserRole.MODERATOR,
            is_active=True,
            invite_token_hash=hash_refresh_token("pending-secret"),
            invite_expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    resp = await client.post(
        f"/users/{user_id}/reset-password",
        headers=auth_headers,
        json={"temporaryPassword": "invite-cleared-1"},
    )
    assert resp.status_code == 200, resp.text

    async with session_manager.session() as session:
        row = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        assert row.hashed_password is not None
        assert row.invite_token_hash is None
        assert row.invite_expires_at is None
        assert row.must_change_password is True


@pytest.mark.asyncio
async def test_admin_cannot_reset_admin_password(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    target = await _create_staff(
        session_manager,
        role=UserRole.ADMIN,
        password="admin-target-12",
    )
    resp = await client.post(
        f"/users/{target.id}/reset-password",
        headers=auth_headers,
        json={},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "USER_MANAGE_DENIED"


@pytest.mark.asyncio
async def test_super_admin_can_reset_admin_password(
    client: AsyncClient,
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        sa = User(
            email=f"sa-reset-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Super Reset",
            hashed_password=get_password_hash("super-pass-1234"),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        session.add(sa)
        await session.commit()
        sa_email = sa.email

    target = await _create_staff(
        session_manager,
        role=UserRole.ADMIN,
        password="admin-old-1234",
    )

    login = await client.post(
        "/auth/login",
        json={"email": sa_email, "password": "super-pass-1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        f"/users/{target.id}/reset-password",
        headers=headers,
        json={"temporaryPassword": "admin-new-1234"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["temporaryPassword"] == "admin-new-1234"


@pytest.mark.asyncio
async def test_unauthenticated_cannot_reset_password(
    client: AsyncClient,
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager)
    resp = await client.post(f"/users/{user.id}/reset-password", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_unknown_user_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        f"/users/{uuid.uuid4()}/reset-password",
        headers=auth_headers,
        json={},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_forced_change_after_reset(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager, password="before-reset-1")
    reset = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"temporaryPassword": "after-reset-12"},
    )
    assert reset.status_code == 200
    temp = reset.json()["temporaryPassword"]

    login = await client.post(
        "/auth/login",
        json={"email": user.email, "password": temp},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    blocked = await client.get("/users", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    change = await client.post(
        "/auth/change-password",
        headers=headers,
        json={
            "currentPassword": temp,
            "newPassword": "final-pass-123",
            "newPasswordConfirm": "final-pass-123",
        },
    )
    assert change.status_code == 204, change.text

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["mustChangePassword"] is False


@pytest.mark.asyncio
async def test_reset_send_via_sms_requires_phone(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    user = await _create_staff(session_manager)
    resp = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"sendViaSms": True},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "PHONE_REQUIRED"


@pytest.mark.asyncio
async def test_reset_send_via_sms_requires_sms_enabled(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    user = await _create_staff(session_manager)
    resp = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"sendViaSms": True, "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "SMS_DISABLED"


@pytest.mark.asyncio
async def test_reset_send_via_sms_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.models import SmsDelivery
    from app.services.sms.types import SmsDeliveryResult

    monkeypatch.setattr(settings, "sms_enabled", True)

    class _FakeProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def send_sms(self, msisdn: str, message: str) -> SmsDeliveryResult:
            self.calls.append((msisdn, message))
            return SmsDeliveryResult(sent=True)

    provider = _FakeProvider()
    monkeypatch.setattr(
        "app.services.sms.delivery_log.get_sms_provider",
        lambda: provider,
    )

    user = await _create_staff(session_manager)
    # Seed account phone as if collected at signup
    async with session_manager.session() as session:
        row = (
            await session.execute(select(User).where(User.id == user.id))
        ).scalar_one()
        row.phone_number = "0551234567"
        await session.commit()

    resp = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"sendViaSms": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["smsSent"] is True
    assert body.get("smsError") in (None, "")
    assert len(body["temporaryPassword"]) == 8
    assert body["phoneNumber"] == "0551234567"
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == "233551234567"
    assert body["temporaryPassword"] in provider.calls[0][1]

    async with session_manager.session() as session:
        row = (
            await session.execute(
                select(SmsDelivery).where(
                    SmsDelivery.user_id == user.id,
                    SmsDelivery.message_type == "PASSWORD_RESET",
                )
            )
        ).scalar_one()
        assert row.status == "sent"
        assert row.msisdn == "233551234567"


@pytest.mark.asyncio
async def test_reset_send_via_sms_invalid_phone(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    user = await _create_staff(session_manager)
    resp = await client.post(
        f"/users/{user.id}/reset-password",
        headers=auth_headers,
        json={"sendViaSms": True, "phoneNumber": "123"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "INVALID_PHONE"
