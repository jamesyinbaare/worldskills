"""US-SKL-02 — Manage skill families and the skill catalog."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, CatalogSkill, Family, Skill, User
from pytest_tests.conftest import competition_payload


@pytest.mark.asyncio
async def test_US_SKL_02_AC1_create_family(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    resp = await client.post(
        "/families",
        json={"name": "Information Technology", "description": "IT skills"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Information Technology"
    assert body["active"] is True
    assert "familyId" in body

    listed = await client.get("/families", headers=auth_headers)
    assert listed.status_code == 200
    assert any(f["familyId"] == body["familyId"] for f in listed.json())

    async with session_manager.session() as session:
        family = await session.get(Family, uuid.UUID(body["familyId"]))
        assert family is not None
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "FAMILY_CREATE",
                    AuditEvent.entity_id == body["familyId"],
                )
            )
        ).scalar_one_or_none()
        assert audit is not None

    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200
    denied = await client.post(
        "/families",
        json={"name": "Denied Family"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_US_SKL_02_AC2_create_catalog_skill_with_family(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    fam = await client.post("/families", json={"name": "Construction"}, headers=auth_headers)
    assert fam.status_code == 201, fam.text
    family_id = fam.json()["familyId"]

    resp = await client.post(
        "/skills",
        json={
            "name": "Bricklaying",
            "number": "12",
            "familyId": family_id,
            "description": "Masonry",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Bricklaying"
    assert body["familyId"] == family_id
    assert body["familyName"] == "Construction"
    assert body["active"] is True

    listed = await client.get("/skills", headers=auth_headers)
    assert listed.status_code == 200
    assert any(s["skillId"] == body["skillId"] for s in listed.json())

    async with session_manager.session() as session:
        skill = await session.get(CatalogSkill, uuid.UUID(body["skillId"]))
        assert skill is not None
        assert skill.family_id == uuid.UUID(family_id)


@pytest.mark.asyncio
async def test_US_SKL_02_AC3_family_required(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    missing = await client.post(
        "/skills",
        json={"name": "No Family Skill"},
        headers=auth_headers,
    )
    assert missing.status_code == 422

    fake_family = str(uuid.uuid4())
    unresolved = await client.post(
        "/skills",
        json={"name": "Bad Family Skill", "familyId": fake_family},
        headers=auth_headers,
    )
    assert unresolved.status_code == 409, unresolved.text
    assert unresolved.json()["error"]["code"] == "CONFIG_INCOMPLETE"
    reasons = [f["reason"] for f in unresolved.json()["error"].get("fields", [])]
    assert "CONFIG_INCOMPLETE" in reasons or "REQUIRED" in reasons


@pytest.mark.asyncio
async def test_US_SKL_02_AC4_duplicate_name(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fam = await client.post("/families", json={"name": "Unique Fam"}, headers=auth_headers)
    assert fam.status_code == 201
    family_id = fam.json()["familyId"]

    dup_fam = await client.post("/families", json={"name": "Unique Fam"}, headers=auth_headers)
    assert dup_fam.status_code == 409
    assert any(f["reason"] == "DUPLICATE" for f in dup_fam.json()["error"]["fields"])

    sk = await client.post(
        "/skills",
        json={"name": "Unique Skill", "familyId": family_id},
        headers=auth_headers,
    )
    assert sk.status_code == 201
    dup_sk = await client.post(
        "/skills",
        json={"name": "Unique Skill", "familyId": family_id},
        headers=auth_headers,
    )
    assert dup_sk.status_code == 409
    assert any(f["reason"] == "DUPLICATE" for f in dup_sk.json()["error"]["fields"])


@pytest.mark.asyncio
async def test_US_SKL_02_AC5_deactivate_without_orphaning_cycles(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    fam = await client.post("/families", json={"name": "Deact Fam"}, headers=auth_headers)
    family_id = fam.json()["familyId"]
    sk = await client.post(
        "/skills",
        json={"name": "Deact Skill", "familyId": family_id},
        headers=auth_headers,
    )
    assert sk.status_code == 201, sk.text
    catalog_id = sk.json()["skillId"]

    cycle = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    assert cycle.status_code == 201
    competition_id = cycle.json()["competitionId"]

    assoc = await client.post(
        f"/competitions/{competition_id}/skills",
        json={
            "skillId": catalog_id,
            "ageRule": {
                "maxAge": 25,
                "referenceDate": str(date.today()),
                "openCategoryEnabled": False,
            },
            "capacity": 10,
        },
        headers=auth_headers,
    )
    assert assoc.status_code == 201, assoc.text
    cycle_skill_id = assoc.json()["skillId"]

    patch = await client.patch(
        f"/skills/{catalog_id}",
        json={"active": False},
        headers=auth_headers,
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["active"] is False

    # Existing association still resolvable
    listed = await client.get(f"/competitions/{competition_id}/skills", headers=auth_headers)
    assert listed.status_code == 200
    row = next(s for s in listed.json() if s["skillId"] == cycle_skill_id)
    assert row["name"] == "Deact Skill"
    assert row["catalogSkillId"] == catalog_id

    # Hidden from active catalog picker
    active_only = await client.get("/skills?active=true", headers=auth_headers)
    assert active_only.status_code == 200
    assert all(s["skillId"] != catalog_id for s in active_only.json())

    # New association blocked
    cycle2 = await client.post(
        "/competitions",
        json=competition_payload(name="Other Competition For Deact"),
        headers=auth_headers,
    )
    assert cycle2.status_code == 201
    blocked = await client.post(
        f"/competitions/{cycle2.json()['competitionId']}/skills",
        json={
            "skillId": catalog_id,
            "ageRule": {"maxAge": 22, "openCategoryEnabled": False},
        },
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    async with session_manager.session() as session:
        cycle_skill = await session.get(Skill, uuid.UUID(cycle_skill_id))
        assert cycle_skill is not None
        assert cycle_skill.catalog_skill_id == uuid.UUID(catalog_id)
