"""US-SUB-01 — Configure and publish an Exercise per stage."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AgeRule, Exercise, MarkingScheme, Pathway, Skill, Stage, Zone
from pytest_tests.conftest import competition_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_stage(
    session_manager: DBManager, competition_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns stage_id, scheme_id."""
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
            max_age=25,
            open_category_enabled=False,
            capacity=40,
            active=True,
        )
        session.add(skill)
        await session.flush()
        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            stage_type="VIRTUAL",
            quota=20,
            quota_by_zone={str(zone.id): 20},
        )
        session.add(stage)
        await session.commit()
        return stage.id, scheme.id


def _exercise_body(scheme_id: uuid.UUID | None = None, *, deliverables: bool = True) -> dict:
    body: dict = {
        "title": "Regional challenge",
        "brief": "Build a web page",
        "deliverables": (
            [
                {
                    "code": "main",
                    "label": "Main package",
                    "required": True,
                    "allowedTypes": ["pdf", "zip"],
                    "maxSizeBytes": 20_000_000,
                }
            ]
            if deliverables
            else []
        ),
        "latePolicy": "block",
    }
    if scheme_id is not None:
        body["schemeId"] = str(scheme_id)
    return body


@pytest.mark.asyncio
async def test_US_SUB_01_AC1_create_exercise_1to1(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    resp = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "DRAFT"
    assert body["title"] == "Regional challenge"
    assert body["stageId"] == str(stage_id)
    async with session_manager.session() as session:
        ex = (
            await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
        ).scalar_one()
        assert ex.status == "DRAFT"


@pytest.mark.asyncio
async def test_US_SUB_01_AC2_reject_second_exercise_same_stage(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """PUT is upsert (1:1) — second PUT updates; creating a second row is impossible."""
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    first = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json={**_exercise_body(scheme_id), "title": "Updated title"},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["title"] == "Updated title"
    async with session_manager.session() as session:
        rows = (
            await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
        ).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_US_SUB_01_AC3_attach_marking_scheme(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    resp = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["schemeId"] == str(scheme_id)


@pytest.mark.asyncio
async def test_US_SUB_01_AC4_publish_requires_scheme_and_deliverables(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(None, deliverables=False),
        headers=auth_headers,
    )
    pub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub.status_code == 422, pub.text
    reasons = {f["reason"] for f in pub.json()["error"]["fields"]}
    assert "REQUIRED" in reasons


@pytest.mark.asyncio
async def test_US_SUB_01_AC5_publish_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    pub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub.status_code == 200, pub.text
    assert pub.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_US_SUB_01_AC6_cycle_validate_exercise_advisory(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    # Stage exists but no published exercise — advisory, not blocking by itself if other config incomplete
    validate = await client.post(f"/competitions/{competition_id}:validate", headers=auth_headers)
    assert validate.status_code == 200
    body = validate.json()
    codes = {i["code"] for i in body["issues"]}
    assert "EXERCISE_PENDING" in codes
    assert any(i.get("severity") == "advisory" and i["code"] == "EXERCISE_PENDING" for i in body["issues"])

    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    # Still may fail for other reasons (registration window etc.) but exercise issue should be gone
    validate2 = await client.post(f"/competitions/{competition_id}:validate", headers=auth_headers)
    assert validate2.status_code == 200
    exercise_issues = [
        i
        for i in validate2.json()["issues"]
        if i.get("code") in {"EXERCISE_PENDING", "EXERCISE_NOT_PUBLISHED"}
        or "Exercise" in i.get("message", "")
    ]
    assert exercise_issues == []


@pytest.mark.asyncio
async def test_US_SUB_01_AC7_competitor_cannot_use_unpublished(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from app.core.security import get_password_hash
    from app.models import Competitor, User, UserRole

    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    # DRAFT — not published
    async with session_manager.session() as session:
        stage = await session.get(Stage, stage_id)
        assert stage is not None
        zone = (
            await session.execute(select(Zone).where(Zone.competition_id == competition_id))
        ).scalar_one()
        competitor_user = User(
            email=f"comp-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Comp Etitor",
            hashed_password=get_password_hash("comp-pass-1234"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor_user)
        await session.flush()
        competitor = Competitor(
            competition_id=competition_id,
            skill_id=stage.skill_id,
            zone_id=zone.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Comp",
            family_name="Etitor",
            user_id=competitor_user.id,
        )
        session.add(competitor)
        await session.commit()
        comp_email = competitor_user.email

    login = await client.post(
        "/auth/login",
        json={"email": comp_email, "password": "comp-pass-1234"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    open_sub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/submissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert open_sub.status_code in (403, 409), open_sub.text
    code = open_sub.json()["error"]["code"]
    assert code in {"EXERCISE_NOT_PUBLISHED", "CONFIG_INCOMPLETE", "FORBIDDEN", "INELIGIBLE"}
