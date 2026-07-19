"""US-SKL-01 — Define a skill area with its pathway, age rule and capacity."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.errors import AppError
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AgeRule, AuditEvent, MarkingScheme, Pathway, Skill, User
from app.services.config_resolution import load_cycle_config
from app.services.skills import enforce_skill_capacity
from pytest_tests.conftest import cycle_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_links(
    session_manager: DBManager, cycle_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with session_manager.session() as session:
        age = AgeRule(cycle_id=cycle_id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.commit()
        return age.id, path.id, scheme.id


@pytest.mark.asyncio
async def test_US_SKL_01_AC1_create_skill(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    age_id, path_id, scheme_id = await _seed_links(session_manager, cycle_id)

    payload = {
        "name": "Web Development",
        "number": "17",
        "familyId": "it",
        "ageRuleId": str(age_id),
        "pathwayId": str(path_id),
        "schemeId": str(scheme_id),
        "capacity": 20,
    }
    resp = await client.post(f"/cycles/{cycle_id}/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Web Development"
    assert body["active"] is True
    assert "skillId" in body

    async with session_manager.session() as session:
        skill = await session.get(Skill, uuid.UUID(body["skillId"]))
        assert skill is not None
        assert skill.cycle_id == cycle_id
        assert skill.age_rule_id == age_id
        assert skill.pathway_id == path_id
        assert skill.scheme_id == scheme_id
        assert skill.capacity == 20

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SKILL_CREATE",
                    AuditEvent.entity_id == body["skillId"],
                )
            )
        ).scalar_one_or_none()
        assert audit is not None

    # Non-admin forbidden
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200
    comp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = await client.post(
        f"/cycles/{cycle_id}/skills",
        json={**payload, "name": "Another Skill"},
        headers=comp_headers,
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_US_SKL_01_AC1_validation_failures(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    age_id, path_id, scheme_id = await _seed_links(session_manager, cycle_id)
    base = {
        "name": "Cloud Computing",
        "ageRuleId": str(age_id),
        "pathwayId": str(path_id),
        "schemeId": str(scheme_id),
    }
    ok = await client.post(f"/cycles/{cycle_id}/skills", json=base, headers=auth_headers)
    assert ok.status_code == 201, ok.text

    dup = await client.post(f"/cycles/{cycle_id}/skills", json=base, headers=auth_headers)
    assert dup.status_code == 409
    err = dup.json()["error"]
    assert any(f["name"] == "name" and f["reason"] == "DUPLICATE" for f in err["fields"])

    bad_cap = await client.post(
        f"/cycles/{cycle_id}/skills",
        json={**base, "name": "Robotics", "capacity": 0},
        headers=auth_headers,
    )
    assert bad_cap.status_code == 422
    assert any(
        f["name"] == "capacity" and f["reason"] == "INVALID_CAPACITY"
        for f in bad_cap.json()["error"]["fields"]
    )

    missing_fk = await client.post(
        f"/cycles/{cycle_id}/skills",
        json={
            "name": "Mechatronics",
            "ageRuleId": str(uuid.uuid4()),
            "pathwayId": str(path_id),
            "schemeId": str(scheme_id),
        },
        headers=auth_headers,
    )
    assert missing_fk.status_code == 409
    assert missing_fk.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_SKL_01_AC2_per_skill_age_rule(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    async with session_manager.session() as session:
        age_young = AgeRule(cycle_id=cycle_id, name="U18", max_age=18)
        age_older = AgeRule(cycle_id=cycle_id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        session.add_all([age_young, age_older, path, scheme])
        await session.flush()
        skill_a = Skill(
            cycle_id=cycle_id,
            name="Skill A",
            age_rule_id=age_young.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
        )
        skill_b = Skill(
            cycle_id=cycle_id,
            name="Skill B",
            age_rule_id=age_older.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
        )
        session.add_all([skill_a, skill_b])
        await session.commit()
        skill_a_id, skill_b_id = skill_a.id, skill_b.id

    async with session_manager.session() as session:
        cfg = await load_cycle_config(session, cycle_id)
        rule_a = cfg.age_rule_for_skill(skill_a_id)
        rule_b = cfg.age_rule_for_skill(skill_b_id)
        assert rule_a.max_age == 18
        assert rule_b.max_age == 25
        assert rule_a.id != rule_b.id


@pytest.mark.asyncio
async def test_US_SKL_01_AC3_capacity_enforced() -> None:
    skill = Skill(name="Full", capacity=2, active=True)
    enforce_skill_capacity(skill, occupied_count=1)  # under capacity — ok

    with pytest.raises(AppError) as exc_info:
        enforce_skill_capacity(skill, occupied_count=2)
    assert exc_info.value.code == "SKILL_CAPACITY_REACHED"

    unlimited = Skill(name="Open", capacity=None, active=True)
    enforce_skill_capacity(unlimited, occupied_count=999)  # no capacity — ok


@pytest.mark.asyncio
async def test_US_SKL_01_AC4_incomplete_skill_on_validate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    _age_id, path_id, scheme_id = await _seed_links(session_manager, cycle_id)

    # Create via API without age rule (draft-incomplete allowed)
    resp = await client.post(
        f"/cycles/{cycle_id}/skills",
        json={
            "name": "Incomplete Skill",
            "pathwayId": str(path_id),
            "schemeId": str(scheme_id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    skill_id = resp.json()["skillId"]

    validate = await client.post(f"/cycles/{cycle_id}:validate", headers=auth_headers)
    assert validate.status_code == 200
    body = validate.json()
    assert body["ok"] is False
    assert any(
        i["code"] == "CONFIG_INCOMPLETE" and i["entity"] == skill_id for i in body["issues"]
    )
