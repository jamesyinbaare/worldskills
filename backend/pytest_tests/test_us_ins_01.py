"""US-INS-01 — Institution nominates a competitor with limit and approval workflow."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    Competitor,
    Institution,
    InstitutionCompetitionMembership,
    MarkingScheme,
    NominationLimit,
    NotificationOutbox,
    Pathway,
    Skill,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload, map_region_to_zone, region_id_by_name


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_nomination_context(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    limit: int = 2,
    skill_active: bool = True,
) -> dict[str, uuid.UUID]:
    region_id = await region_id_by_name(session_manager, "Greater Accra")
    async with session_manager.session() as session:
        inst = Institution(name=f"Tech Inst {uuid.uuid4().hex[:6]}", region_id=region_id)
        session.add(inst)
        await session.flush()

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
            active=skill_active,
            school_quota=limit,
        )
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([skill, zone])
        await session.flush()

        session.add(
            InstitutionCompetitionMembership(
                competition_id=competition_id,
                institution_id=inst.id,
                zone_id=zone.id,
            )
        )
        session.add(
            NominationLimit(
                competition_id=competition_id,
                institution_id=inst.id,
                skill_id=skill.id,
                max_nominations=limit,
            )
        )

        inst_user = User(
            email=f"inst-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Institution Head",
            hashed_password=get_password_hash("inst-pass-123"),
            role=UserRole.INSTITUTION,
            is_active=True,
            institution_id=inst.id,
        )
        session.add(inst_user)
        await session.commit()
        out = {
            "institution_id": inst.id,
            "skill_id": skill.id,
            "zone_id": zone.id,
            "inst_user_id": inst_user.id,
            "region_id": region_id,
        }
    await map_region_to_zone(session_manager, competition_id, region_id, out["zone_id"])
    return out


async def _inst_headers(client: AsyncClient, session_manager: DBManager, user_id: uuid.UUID) -> dict[str, str]:
    async with session_manager.session() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.email is not None
        email = user.email
    login = await client.post("/auth/login", json={"email": email, "password": "inst-pass-123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_INS_01_AC1_within_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id, limit=2)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    resp = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-001",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["competitorId"] is not None

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(body["competitorId"]))
        assert competitor is not None
        assert competitor.status == "PENDING_REVIEW"

        note = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "NOMINATION_PENDING_REVIEW",
                    NotificationOutbox.recipient_role == "ADMIN",
                )
            )
        ).scalar_one_or_none()
        assert note is not None

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "NOMINATION_CREATE",
                    AuditEvent.entity_id == body["nominationId"],
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_INS_01_AC2_limit_exceeded(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id, limit=1)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    first = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-A",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-B",
        },
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "NOMINATION_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_US_INS_01_AC2_inactive_skill(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id, skill_active=False)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    resp = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-X",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SKILL_INACTIVE"


@pytest.mark.asyncio
async def test_US_INS_01_AC3_approval(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    created = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-OK",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    nid = created.json()["nominationId"]
    competitor_id = created.json()["competitorId"]

    approved = await client.post(f"/nominations/{nid}:approve", headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(competitor_id))
        assert competitor is not None
        assert competitor.status == "REGISTERED"

        notes = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.template == "NOMINATION_APPROVED")
            )
        ).scalars().all()
        roles = {n.recipient_role for n in notes}
        assert "INSTITUTION" in roles
        assert "ADMIN" in roles

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "NOMINATION_APPROVE",
                    AuditEvent.entity_id == nid,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_INS_01_AC4_rejection(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    created = await client.post(
        f"/competitions/{competition_id}/nominations",
        json={
            "institutionId": str(ctx["institution_id"]),
            "skillId": str(ctx["skill_id"]),
            "competitorRef": "COMP-NO",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    nid = created.json()["nominationId"]

    missing = await client.post(
        f"/nominations/{nid}:reject",
        json={},
        headers=auth_headers,
    )
    assert missing.status_code == 422
    assert any(f["reason"] == "REASON_REQUIRED" for f in missing.json()["error"]["fields"])

    rejected = await client.post(
        f"/nominations/{nid}:reject",
        json={"reason": "Incomplete documentation"},
        headers=auth_headers,
    )
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["status"] == "REJECTED"
    assert body["reason"] == "Incomplete documentation"

    async with session_manager.session() as session:
        note = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "NOMINATION_REJECTED",
                    NotificationOutbox.recipient_role == "INSTITUTION",
                )
            )
        ).scalar_one_or_none()
        assert note is not None

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "NOMINATION_REJECT",
                    AuditEvent.entity_id == nid,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.reason == "Incomplete documentation"


@pytest.mark.asyncio
async def test_US_INS_01_concurrency_last_slot(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_nomination_context(session_manager, competition_id, limit=1)
    headers = await _inst_headers(client, session_manager, ctx["inst_user_id"])

    async def nominate(ref: str):
        return await client.post(
            f"/competitions/{competition_id}/nominations",
            json={
                "institutionId": str(ctx["institution_id"]),
                "skillId": str(ctx["skill_id"]),
                "competitorRef": ref,
            },
            headers=headers,
        )

    r1, r2 = await asyncio.gather(nominate("RACE-1"), nominate("RACE-2"))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [201, 409]
    loser = r1 if r1.status_code == 409 else r2
    assert loser.json()["error"]["code"] == "NOMINATION_LIMIT_REACHED"
