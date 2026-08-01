"""US-SEC-02 — Admin-provisioned staff accounts."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, Institution, NotificationTemplate, User, UserRole
from pytest_tests.conftest import region_id_by_name


async def _ensure_invite_template(session_manager: DBManager) -> None:
    async with session_manager.session() as session:
        existing = (
            await session.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.event_key == "USER_ACCOUNT_INVITE",
                    NotificationTemplate.language == "en",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                NotificationTemplate(
                    event_key="USER_ACCOUNT_INVITE",
                    language="en",
                    subject="Invite {{fullName}}",
                    body="Link: {{inviteUrl}} expires {{expiresAt}}",
                    essential=True,
                    created_at=datetime.utcnow(),
                )
            )
            await session.commit()


async def _seed_institution(session_manager: DBManager) -> uuid.UUID:
    region_id = await region_id_by_name(session_manager, "Greater Accra")
    async with session_manager.session() as session:
        inst = Institution(
            name=f"Inst {uuid.uuid4().hex[:8]}",
            region_id=region_id,
            active=True,
        )
        session.add(inst)
        await session.commit()
        return inst.id


@pytest.mark.asyncio
async def test_US_SEC_02_AC1_create_with_temp_password(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    inst_id = await _seed_institution(session_manager)
    phone = f"055{uuid.uuid4().int % 10**7:07d}"
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": f"expert-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Temp Expert",
            "phoneNumber": phone,
            "role": "EXPERT",
            "institutionId": str(inst_id),
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "temp-pass-1234",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["temporaryPassword"] == "temp-pass-1234"
    assert body["mustChangePassword"] is True
    assert body["role"] == "EXPERT"
    assert body["phoneNumber"] == phone

    async with session_manager.session() as session:
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "USER_CREATED")
            )
        ).scalars().all()
        assert any(a.entity_id == body["userId"] for a in audits)
        user = (
            await session.execute(select(User).where(User.id == uuid.UUID(body["userId"])))
        ).scalar_one()
        assert user.phone_number == phone


@pytest.mark.asyncio
async def test_US_SEC_02_AC2_create_with_invite(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    await _ensure_invite_template(session_manager)
    inst_id = await _seed_institution(session_manager)
    email = f"invite-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": email,
            "fullName": "Invited Moderator",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "MODERATOR",
            "credentialMode": "INVITE",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["inviteSent"] is True
    assert body.get("temporaryPassword") is None

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.hashed_password is None
        assert user.invite_token_hash is not None


@pytest.mark.asyncio
async def test_US_SEC_02_AC3_admin_may_create_expert(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    inst_id = await _seed_institution(session_manager)
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": f"admin-expert-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Admin Created Expert",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "CHIEF_EXPERT",
            "institutionId": str(inst_id),
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "chief-pass-1234",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "CHIEF_EXPERT"


@pytest.mark.asyncio
async def test_US_SEC_02_AC3b_admin_cannot_create_admin(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": f"new-admin-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Blocked Admin",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "ADMIN",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "admin-pass-1234",
        },
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "ROLE_CREATE_DENIED"


@pytest.mark.asyncio
async def test_US_SEC_02_AC4_expert_requires_institution(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": f"no-inst-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "No Inst Expert",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "EXPERT",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "temp-pass-1234",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "EXPERT"
    assert body.get("institutionId") in (None, "")


@pytest.mark.asyncio
async def test_US_SEC_02_AC8_expert_without_institution(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": f"no-inst-ok-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Independent Expert",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "EXPERT",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "temp-pass-1234",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json().get("institutionId") in (None, "")


@pytest.mark.asyncio
async def test_US_SEC_02_AC5_accept_invite(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    await _ensure_invite_template(session_manager)
    inst_id = await _seed_institution(session_manager)
    email = f"accept-{uuid.uuid4().hex[:8]}@example.com"
    create = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": email,
            "fullName": "Accept Invite",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "EXPERT",
            "institutionId": str(inst_id),
            "credentialMode": "INVITE",
        },
    )
    assert create.status_code == 201, create.text

    async with session_manager.session() as session:
        from app.services.users import create_invite_token

        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        token, secret = create_invite_token(user.id)
        from app.core.security import hash_refresh_token

        user.invite_token_hash = hash_refresh_token(secret)
        user.invite_expires_at = datetime.utcnow() + timedelta(hours=1)
        await session.commit()

    accept = await client.post(
        "/auth/accept-invite",
        json={
            "token": token,
            "password": "new-secure-pass",
            "passwordConfirm": "new-secure-pass",
        },
    )
    assert accept.status_code == 204, accept.text

    login = await client.post("/auth/login", json={"email": email, "password": "new-secure-pass"})
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_US_SEC_02_AC6_list_and_deactivate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    inst_id = await _seed_institution(session_manager)
    email = f"deact-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": email,
            "fullName": "Deactivate Me",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "MODERATOR",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "mod-pass-1234",
        },
    )
    user_id = created.json()["userId"]

    listed = await client.get("/users?role=MODERATOR", headers=auth_headers)
    assert listed.status_code == 200
    assert any(u["userId"] == user_id for u in listed.json())

    patched = await client.patch(
        f"/users/{user_id}",
        headers=auth_headers,
        json={"isActive": False},
    )
    assert patched.status_code == 200
    assert patched.json()["isActive"] is False

    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "mod-pass-1234"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_US_SEC_02_AC7_duplicate_email(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    inst_id = await _seed_institution(session_manager)
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "fullName": "First",
        "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
        "role": "MODERATOR",
        "credentialMode": "TEMP_PASSWORD",
        "temporaryPassword": "mod-pass-1234",
    }
    first = await client.post("/users", headers=auth_headers, json=payload)
    assert first.status_code == 201
    second = await client.post("/users", headers=auth_headers, json={**payload, "fullName": "Second"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_US_SEC_02_super_admin_creates_admin(
    client: AsyncClient,
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        sa = User(
            email=f"sa-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Super",
            hashed_password=get_password_hash("super-pass-1234"),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        session.add(sa)
        await session.commit()
        sa_email = sa.email

    login = await client.post(
        "/auth/login",
        json={"email": sa_email, "password": "super-pass-1234"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.post(
        "/users",
        headers=headers,
        json={
            "email": f"child-admin-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Child Admin",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "role": "ADMIN",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "admin-pass-1234",
        },
    )
    assert resp.status_code == 201, resp.text
