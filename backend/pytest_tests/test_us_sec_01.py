"""US-SEC-01 — Assign experts with COI and segregation-of-duties enforcement."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    CatalogSkill,
    Competitor,
    ExpertSkillArea,
    Family,
    Institution,
    MarkingScheme,
    Pathway,
    Score,
    Skill,
    Submission,
    User,
    UserRole,
    Zone,
)
from app.services.assignments import assert_can_moderate, assert_can_score
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_skill_zone(
    session: AsyncSession, competition_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns skill_id, zone_id, catalog_skill_id."""
    family = Family(name=f"Family {uuid.uuid4().hex[:6]}", active=True)
    session.add(family)
    await session.flush()
    catalog = CatalogSkill(
        name=f"Web Dev {uuid.uuid4().hex[:6]}",
        family_id=family.id,
        active=True,
    )
    session.add(catalog)
    await session.flush()
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
    zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
    session.add_all([skill, zone])
    await session.flush()
    return skill.id, zone.id, catalog.id


async def _make_expert(
    session: AsyncSession,
    *,
    institution_id: uuid.UUID | None,
    label: str,
    catalog_skill_id: uuid.UUID | None = None,
) -> User:
    user = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"Expert {label}",
        hashed_password=get_password_hash("expert-pass-123"),
        role=UserRole.EXPERT,
        is_active=True,
        institution_id=institution_id,
    )
    session.add(user)
    await session.flush()
    if catalog_skill_id is not None:
        session.add(
            ExpertSkillArea(expert_id=user.id, catalog_skill_id=catalog_skill_id)
        )
        await session.flush()
    return user


@pytest.mark.asyncio
async def test_US_SEC_01_AC1_coi_at_assignment_and_queue_filter(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)

    async with session_manager.session() as session:
        inst_x = Institution(name=f"Inst X {uuid.uuid4().hex[:6]}")
        inst_y = Institution(name=f"Inst Y {uuid.uuid4().hex[:6]}")
        session.add_all([inst_x, inst_y])
        await session.flush()
        skill_id, zone_id, catalog_id = await _seed_skill_zone(session, competition_id)
        expert = await _make_expert(
            session, institution_id=inst_x.id, label="coi", catalog_skill_id=catalog_id
        )
        conflicted = Competitor(
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            institution_id=inst_x.id,
            ref_no="C-X-1",
        )
        safe = Competitor(
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            institution_id=inst_y.id,
            ref_no="C-Y-1",
        )
        session.add_all([conflicted, safe])
        await session.flush()
        sub_conflict = Submission(competition_id=competition_id, competitor_id=conflicted.id, state="ACCEPTED")
        sub_safe = Submission(competition_id=competition_id, competitor_id=safe.id, state="ACCEPTED")
        session.add_all([sub_conflict, sub_safe])
        await session.commit()
        expert_id = expert.id
        conflicted_id = conflicted.id
        safe_id = safe.id
        skill_id_r, zone_id_r = skill_id, zone_id
        sub_safe_id = sub_safe.id

    resp = await client.post(
        f"/competitions/{competition_id}/assignments",
        json={"expertId": str(expert_id), "skillId": str(skill_id_r), "zoneId": str(zone_id_r)},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["coiFlags"]) >= 1
    flag = body["coiFlags"][0]
    assert flag["reason"] == "SAME_INSTITUTION"
    assert str(conflicted_id) in [str(c) for c in flag["competitorIds"]]

    queue = await client.get(
        f"/competitions/{competition_id}/assessors/{expert_id}/queue",
        headers=auth_headers,
    )
    assert queue.status_code == 200, queue.text
    submissions = queue.json()["submissions"]
    competitor_ids = {s["competitorId"] for s in submissions}
    assert str(safe_id) in competitor_ids
    assert str(conflicted_id) not in competitor_ids
    assert any(s["submissionId"] == str(sub_safe_id) for s in submissions)


