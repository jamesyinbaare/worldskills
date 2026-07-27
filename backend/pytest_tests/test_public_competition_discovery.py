"""Public competition discovery — open list, about page, public-profile edit."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    CompetitionStatus,
    MarkingScheme,
    Pathway,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    User,
    UserRole,
)
from pytest_tests.conftest import competition_payload, login_as


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
) -> uuid.UUID:
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
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
            from app.models import Competition

            cycle = await session.get(Competition, competition_id)
            assert cycle is not None
            cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        return skill.id


@pytest.mark.asyncio
async def test_public_open_cycles_anonymous(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    open_id = await _create_competition(
        client, auth_headers, description="National finals about text"
    )
    draft_id = await _create_competition(client, auth_headers, description="Still a draft")
    await _seed_open_cycle(session_manager, open_id)
    # draft has no window / not activated

    resp = await client.get("/competitions:open-for-registration")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {c["competitionId"] for c in body}
    assert str(open_id) in ids
    assert str(draft_id) not in ids
    match = next(c for c in body if c["competitionId"] == str(open_id))
    assert match["description"] == "National finals about text"
    assert match["window"] is not None


@pytest.mark.asyncio
async def test_public_cycle_detail_and_404_when_closed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(
        client, auth_headers, description="Read about this competition"
    )
    skill_id = await _seed_open_cycle(session_manager, competition_id)

    ok = await client.get(f"/competitions/{competition_id}/public")
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data["name"]
    assert data["description"] == "Read about this competition"
    assert data["period"]["start"]
    assert data["window"]["closesAt"]
    assert str(skill_id) in {s["skillId"] for s in data["skills"]}

    # Close window → 404
    async with session_manager.session() as session:
        from sqlalchemy import select

        from app.models import RegistrationWindow

        result = await session.execute(
            select(RegistrationWindow).where(RegistrationWindow.competition_id == competition_id)
        )
        window = result.scalar_one()
        window.closes_at = datetime.utcnow() - timedelta(hours=1)
        await session.commit()

    closed = await client.get(f"/competitions/{competition_id}/public")
    assert closed.status_code == 404


@pytest.mark.asyncio
async def test_admin_patch_public_profile_on_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed_open_cycle(session_manager, competition_id)

    patched = await client.patch(
        f"/competitions/{competition_id}/public-profile",
        json={"description": "Updated about for active cycle"},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["description"] == "Updated about for active cycle"

    public = await client.get(f"/competitions/{competition_id}/public")
    assert public.status_code == 200
    assert public.json()["description"] == "Updated about for active cycle"

    # Non-admin forbidden
    async with session_manager.session() as session:
        email = f"comp-{uuid.uuid4().hex[:8]}@example.com"
        session.add(
            User(
                email=email,
                full_name="Competitor",
                hashed_password=get_password_hash("CompPass1!"),
                role=UserRole.COMPETITOR,
                is_active=True,
            )
        )
        await session.commit()
    comp = await login_as(client, email, "CompPass1!")
    denied = await client.patch(
        f"/competitions/{competition_id}/public-profile",
        json={"description": "Nope"},
        headers=comp,
    )
    assert denied.status_code == 403
