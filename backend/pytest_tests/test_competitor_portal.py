"""Competitor portal discovery — my registrations, stages, published exercise read."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    CompetitionStatus,
    Competitor,
    Exercise,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    Submission,
    User,
    Zone,
)
from pytest_tests.conftest import competition_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_registered_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    competitor_user: User,
    *,
    publish_exercise: bool = True,
    second_stage: bool = False,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (stage_id, competitor_id, skill_id)."""
    now = datetime.utcnow()
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
        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Regional Project",
            order=1,
            stage_type="VIRTUAL",
            quota=20,
            opens_at=now - timedelta(hours=1),
            closes_at=now + timedelta(hours=24),
        )
        session.add(stage)
        await session.flush()
        stages = [stage]
        if second_stage:
            stage2 = Stage(
                competition_id=competition_id,
                skill_id=skill.id,
                name="National Final",
                order=2,
                stage_type="PHYSICAL",
                quota=10,
                opens_at=now + timedelta(days=7),
                closes_at=now + timedelta(days=14),
            )
            session.add(stage2)
            await session.flush()
            stages.append(stage2)

        for s in stages:
            ex = Exercise(
                stage_id=s.id,
                competition_id=competition_id,
                title=f"Challenge for {s.name}",
                brief="Build something great",
                deliverables=[
                    {
                        "code": "main",
                        "label": "Main package",
                        "required": True,
                        "allowedTypes": ["pdf", "zip"],
                        "maxSizeBytes": 20_000_000,
                    }
                ],
                status="PUBLISHED" if publish_exercise and s.order == 1 else "DRAFT",
                scheme_id=scheme.id,
                late_policy="block",
            )
            session.add(ex)

        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="REGISTERED",
            eligibility_status="ELIGIBLE",
            user_id=competitor_user.id,
            given_names="Ada",
            family_name="Lovelace",
            email=competitor_user.email,
        )
        session.add(competitor)
        cycle = await session.get(
            __import__("app.models", fromlist=["Competition"]).Competition, competition_id
        )
        if cycle is not None:
            cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        return stages[0].id, competitor.id, skill.id


async def _competitor_headers(client: AsyncClient, competitor_user: User) -> dict[str, str]:
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_list_my_registrations_empty(
    client: AsyncClient,
    competitor_user: User,
) -> None:
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get("/competitors/me/registrations", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_my_registrations(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, competitor_id, skill_id = await _seed_registered_world(
        session_manager, competition_id, competitor_user
    )
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get("/competitors/me/registrations", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["competitorId"] == str(competitor_id)
    assert body[0]["competitionId"] == str(competition_id)
    assert body[0]["skillId"] == str(skill_id)
    assert body[0]["skillName"] == "Web Development"
    assert body[0]["status"] == "REGISTERED"
    assert body[0]["competitionName"]
    _ = stage_id


@pytest.mark.asyncio
async def test_my_stages_hides_draft_brief(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, competitor_id, _skill_id = await _seed_registered_world(
        session_manager,
        competition_id,
        competitor_user,
        publish_exercise=False,
        second_stage=True,
    )
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get(
        f"/competitions/{competition_id}/me/stages",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["competitorId"] == str(competitor_id)
    assert len(body["stages"]) == 2
    first = body["stages"][0]
    assert first["stageId"] == str(stage_id)
    assert first["exerciseAvailable"] is False
    assert first["exerciseTitle"] is None
    assert first["exerciseStatus"] == "DRAFT"
    assert first["windowStatus"] == "open"
    assert first["submission"]["state"] is None
    second = body["stages"][1]
    assert second["order"] == 2
    assert second["windowStatus"] == "upcoming"
    assert second["exerciseAvailable"] is False


@pytest.mark.asyncio
async def test_my_stages_published_and_submission(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, competitor_id, _skill_id = await _seed_registered_world(
        session_manager, competition_id, competitor_user, publish_exercise=True
    )
    async with session_manager.session() as session:
        session.add(
            Submission(
                competition_id=competition_id,
                competitor_id=competitor_id,
                stage_id=stage_id,
                state="OPEN",
                upload_locked=False,
            )
        )
        await session.commit()

    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get(
        f"/competitions/{competition_id}/me/stages",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    stage = body["stages"][0]
    assert stage["exerciseAvailable"] is True
    assert stage["exerciseTitle"] == "Challenge for Regional Project"
    assert stage["submission"]["state"] == "OPEN"
    assert stage["submission"]["submissionId"] is not None


@pytest.mark.asyncio
async def test_my_stages_not_registered_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get(
        f"/competitions/{competition_id}/me/stages",
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "COMPETITOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_competitor_get_published_exercise(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _competitor_id, _skill_id = await _seed_registered_world(
        session_manager, competition_id, competitor_user, publish_exercise=True
    )
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Challenge for Regional Project"
    assert body["status"] == "PUBLISHED"
    assert body["brief"] == "Build something great"


@pytest.mark.asyncio
async def test_competitor_get_draft_exercise_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _competitor_id, _skill_id = await _seed_registered_world(
        session_manager, competition_id, competitor_user, publish_exercise=False
    )
    headers = await _competitor_headers(client, competitor_user)
    resp = await client.get(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EXERCISE_NOT_PUBLISHED"
