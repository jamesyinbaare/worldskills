"""Public homepage live stats — aggregates for open registration cycles."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    CatalogSkill,
    Competitor,
    Competition,
    CompetitionStatus,
    ExpertSkillArea,
    Family,
    MarkingScheme,
    Pathway,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    User,
    UserRole,
    Zone,
)
from app.services import public_portal as portal_service
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str], **extra) -> uuid.UUID:
    payload = competition_payload()
    payload.update(extra)
    resp = await client.post("/competitions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_open_cycle(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    activate: bool = True,
    skill_name: str = "Web Development",
    capacity: int | None = 40,
) -> dict:
    async with session_manager.session() as session:
        family = Family(name=f"Family {uuid.uuid4().hex[:6]}", active=True)
        session.add(family)
        await session.flush()
        catalog = CatalogSkill(
            name=f"{skill_name} {uuid.uuid4().hex[:6]}",
            family_id=family.id,
            active=True,
        )
        session.add(catalog)
        await session.flush()
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name=skill_name,
            catalog_skill_id=catalog.id,
            family_id=str(family.id),
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=capacity,
            active=True,
        )
        session.add(skill)
        session.add(
            RegistrationFormDefinition(
                competition_id=competition_id,
                fields=[
                    {"name": "givenNames", "type": "string", "required": True},
                    {"name": "skillIds", "type": "array", "required": True},
                    {"name": "declarationAccepted", "type": "boolean", "required": True},
                ],
                max_skills=1,
            )
        )
        now = datetime.utcnow()
        session.add(
            RegistrationWindow(
                competition_id=competition_id,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
            )
        )
        await session.flush()
        if activate:
            cycle = await session.get(Competition, competition_id)
            assert cycle is not None
            cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        return {
            "skill_id": skill.id,
            "zone_id": zone.id,
            "catalog_skill_id": catalog.id,
        }


async def _add_competitor(
    session_manager: DBManager,
    *,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    zone_id: uuid.UUID,
    status: str,
    given_names: str = "Ada",
) -> uuid.UUID:
    async with session_manager.session() as session:
        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status=status,
            given_names=given_names,
            family_name="Tester",
            flags=[],
        )
        session.add(competitor)
        await session.commit()
        return competitor.id


async def _add_expert_assignment(
    session_manager: DBManager,
    *,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    zone_id: uuid.UUID,
    full_name: str = "Portal Expert",
    catalog_skill_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with session_manager.session() as session:
        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name=full_name,
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        catalog_id = catalog_skill_id
        if catalog_id is None:
            skill = await session.get(Skill, skill_id)
            assert skill is not None and skill.catalog_skill_id is not None
            catalog_id = skill.catalog_skill_id
        session.add(
            ExpertSkillArea(expert_id=expert.id, catalog_skill_id=catalog_id)
        )
        await session.commit()
        return expert.id


@pytest.mark.asyncio
async def test_public_stats_empty_when_no_open_window(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    portal_service.reset_rate_limits()
    await _create_competition(client, auth_headers)

    resp = await client.get("/public/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["competitions"] == []
    assert body["skills"] == []
    assert body["totals"] == {
        "competitorsRegistered": 0,
        "skillAreas": 0,
        "expertsAssigned": 0,
    }
    assert body["generatedAt"]


@pytest.mark.asyncio
async def test_public_stats_counts_registered_statuses_and_excludes_others(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    portal_service.reset_rate_limits()
    competition_id = await _create_competition(client, auth_headers, name="Live Stats Cycle")
    seed = await _seed_open_cycle(session_manager, competition_id)
    skill_id = seed["skill_id"]
    zone_id = seed["zone_id"]

    include_statuses = [
        "PENDING_REVIEW",
        "REGISTERED",
        "ACTIVE_IN_STAGE",
        "FINALIST",
        "CONSENT_PENDING",
        "ELIGIBLE",
    ]
    exclude_statuses = ["DRAFT", "REJECTED", "WITHDRAWN", "DISQUALIFIED", "DQ", "INELIGIBLE"]

    for status in include_statuses:
        await _add_competitor(
            session_manager,
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            status=status,
            given_names=status[:8],
        )
    for status in exclude_statuses:
        await _add_competitor(
            session_manager,
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            status=status,
            given_names=f"X-{status[:6]}",
        )

    expert_id = await _add_expert_assignment(
        session_manager,
        competition_id=competition_id,
        skill_id=skill_id,
        zone_id=zone_id,
        full_name="Ama Expert",
    )

    resp = await client.get("/public/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["competitions"]) == 1
    assert body["competitions"][0]["competitionId"] == str(competition_id)
    assert body["competitions"][0]["name"] == "Live Stats Cycle"

    assert body["totals"]["competitorsRegistered"] == len(include_statuses)
    assert body["totals"]["skillAreas"] == 1
    assert body["totals"]["expertsAssigned"] == 1

    assert len(body["skills"]) == 1
    skill = body["skills"][0]
    assert skill["skillId"] == str(skill_id)
    assert skill["name"] == "Web Development"
    assert skill["competitorsRegistered"] == len(include_statuses)
    assert skill["capacity"] == 40
    assert len(skill["experts"]) == 1
    assert skill["experts"][0]["expertId"] == str(expert_id)
    assert skill["experts"][0]["fullName"] == "Ama Expert"


@pytest.mark.asyncio
async def test_public_stats_dedupes_experts_across_zones(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    portal_service.reset_rate_limits()
    competition_id = await _create_competition(client, auth_headers)
    seed = await _seed_open_cycle(session_manager, competition_id)
    skill_id = seed["skill_id"]

    async with session_manager.session() as session:
        expert = User(
            email=f"expert-multi-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Shared Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        skill = await session.get(Skill, skill_id)
        assert skill is not None and skill.catalog_skill_id is not None
        session.add(
            ExpertSkillArea(expert_id=expert.id, catalog_skill_id=skill.catalog_skill_id)
        )
        await session.commit()
        expert_id = expert.id

    resp = await client.get("/public/stats")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    skill = next(s for s in body["skills"] if s["skillId"] == str(skill_id))
    # Catalog skill area binding appears once per skill regardless of zones.
    assert len(skill["experts"]) == 1
    assert skill["experts"][0]["expertId"] == str(expert_id)
    assert skill["experts"][0]["fullName"] == "Shared Expert"
    # Totals use distinct expert IDs across open cycles (DB may retain other fixtures).
    assert str(expert_id) in {
        e["expertId"] for s in body["skills"] for e in s["experts"]
    }