@pytest.mark.asyncio
async def test_US_SEC_01_AC1_invalid_assignment(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    async with session_manager.session() as session:
        skill_id, zone_id, _catalog_id = await _seed_skill_zone(session, competition_id)
        inactive = await _make_expert(session, institution_id=None, label="inactive")
        inactive.is_active = False
        await session.commit()
        inactive_id = inactive.id

    resp = await client.post(
        f"/competitions/{competition_id}/assignments",
        json={
            "expertId": str(inactive_id),
            "skillId": str(skill_id),
            "zoneId": str(zone_id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_ASSIGNMENT"


@pytest.mark.asyncio
async def test_US_SEC_01_AC2_coi_blocks_scoring(
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        inst = Institution(name=f"Inst COI {uuid.uuid4().hex[:6]}")
        session.add(inst)
        await session.flush()
        # Minimal cycle row via Institution alone is not enough — use bare IDs for helper
        from app.models import Competition, CompetitionStatus
        from datetime import date, timedelta

        cycle = Competition(
            name=f"COI Competition {uuid.uuid4().hex[:4]}",
            period_start=date.today(),
            period_end=date.today() + timedelta(days=30),
            time_zone="Africa/Accra",
            status=CompetitionStatus.DRAFT,
            languages=["en"],
        )
        session.add(cycle)
        await session.flush()
        skill_id, zone_id, catalog_id = await _seed_skill_zone(session, cycle.id)
        expert = await _make_expert(
            session, institution_id=inst.id, label="scorer", catalog_skill_id=catalog_id
        )
        competitor = Competitor(
            competition_id=cycle.id,
            skill_id=skill_id,
            zone_id=zone_id,
            institution_id=inst.id,
            ref_no="C-1",
        )
        session.add(competitor)
        await session.flush()
        sub = Submission(competition_id=cycle.id, competitor_id=competitor.id)
        session.add(sub)
        await session.commit()
        competition_id, expert_id, competitor_id, sub_id = cycle.id, expert.id, competitor.id, sub.id

    async with session_manager.session() as session:
        expert = await session.get(User, expert_id)
        competitor = await session.get(Competitor, competitor_id)
        assert expert is not None and competitor is not None
        with pytest.raises(AppError) as exc_info:
            await assert_can_score(
                session,
                competition_id=competition_id,
                expert=expert,
                competitor=competitor,
                submission_id=sub_id,
            )
        assert exc_info.value.code == "CONFLICT_OF_INTEREST"

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCORE_REFUSED_COI",
                    AuditEvent.entity_id == str(sub_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_SEC_01_AC3_segregation_of_duties(
    session_manager: DBManager,
) -> None:
    async with session_manager.session() as session:
        from datetime import date, timedelta

        from app.models import Competition, CompetitionStatus

        cycle = Competition(
            name=f"SoD Competition {uuid.uuid4().hex[:4]}",
            period_start=date.today(),
            period_end=date.today() + timedelta(days=30),
            time_zone="Africa/Accra",
            status=CompetitionStatus.DRAFT,
            languages=["en"],
        )
        session.add(cycle)
        await session.flush()
        skill_id, zone_id, catalog_id = await _seed_skill_zone(session, cycle.id)
        expert = await _make_expert(
            session, institution_id=None, label="sod", catalog_skill_id=catalog_id
        )
        competitor = Competitor(
            competition_id=cycle.id,
            skill_id=skill_id,
            zone_id=zone_id,
            institution_id=None,
            ref_no="C-SOD",
        )
        session.add(competitor)
        await session.flush()
        sub = Submission(competition_id=cycle.id, competitor_id=competitor.id)
        session.add(sub)
        await session.flush()
        score = Score(submission_id=sub.id, assessor_id=expert.id, raw=80)
        session.add(score)
        await session.commit()
        competition_id, expert_id, score_id = cycle.id, expert.id, score.id

    async with session_manager.session() as session:
        expert = await session.get(User, expert_id)
        score = await session.get(Score, score_id)
        assert expert is not None and score is not None
        with pytest.raises(AppError) as exc_info:
            await assert_can_moderate(
                session,
                competition_id=competition_id,
                score=score,
                moderator=expert,
            )
        assert exc_info.value.code == "SEGREGATION_VIOLATION"

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "MODERATE_REFUSED_SOD",
                    AuditEvent.entity_id == str(score_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_SEC_01_AC4_reassignment_audited_and_coi_rechecked(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)

    async with session_manager.session() as session:
        inst_a = Institution(name=f"Inst A {uuid.uuid4().hex[:6]}")
        inst_b = Institution(name=f"Inst B {uuid.uuid4().hex[:6]}")
        session.add_all([inst_a, inst_b])
        await session.flush()
        skill_id, zone_id, catalog_id = await _seed_skill_zone(session, competition_id)
        expert_a = await _make_expert(
            session, institution_id=inst_a.id, label="a", catalog_skill_id=catalog_id
        )
        expert_b = await _make_expert(
            session, institution_id=inst_b.id, label="b", catalog_skill_id=catalog_id
        )
        conflicted_for_b = Competitor(
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_id,
            institution_id=inst_b.id,
            ref_no="C-B-1",
        )
        session.add(conflicted_for_b)
        await session.commit()
        expert_a_id, expert_b_id = expert_a.id, expert_b.id
        skill_id_r, zone_id_r = skill_id, zone_id
        conflicted_b_id = conflicted_for_b.id

    create = await client.post(
        f"/competitions/{competition_id}/assignments",
        json={"expertId": str(expert_a_id), "skillId": str(skill_id_r), "zoneId": str(zone_id_r)},
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    assignment_id = create.json()["assignmentId"]

    delegated = await client.post(
        f"/competitions/{competition_id}/assignments/{assignment_id}:delegate",
        json={"expertId": str(expert_b_id)},
        headers=auth_headers,
    )
    assert delegated.status_code == 201, delegated.text
    body = delegated.json()
    assert body["expertId"] == str(expert_b_id)
    assert any(
        str(conflicted_b_id) in [str(c) for c in f["competitorIds"]] for f in body["coiFlags"]
    )

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ASSIGNMENT_DELEGATE",
                    AuditEvent.entity_id == assignment_id,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.before is not None
        assert audit.after is not None
