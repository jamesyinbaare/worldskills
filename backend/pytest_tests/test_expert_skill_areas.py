"""Global expert catalog skill areas."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    CatalogSkill,
    Competitor,
    ExpertSkillArea,
    Family,
    MarkingScheme,
    Pathway,
    Skill,
    Submission,
    User,
    UserRole,
    Zone,
)
from app.services.assessment import _ensure_assigned
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_family_skills(session, *, count: int = 2) -> tuple[Family, list[CatalogSkill]]:
    family = Family(name=f"Family {uuid.uuid4().hex[:6]}", active=True)
    session.add(family)
    await session.flush()
    skills: list[CatalogSkill] = []
    for i in range(count):
        skill = CatalogSkill(
            name=f"Skill {i}-{uuid.uuid4().hex[:6]}",
            family_id=family.id,
            active=True,
        )
        session.add(skill)
        skills.append(skill)
    await session.flush()
    return family, skills


@pytest.mark.asyncio
async def test_set_and_list_expert_skill_areas(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        _family, catalogs = await _seed_family_skills(session, count=2)
        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Skill Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.commit()
        expert_id = expert.id
        catalog_ids = [str(c.id) for c in catalogs]

    put = await client.put(
        f"/users/{expert_id}/skill-areas",
        json={"catalogSkillIds": catalog_ids},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    items = put.json()["items"]
    assert len(items) == 2
    assert {i["catalogSkillId"] for i in items} == set(catalog_ids)

    listed = await client.get(f"/users/{expert_id}/skill-areas", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 2

    # Change to a single skill area
    put2 = await client.put(
        f"/users/{expert_id}/skill-areas",
        json={"catalogSkillIds": [catalog_ids[0]]},
        headers=auth_headers,
    )
    assert put2.status_code == 200, put2.text
    assert len(put2.json()["items"]) == 1
    assert put2.json()["items"][0]["catalogSkillId"] == catalog_ids[0]


@pytest.mark.asyncio
async def test_create_user_with_catalog_skill_ids(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        _family, catalogs = await _seed_family_skills(session, count=2)
        await session.commit()
        catalog_ids = [str(c.id) for c in catalogs]

    email = f"new-expert-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/users",
        json={
            "email": email,
            "fullName": "New Expert",
            "phoneNumber": "0551234567",
            "role": "EXPERT",
            "credentialMode": "TEMP_PASSWORD",
            "temporaryPassword": "TempPass1!",
            "catalogSkillIds": catalog_ids,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["userId"]

    areas = await client.get(f"/users/{user_id}/skill-areas", headers=auth_headers)
    assert areas.status_code == 200, areas.text
    assert {i["catalogSkillId"] for i in areas.json()["items"]} == set(catalog_ids)


@pytest.mark.asyncio
async def test_scoring_authorized_via_catalog_skill_all_zones(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    async with session_manager.session() as session:
        family, catalogs = await _seed_family_skills(session, count=1)
        catalog = catalogs[0]
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            catalog_skill_id=catalog.id,
            family_id=str(family.id),
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        zone_a = Zone(competition_id=competition_id, name="Zone A", active=True)
        zone_b = Zone(competition_id=competition_id, name="Zone B", active=True)
        session.add_all([skill, zone_a, zone_b])
        await session.flush()
        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Global Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        session.add(ExpertSkillArea(expert_id=expert.id, catalog_skill_id=catalog.id))
        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone_b.id,
            ref_no="C-1",
        )
        session.add(competitor)
        await session.flush()
        sub = Submission(competition_id=competition_id, competitor_id=competitor.id, state="ACCEPTED")
        session.add(sub)
        await session.commit()
        expert_id = expert.id
        competitor_id = competitor.id

    async with session_manager.session() as session:
        expert = await session.get(User, expert_id)
        competitor = await session.get(Competitor, competitor_id)
        assert expert is not None and competitor is not None
        # All zones: no competition ExpertAssignment required
        await _ensure_assigned(
            session, competition_id=competition_id, expert=expert, competitor=competitor
        )


@pytest.mark.asyncio
async def test_assignment_without_zone_allowed_when_expert_has_catalog_skill(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    async with session_manager.session() as session:
        family, catalogs = await _seed_family_skills(session, count=1)
        catalog = catalogs[0]
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            catalog_skill_id=catalog.id,
            family_id=str(family.id),
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        session.add(skill)
        await session.flush()
        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Zone Optional Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        session.add(ExpertSkillArea(expert_id=expert.id, catalog_skill_id=catalog.id))
        await session.commit()
        expert_id = expert.id
        skill_id = skill.id

    resp = await client.post(
        f"/competitions/{competition_id}/assignments",
        json={"expertId": str(expert_id), "skillId": str(skill_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["zoneId"] is None


@pytest.mark.asyncio
async def test_assessor_queue_excludes_non_scoreable_states(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Queue must only list ACCEPTED/LATE — not UPLOADED/OPEN (assessment gate)."""
    competition_id = await _create_competition(client, auth_headers)
    async with session_manager.session() as session:
        family, catalogs = await _seed_family_skills(session, count=1)
        catalog = catalogs[0]
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            catalog_skill_id=catalog.id,
            family_id=str(family.id),
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        session.add(skill)
        await session.flush()
        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Queue Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.flush()
        session.add(ExpertSkillArea(expert_id=expert.id, catalog_skill_id=catalog.id))

        comp_uploaded = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            ref_no="C-UP",
        )
        comp_accepted = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            ref_no="C-OK",
        )
        session.add_all([comp_uploaded, comp_accepted])
        await session.flush()
        sub_uploaded = Submission(
            competition_id=competition_id,
            competitor_id=comp_uploaded.id,
            state="UPLOADED",
        )
        sub_accepted = Submission(
            competition_id=competition_id,
            competitor_id=comp_accepted.id,
            state="ACCEPTED",
        )
        session.add_all([sub_uploaded, sub_accepted])
        await session.commit()
        expert_id = expert.id
        uploaded_id = sub_uploaded.id
        accepted_id = sub_accepted.id

    queue = await client.get(
        f"/competitions/{competition_id}/assessors/{expert_id}/queue",
        headers=auth_headers,
    )
    assert queue.status_code == 200, queue.text
    submission_ids = {s["submissionId"] for s in queue.json()["submissions"]}
    assert str(accepted_id) in submission_ids
    assert str(uploaded_id) not in submission_ids
    assert all(s["state"] in {"ACCEPTED", "LATE"} for s in queue.json()["submissions"])
