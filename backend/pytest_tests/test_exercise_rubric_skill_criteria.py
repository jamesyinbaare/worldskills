"""Exercise rubric + skill-area criteria document."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Institution,
    Pathway,
    Region,
    Skill,
    Stage,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_skill_stage(
    session_manager: DBManager,
    competition_id: uuid.UUID,
) -> dict:
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, zone])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
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
        )
        session.add(stage)
        await session.commit()
        return {"skill_id": skill.id, "stage_id": stage.id}


@pytest.mark.asyncio
async def test_put_exercise_rubric_enables_assessment_config(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_skill_stage(session_manager, competition_id)
    stage_id = ctx["stage_id"]

    # Exercise draft with deliverables
    put_ex = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        headers=auth_headers,
        json={
            "title": "Regional Challenge",
            "brief": "Build a site",
            "deliverables": [
                {
                    "code": "main",
                    "label": "Package",
                    "required": True,
                    "allowedTypes": ["zip"],
                    "maxSizeBytes": 1_000_000,
                }
            ],
        },
    )
    assert put_ex.status_code == 200, put_ex.text

    # Publish without rubric is allowed — rubric file is optional
    pub_ok = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub_ok.status_code == 200, pub_ok.text

    # Optional structured rubric API still works for advanced config
    rubric = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/rubric",
        headers=auth_headers,
        json={
            "blindMode": True,
            "criteria": [
                {"name": "Accuracy", "type": "MEASUREMENT", "max": 15},
                {"name": "Craft", "type": "JUDGEMENT", "max": 10},
            ],
            "penalties": [{"code": "MINOR_NON_COMPLIANCE", "deduction": 2}],
        },
    )
    assert rubric.status_code == 200, rubric.text
    body = rubric.json()
    assert body["hasRubricCriteria"] is True
    assert body["blindMode"] is True
    assert len(body["criteria"]) == 2


@pytest.mark.asyncio
async def test_skill_criteria_document_upload_and_download_acl(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_skill_stage(session_manager, competition_id)
    skill_id = ctx["skill_id"]

    pdf = b"%PDF-1.4 skill-criteria"
    upload = await client.post(
        f"/competitions/{competition_id}/skills/{skill_id}/criteria-document",
        headers=auth_headers,
        files={"file": ("criteria.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["hasCriteriaDocument"] is True
    assert upload.json()["criteriaFileName"] == "criteria.pdf"

    # Institution can download
    async with session_manager.session() as session:
        region = (
            await session.execute(select(Region).limit(1))
        ).scalar_one_or_none()
        if region is None:
            region = Region(name=f"Region-{uuid.uuid4().hex[:6]}")
            session.add(region)
            await session.flush()
        inst = Institution(
            name=f"School-{uuid.uuid4().hex[:6]}",
            region_id=region.id,
        )
        session.add(inst)
        await session.flush()
        inst_user = User(
            email=f"inst-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Institution User",
            hashed_password=get_password_hash("inst-pass-123"),
            role=UserRole.INSTITUTION,
            is_active=True,
            institution_id=inst.id,
        )
        session.add(inst_user)
        await session.commit()
        email = inst_user.email

    login = await client.post(
        "/auth/login", json={"email": email, "password": "inst-pass-123"}
    )
    assert login.status_code == 200, login.text
    inst_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    dl = await client.get(
        f"/competitions/{competition_id}/skills/{skill_id}/criteria-document",
        headers=inst_headers,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content.startswith(b"%PDF")

    # Competitor not registered for skill is denied
    async with session_manager.session() as session:
        competitor = User(
            email=f"comp-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Competitor User",
            hashed_password=get_password_hash("comp-pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor)
        await session.commit()
        comp_email = competitor.email

    clogin = await client.post(
        "/auth/login", json={"email": comp_email, "password": "comp-pass-123"}
    )
    assert clogin.status_code == 200, clogin.text
    comp_headers = {"Authorization": f"Bearer {clogin.json()['access_token']}"}
    denied = await client.get(
        f"/competitions/{competition_id}/skills/{skill_id}/criteria-document",
        headers=comp_headers,
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_public_skill_criteria_download_while_registration_open(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from datetime import datetime, timedelta

    from app.models import Competition, CompetitionStatus, RegistrationWindow

    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_skill_stage(session_manager, competition_id)
    skill_id = ctx["skill_id"]

    pdf = b"%PDF-1.4 public-criteria"
    upload = await client.post(
        f"/competitions/{competition_id}/skills/{skill_id}/criteria-document",
        headers=auth_headers,
        files={"file": ("public-criteria.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    now = datetime.utcnow()
    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        existing = (
            await session.execute(
                select(RegistrationWindow).where(
                    RegistrationWindow.competition_id == competition_id
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                RegistrationWindow(
                    competition_id=cycle.id,
                    opens_at=now - timedelta(days=1),
                    closes_at=now + timedelta(days=30),
                )
            )
        else:
            existing.opens_at = now - timedelta(days=1)
            existing.closes_at = now + timedelta(days=30)
        await session.commit()

    public = await client.get(f"/competitions/{competition_id}/public")
    assert public.status_code == 200, public.text
    skills = public.json()["skills"]
    match = next(s for s in skills if s["skillId"] == str(skill_id))
    assert match["hasCriteriaDocument"] is True
    assert match["criteriaFileName"] == "public-criteria.pdf"

    dl = await client.get(
        f"/competitions/{competition_id}/public/skills/{skill_id}/criteria-document",
    )
    assert dl.status_code == 200, dl.text
    assert dl.content.startswith(b"%PDF")
