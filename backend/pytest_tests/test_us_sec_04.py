"""US-SEC-04 — Institution claims existing school by code."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, Institution, User, UserRole
from pytest_tests.conftest import region_id_by_name


async def _seed_school(
    session_manager: DBManager,
    *,
    code: str | None = None,
    active: bool = True,
) -> Institution:
    region_id = await region_id_by_name(session_manager, "Greater Accra")
    async with session_manager.session() as session:
        school = Institution(
            code=code or f"SCH-{uuid.uuid4().hex[:8].upper()}",
            name=f"Claim School {uuid.uuid4().hex[:6]}",
            region_id=region_id,
            active=active,
        )
        session.add(school)
        await session.commit()
        await session.refresh(school)
        return school


@pytest.mark.asyncio
async def test_US_SEC_04_AC1_successful_claim(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school = await _seed_school(session_manager)
    email = f"head-{uuid.uuid4().hex[:8]}@school.edu"
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": email,
            "fullName": "School Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school.code,
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["role"] == "INSTITUTION"
    assert body["user"]["institutionId"] == str(school.id)

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["institutionId"] == str(school.id)
    assert me.json()["role"] == "INSTITUTION"

    async with session_manager.session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.role == UserRole.INSTITUTION
        assert user.institution_id == school.id
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "INSTITUTION_CLAIMED",
                    AuditEvent.entity_id == str(user.id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_SEC_04_AC2_unknown_code(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": f"x-{uuid.uuid4().hex[:8]}@school.edu",
            "fullName": "Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": "DOES-NOT-EXIST",
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SCHOOL_NOT_FOUND"


@pytest.mark.asyncio
async def test_US_SEC_04_AC3_inactive_school(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school = await _seed_school(session_manager, active=False)
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": f"x-{uuid.uuid4().hex[:8]}@school.edu",
            "fullName": "Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school.code,
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SCHOOL_INACTIVE"


@pytest.mark.asyncio
async def test_US_SEC_04_AC4_already_claimed(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school = await _seed_school(session_manager)
    payload = {
        "email": f"first-{uuid.uuid4().hex[:8]}@school.edu",
        "fullName": "First Head",
        "password": "Institution1!",
        "passwordConfirm": "Institution1!",
        "schoolCode": school.code,
        "captchaToken": "ok",
    }
    first = await client.post("/auth/register-institution", json=payload)
    assert first.status_code == 201, first.text

    second = await client.post(
        "/auth/register-institution",
        json={
            **payload,
            "email": f"second-{uuid.uuid4().hex[:8]}@school.edu",
            "fullName": "Second Head",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SCHOOL_ALREADY_CLAIMED"


@pytest.mark.asyncio
async def test_US_SEC_04_AC5_duplicate_email(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school_a = await _seed_school(session_manager)
    school_b = await _seed_school(session_manager)
    email = f"dup-{uuid.uuid4().hex[:8]}@school.edu"
    first = await client.post(
        "/auth/register-institution",
        json={
            "email": email,
            "fullName": "Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school_a.code,
            "captchaToken": "ok",
        },
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/auth/register-institution",
        json={
            "email": email,
            "fullName": "Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school_b.code,
            "captchaToken": "ok",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_US_SEC_04_AC6_lookup_by_code(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school = await _seed_school(session_manager)
    ok = await client.get("/institutions/lookup", params={"code": school.code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["code"] == school.code
    assert ok.json()["name"] == school.name
    assert ok.json()["institutionId"] == str(school.id)

    missing = await client.get("/institutions/lookup", params={"code": "NOPE"})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_US_SEC_04_AC6b_search_active_schools(
    client: AsyncClient, session_manager: DBManager
) -> None:
    school = await _seed_school(session_manager)
    hit = await client.get("/institutions:search", params={"q": school.name[:4]})
    assert hit.status_code == 200, hit.text
    body = hit.json()
    assert any(row["institutionId"] == str(school.id) for row in body)

    empty = await client.get("/institutions:search", params={"q": "zzzz-no-match"})
    assert empty.status_code == 200
    assert empty.json() == []
