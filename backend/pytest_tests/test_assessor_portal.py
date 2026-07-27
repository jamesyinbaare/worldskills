"""Expert assessor portal — my assignments discovery."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    ExpertAssignment,
    MarkingScheme,
    Pathway,
    Skill,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_assignment(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    expert: User | None = None,
) -> dict:
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()

        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=20,
            active=True,
        )
        session.add(skill)
        await session.flush()

        if expert is None:
            expert = User(
                email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Portal Expert",
                hashed_password=get_password_hash("expert-pass-123"),
                role=UserRole.EXPERT,
                is_active=True,
            )
            session.add(expert)
            await session.flush()

        assignment = ExpertAssignment(
            competition_id=competition_id,
            expert_id=expert.id,
            skill_id=skill.id,
            zone_id=zone.id,
            coi_flags=[],
        )
        session.add(assignment)
        await session.commit()
        return {
            "expert": expert,
            "skill_id": skill.id,
            "zone_id": zone.id,
            "assignment_id": assignment.id,
        }


async def _login(client: AsyncClient, user: User, password: str = "expert-pass-123") -> dict[str, str]:
    resp = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_list_my_assignments_empty(client: AsyncClient, session_manager: DBManager) -> None:
    async with session_manager.session() as session:
        expert = User(
            email=f"expert-empty-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Unassigned Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        expert_id = expert.id
        expert_email = expert.email
        await session.commit()

    # Rebuild a lightweight user for login helper
    expert_ref = User(
        id=expert_id,
        email=expert_email,
        full_name="Unassigned Expert",
        hashed_password="",
        role=UserRole.EXPERT,
        is_active=True,
    )
    headers = await _login(client, expert_ref)
    resp = await client.get("/assessors/me/assignments", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_my_assignments_returns_names(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_assignment(session_manager, competition_id)
    headers = await _login(client, ctx["expert"])

    resp = await client.get("/assessors/me/assignments", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    assert row["assignmentId"] == str(ctx["assignment_id"])
    assert row["competitionId"] == str(competition_id)
    assert row["competitionName"]
    assert row["skillId"] == str(ctx["skill_id"])
    assert row["skillName"] == "Web Development"
    assert row["zoneId"] == str(ctx["zone_id"])
    assert row["zoneName"] == "Greater Accra"


@pytest.mark.asyncio
async def test_list_my_assignments_forbidden_for_non_expert(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/assessors/me/assignments", headers=auth_headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"
