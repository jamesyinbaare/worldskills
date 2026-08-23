"""US-ASM-01 — Expert scores a submission against a rubric (blind, COI-safe)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    CatalogSkill,
    Competitor,
    ExpertAssignment,
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
from pytest_tests.conftest import competition_payload

# Worked example fixture (DoD): measurement 12/15 + judgement 8/10 − penalty 2 = 18
WORKED_TOTAL = 18

RUBRIC = {
    "blindMode": True,
    "criteria": [
        {"id": "c_accuracy", "name": "Accuracy", "type": "MEASUREMENT", "max": 15},
        {"id": "c_craft", "name": "Craft", "type": "JUDGEMENT", "max": 10},
    ],
    "penalties": [
        {"code": "MINOR_NON_COMPLIANCE", "deduction": 2, "cap": 5},
    ],
}


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_scoring_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    blind: bool = True,
    expert_same_institution: bool = False,
) -> dict:
    """Seed scheme/skill/zone/institutions/competitor/submission/experts. Returns context ids."""
    async with session_manager.session() as session:
        inst_a = Institution(name=f"Inst-A-{uuid.uuid4().hex[:6]}")
        inst_b = Institution(name=f"Inst-B-{uuid.uuid4().hex[:6]}")
        session.add_all([inst_a, inst_b])
        await session.flush()

        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        rubric = dict(RUBRIC)
        rubric["blindMode"] = blind
        scheme = MarkingScheme(competition_id=competition_id, name="CIS Rubric", rubric=rubric)
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()

        family = Family(name=f"Family-{uuid.uuid4().hex[:6]}", active=True)
        session.add(family)
        await session.flush()
        catalog = CatalogSkill(
            name=f"Web Dev {uuid.uuid4().hex[:6]}",
            family_id=family.id,
            active=True,
        )
        session.add(catalog)
        await session.flush()

        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            catalog_skill_id=catalog.id,
            family_id=str(family.id),
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=20,
            active=True,
        )
        session.add(skill)
        await session.flush()

        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            institution_id=inst_a.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Secret",
            family_name="Identity",
            photo_key="photos/secret.jpg",
        )
        session.add(competitor)
        await session.flush()

        submission = Submission(
            competition_id=competition_id,
            competitor_id=competitor.id,
            state="ACCEPTED",
        )
        session.add(submission)

        expert = User(
            email=f"expert-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Scoring Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=inst_a.id if expert_same_institution else inst_b.id,
        )
        judge2 = User(
            email=f"judge2-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Judge Two",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=inst_b.id,
        )
        judge3 = User(
            email=f"judge3-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Judge Three",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=inst_b.id,
        )
        session.add_all([expert, judge2, judge3])
        await session.flush()

        for u in (expert, judge2, judge3):
            session.add(
                ExpertSkillArea(expert_id=u.id, catalog_skill_id=catalog.id)
            )
            session.add(
                ExpertAssignment(
                    competition_id=competition_id,
                    expert_id=u.id,
                    skill_id=skill.id,
                    zone_id=zone.id,
                    coi_flags=[],
                )
            )

        await session.commit()
        return {
            "scheme_id": scheme.id,
            "skill_id": skill.id,
            "zone_id": zone.id,
            "competitor_id": competitor.id,
            "submission_id": submission.id,
            "expert": expert,
            "judge2": judge2,
            "judge3": judge3,
            "inst_a": inst_a.id,
            "inst_b": inst_b.id,
        }


async def _login(client: AsyncClient, user: User, password: str = "expert-pass-123") -> dict[str, str]:
    resp = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_ASM_01_AC1_score_entry(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    headers = await _login(client, ctx["expert"])
    sub_id = ctx["submission_id"]

    resp = await client.put(
        f"/submissions/{sub_id}/scores",
        headers=headers,
        json={
            "finalize": True,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 12, "comment": "solid"},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": 8},
            ],
            "penalties": [],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 20  # 12+8 without penalty
    assert body["status"] == "FINAL"

    async with session_manager.session() as session:
        scores = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == sub_id,
                    Score.assessor_id == ctx["expert"].id,
                )
            )
        ).scalars().all()
        assert len(scores) == 2
        assert all(s.assessor_id == ctx["expert"].id for s in scores)
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCORE_SAVE",
                    AuditEvent.entity_id == str(sub_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        sub = await session.get(Submission, sub_id)
        assert sub is not None
        assert sub.score_total == 20


@pytest.mark.asyncio
async def test_US_ASM_01_AC2_blind_mode(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=True)
    headers = await _login(client, ctx["expert"])

    queue = await client.get(
        f"/assessors/{ctx['expert'].id}/queue",
        params={"competitionId": str(competition_id)},
        headers=headers,
    )
    assert queue.status_code == 200, queue.text
    items = queue.json()["items"]
    assert len(items) >= 1
    item = next(i for i in items if i["submissionId"] == str(ctx["submission_id"]))
    assert item["anonCode"]
    assert item.get("competitorId") in (None, "")

    view = await client.get(
        f"/submissions/{ctx['submission_id']}/assessment",
        headers=headers,
    )
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["blindMode"] is True
    assert body["anonCode"]
    assert body["competitorId"] is None
    assert body["givenNames"] is None
    assert body["familyName"] is None
    assert body["institutionId"] is None
    assert body["photoKey"] is None


@pytest.mark.asyncio
async def test_US_ASM_01_AC3_coi_block(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(
        session_manager, competition_id, blind=False, expert_same_institution=True
    )
    headers = await _login(client, ctx["expert"])

    resp = await client.put(
        f"/submissions/{ctx['submission_id']}/scores",
        headers=headers,
        json={
            "finalize": True,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 10},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": 5},
            ],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT_OF_INTEREST"

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCORE_REFUSED_COI",
                    AuditEvent.entity_id == str(ctx["submission_id"]),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        scores = (
            await session.execute(select(Score).where(Score.submission_id == ctx["submission_id"]))
        ).scalars().all()
        assert scores == []


@pytest.mark.asyncio
async def test_US_ASM_01_AC4_out_of_range_mark(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    headers = await _login(client, ctx["expert"])

    resp = await client.put(
        f"/submissions/{ctx['submission_id']}/scores",
        headers=headers,
        json={
            "finalize": False,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 18},
            ],
        },
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "MARK_OUT_OF_RANGE"
    assert any(f["reason"] == "MARK_OUT_OF_RANGE" for f in err["fields"])

    async with session_manager.session() as session:
        scores = (
            await session.execute(select(Score).where(Score.submission_id == ctx["submission_id"]))
        ).scalars().all()
        assert scores == []


@pytest.mark.asyncio
async def test_US_ASM_01_AC5_judgement_marks_per_judge(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    sub_id = ctx["submission_id"]

    for judge, value in (
        (ctx["expert"], 7),
        (ctx["judge2"], 8),
        (ctx["judge3"], 9),
    ):
        headers = await _login(client, judge)
        resp = await client.put(
            f"/submissions/{sub_id}/scores",
            headers=headers,
            json={
                "finalize": False,
                "criterionMarks": [
                    {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 10},
                    {
                        "criterionId": "c_craft",
                        "type": "JUDGEMENT",
                        "value": value,
                        "judgeId": str(judge.id),
                    },
                ],
            },
        )
        assert resp.status_code == 200, resp.text

    async with session_manager.session() as session:
        judgements = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == sub_id,
                    Score.criterion_id == "c_craft",
                    Score.score_type == "JUDGEMENT",
                )
            )
        ).scalars().all()
        assert len(judgements) == 3
        assert {j.raw for j in judgements} == {7, 8, 9}
        assert {j.assessor_id for j in judgements} == {
            ctx["expert"].id,
            ctx["judge2"].id,
            ctx["judge3"].id,
        }


@pytest.mark.asyncio
async def test_US_ASM_01_AC6_penalty_applied(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    headers = await _login(client, ctx["expert"])
    sub_id = ctx["submission_id"]

    resp = await client.put(
        f"/submissions/{sub_id}/scores",
        headers=headers,
        json={
            "finalize": True,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 12},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": 8},
            ],
            "penalties": [{"code": "MINOR_NON_COMPLIANCE"}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == WORKED_TOTAL
    assert any(p["code"] == "MINOR_NON_COMPLIANCE" and p["deduction"] == 2 for p in body["breakdown"]["penalties"])
    assert body["breakdown"]["total"] == WORKED_TOTAL

    # Cap exceeded
    over = await client.put(
        f"/submissions/{sub_id}/scores",
        headers=headers,
        json={
            "finalize": False,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 12},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": 8},
            ],
            "penalties": [{"code": "MINOR_NON_COMPLIANCE", "deduction": 9}],
        },
    )
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "PENALTY_EXCEEDS_CAP"
