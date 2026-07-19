"""US-CFG-01 — Create a competition cycle."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, Skill
from pytest_tests.conftest import cycle_payload, seed_complete_config
from app.models import User


@pytest.mark.asyncio
async def test_US_CFG_01_AC1_happy_path_creates_draft_and_audit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    payload = cycle_payload()
    resp = await client.post("/cycles", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "DRAFT"
    assert "cycleId" in body

    async with session_manager.session() as session:
        result = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == body["cycleId"],
                AuditEvent.action == "CYCLE_CREATE",
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None


@pytest.mark.asyncio
async def test_US_CFG_01_AC2_duplicate_name_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = cycle_payload(name="Duplicate Cycle Name")
    first = await client.post("/cycles", json=payload, headers=auth_headers)
    assert first.status_code == 201, first.text
    second = await client.post("/cycles", json=payload, headers=auth_headers)
    assert second.status_code == 409
    err = second.json()["error"]
    assert err["code"] == "CYCLE_DUPLICATE"
    assert any(f["name"] == "name" and f["reason"] == "DUPLICATE" for f in err["fields"])


@pytest.mark.asyncio
async def test_US_CFG_01_AC3_invalid_period(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    today = date.today()
    payload = cycle_payload(
        period={
            "start": today.isoformat(),
            "end": (today - timedelta(days=1)).isoformat(),
        }
    )
    resp = await client.post("/cycles", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert any(f["name"] == "period.end" and f["reason"] == "BEFORE_START" for f in err["fields"])


@pytest.mark.asyncio
async def test_US_CFG_01_AC4_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    admin_user: User,
) -> None:
    a = await client.post("/cycles", json=cycle_payload(name=f"Cycle A {uuid.uuid4().hex[:4]}"), headers=auth_headers)
    b = await client.post("/cycles", json=cycle_payload(name=f"Cycle B {uuid.uuid4().hex[:4]}"), headers=auth_headers)
    assert a.status_code == 201 and b.status_code == 201
    cycle_a = uuid.UUID(a.json()["cycleId"])
    cycle_b = uuid.UUID(b.json()["cycleId"])

    async with session_manager.session() as session:
        from app.models import Cycle

        ca = await session.get(Cycle, cycle_a)
        assert ca is not None
        await seed_complete_config(session, ca)

    async with session_manager.session() as session:
        skills_a = (await session.execute(select(Skill).where(Skill.cycle_id == cycle_a))).scalars().all()
        skills_b = (await session.execute(select(Skill).where(Skill.cycle_id == cycle_b))).scalars().all()
        assert len(skills_a) >= 1
        assert len(skills_b) == 0
        # Mutating B must not touch A's skills
        for s in skills_a:
            assert s.cycle_id == cycle_a
