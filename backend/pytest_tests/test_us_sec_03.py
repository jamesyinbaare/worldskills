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
    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "fullName": "New Competitor",
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
        "password": "Competitor1!",
        "passwordConfirm": "Competitor1!",
        "captchaToken": "ok",
    }
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201, first.text
    second = await client.post(
        "/auth/register",
        json={**payload, "fullName": "Second"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_US_SEC_03_AC3_password_mismatch_or_weak(client: AsyncClient) -> None:
    mismatch = await client.post(
        "/auth/register",
        json={
            "email": f"mm-{uuid.uuid4().hex[:8]}@example.com",
            "fullName": "Weak",
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
            "password": "Competitor1!",
            "passwordConfirm": "Competitor1!",
            "captchaToken": "ok",
            "role": "COMPETITOR",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["user"]["role"] == "COMPETITOR"
