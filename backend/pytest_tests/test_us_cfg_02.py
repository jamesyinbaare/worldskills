"""US-CFG-02 — Clone, validate and activate a cycle."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AuditEvent, Cycle, CycleStatus, Skill, Stage
from pytest_tests.conftest import cycle_payload, seed_complete_config


@pytest.mark.asyncio
async def test_US_CFG_02_AC1_clone_copies_config_not_ops(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/cycles", json=cycle_payload(), headers=auth_headers)
    cycle_id = uuid.UUID(create.json()["cycleId"])

    async with session_manager.session() as session:
        cycle = await session.get(Cycle, cycle_id)
        assert cycle is not None
        await seed_complete_config(session, cycle)

    clone = await client.post(f"/cycles/{cycle_id}:clone", headers=auth_headers)
    assert clone.status_code == 201, clone.text
    new_id = uuid.UUID(clone.json()["newCycleId"])
    assert new_id != cycle_id

    async with session_manager.session() as session:
        new_cycle = await session.get(Cycle, new_id)
        assert new_cycle is not None
        assert new_cycle.status == CycleStatus.DRAFT
        skills = (await session.execute(select(Skill).where(Skill.cycle_id == new_id))).scalars().all()
        assert len(skills) >= 1


@pytest.mark.asyncio
async def test_US_CFG_02_AC2_validation_blocks_activation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/cycles", json=cycle_payload(), headers=auth_headers)
    cycle_id = create.json()["cycleId"]

    async with session_manager.session() as session:
        cycle = await session.get(Cycle, uuid.UUID(cycle_id))
        assert cycle is not None
        # Incomplete skill (no age rule)
        session.add(Skill(cycle_id=cycle.id, name="Incomplete Skill", active=True))
        session.add(
            Stage(
                cycle_id=cycle.id,
                name="Bare Stage",
                order=1,
                quota=None,
                scheme_id=None,
            )
        )
        await session.commit()

    activate = await client.post(f"/cycles/{cycle_id}:activate", headers=auth_headers)
    assert activate.status_code == 409
    assert activate.json()["error"]["code"] == "CONFIG_INCOMPLETE"

    validate = await client.post(f"/cycles/{cycle_id}:validate", headers=auth_headers)
    assert validate.status_code == 200
    body = validate.json()
    assert body["ok"] is False
    assert any(i["code"] == "CONFIG_INCOMPLETE" for i in body["issues"])
    assert any("link" in i and i["link"] for i in body["issues"])


@pytest.mark.asyncio
async def test_US_CFG_02_AC3_quota_inconsistent(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/cycles", json=cycle_payload(), headers=auth_headers)
    cycle_id = uuid.UUID(create.json()["cycleId"])

    async with session_manager.session() as session:
        from app.models import AgeRule, MarkingScheme, Pathway

        cycle = await session.get(Cycle, cycle_id)
        assert cycle is not None
        age = AgeRule(cycle_id=cycle.id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle.id, name="P")
        scheme = MarkingScheme(cycle_id=cycle.id, name="S")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            cycle_id=cycle.id,
            name="Skill",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
        )
        session.add(skill)
        await session.flush()
        session.add(
            Stage(
                cycle_id=cycle.id,
                skill_id=skill.id,
                name="Prior",
                order=1,
                quota=5,
                scheme_id=scheme.id,
            )
        )
        session.add(
            Stage(
                cycle_id=cycle.id,
                skill_id=skill.id,
                name="Next",
                order=2,
                quota=20,
                scheme_id=scheme.id,
            )
        )
        await session.commit()

    validate = await client.post(f"/cycles/{cycle_id}:validate", headers=auth_headers)
    body = validate.json()
    assert any(i["code"] == "QUOTA_INCONSISTENT" for i in body["issues"])


@pytest.mark.asyncio
async def test_US_CFG_02_AC4_successful_activation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/cycles", json=cycle_payload(), headers=auth_headers)
    cycle_id = uuid.UUID(create.json()["cycleId"])

    async with session_manager.session() as session:
        cycle = await session.get(Cycle, cycle_id)
        assert cycle is not None
        await seed_complete_config(session, cycle)

    activate = await client.post(f"/cycles/{cycle_id}:activate", headers=auth_headers)
    assert activate.status_code == 200, activate.text
    assert activate.json()["status"] == "ACTIVE"

    # Idempotent
    again = await client.post(f"/cycles/{cycle_id}:activate", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["status"] == "ACTIVE"

    async with session_manager.session() as session:
        result = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(cycle_id),
                AuditEvent.action == "CYCLE_ACTIVATE",
            )
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_US_CFG_02_AC5_post_lock_edit_refused(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/cycles", json=cycle_payload(), headers=auth_headers)
    cycle_id = uuid.UUID(create.json()["cycleId"])

    async with session_manager.session() as session:
        cycle = await session.get(Cycle, cycle_id)
        assert cycle is not None
        await seed_complete_config(session, cycle)

    await client.post(f"/cycles/{cycle_id}:activate", headers=auth_headers)

    edit = await client.patch(
        f"/cycles/{cycle_id}",
        json={"name": "Hacked Name"},
        headers=auth_headers,
    )
    assert edit.status_code == 409
    assert edit.json()["error"]["code"] == "CYCLE_LOCKED"
