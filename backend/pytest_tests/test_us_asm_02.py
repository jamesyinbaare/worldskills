"""US-ASM-02 — Moderate and standardise judgement marks."""

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
    Competitor,
    ExpertAssignment,
    Institution,
    MarkingScheme,
    ModerationFlag,
    Pathway,
    Region,
    Score,
    Skill,
    Submission,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload

# Fixtures: measurement 10; judgement raws 3,8,9 (spread 6 > tol 2);
# STANDARDISE MEAN → 7; total = 10 + 7 = 17
EXPECTED_STANDARDISED = 7
EXPECTED_TOTAL_AFTER = 17

RUBRIC = {
    "blindMode": False,
    "criteria": [
        {"id": "c_accuracy", "name": "Accuracy", "type": "MEASUREMENT", "max": 15},
        {"id": "c_craft", "name": "Craft", "type": "JUDGEMENT", "max": 10},
    ],
    "penalties": [],
    "moderation": {"judgementSpreadTolerance": 2, "standardiseMethod": "MEAN"},
}


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_moderation_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    judgement_values: list[int] | None = None,
) -> dict:
    values = judgement_values if judgement_values is not None else [3, 8, 9]
    async with session_manager.session() as session:
        region = Region(name=f"Mod-Region-{uuid.uuid4().hex[:6]}")
        session.add(region)
        await session.flush()
        inst = Institution(
            name=f"Mod-Inst-{uuid.uuid4().hex[:6]}",
            region_id=region.id,
        )
        session.add(inst)
        await session.flush()

        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS Rubric", rubric=dict(RUBRIC))
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

        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            institution_id=inst.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Comp",
            family_name="Etitor",
        )
        session.add(competitor)
        await session.flush()

        submission = Submission(
            competition_id=competition_id,
            competitor_id=competitor.id,
            state="ACCEPTED",
            score_total=None,
        )
        session.add(submission)
        await session.flush()

        experts: list[User] = []
        for i, jval in enumerate(values):
            expert = User(
                email=f"judge{i}-{uuid.uuid4().hex[:6]}@example.com",
                full_name=f"Judge {i}",
                hashed_password=get_password_hash("expert-pass-123"),
                role=UserRole.EXPERT,
                is_active=True,
                institution_id=None,
            )
            session.add(expert)
            await session.flush()
            session.add(
                ExpertAssignment(
                    competition_id=competition_id,
                    expert_id=expert.id,
                    skill_id=skill.id,
                    zone_id=zone.id,
                    coi_flags=[],
                )
            )
            session.add(
                Score(
                    submission_id=submission.id,
                    assessor_id=expert.id,
                    criterion_id="c_accuracy",
                    score_type="MEASUREMENT",
                    raw=10,
                    status="FINAL",
                )
            )
            session.add(
                Score(
                    submission_id=submission.id,
                    assessor_id=expert.id,
                    criterion_id="c_craft",
                    score_type="JUDGEMENT",
                    raw=jval,
                    judge_id=expert.id,
                    status="FINAL",
                )
            )
            experts.append(expert)

        moderator = User(
            email=f"mod-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Independent Mod",
            hashed_password=get_password_hash("mod-pass-123"),
            role=UserRole.MODERATOR,
            is_active=True,
        )
        session.add(moderator)
        await session.commit()

        return {
            "submission_id": submission.id,
            "experts": experts,
            "moderator": moderator,
            "scheme_id": scheme.id,
            "judgement_values": values,
        }


async def _login(client: AsyncClient, user: User, password: str) -> dict[str, str]:
    resp = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_ASM_02_AC1_spread_flagged(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_moderation_world(session_manager, competition_id)
    headers = await _login(client, ctx["moderator"], "mod-pass-123")

    resp = await client.post(
        f"/submissions/{ctx['submission_id']}/moderation:analyse",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tolerance"] == 2
    craft = next(f for f in body["flags"] if f["criterionId"] == "c_craft")
    assert craft["flagged"] is True
    assert craft["spread"] == 6
    assert sorted(craft["rawMarks"]) == [3, 8, 9]
    assert craft["state"] == "OPEN"

    async with session_manager.session() as session:
        flag = (
            await session.execute(
                select(ModerationFlag).where(
                    ModerationFlag.submission_id == ctx["submission_id"],
                    ModerationFlag.criterion_id == "c_craft",
                )
            )
        ).scalar_one()
        assert flag.flagged is True


@pytest.mark.asyncio
async def test_US_ASM_02_AC2_standardise(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_moderation_world(session_manager, competition_id)
    headers = await _login(client, ctx["moderator"], "mod-pass-123")
    sub_id = ctx["submission_id"]

    await client.post(f"/submissions/{sub_id}/moderation:analyse", headers=headers)

    resp = await client.post(
        f"/submissions/{sub_id}/moderation",
        headers=headers,
        json={"criterionId": "c_craft", "method": "STANDARDISE"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["standardisedValue"] == EXPECTED_STANDARDISED
    assert body["total"] == EXPECTED_TOTAL_AFTER
    assert sorted(body["rawMarks"]) == [3, 8, 9]

    async with session_manager.session() as session:
        rows = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == sub_id,
                    Score.criterion_id == "c_craft",
                    Score.score_type == "JUDGEMENT",
                )
            )
        ).scalars().all()
        assert len(rows) == 3
        for row in rows:
            assert row.raw in {3, 8, 9}  # raw preserved
            assert row.standardised == EXPECTED_STANDARDISED
        sub = await session.get(Submission, sub_id)
        assert sub is not None
        assert sub.score_total == EXPECTED_TOTAL_AFTER


@pytest.mark.asyncio
async def test_US_ASM_02_AC3_manual_adjust_requires_reason(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_moderation_world(session_manager, competition_id)
    headers = await _login(client, ctx["moderator"], "mod-pass-123")
    sub_id = ctx["submission_id"]

    missing = await client.post(
        f"/submissions/{sub_id}/moderation",
        headers=headers,
        json={"criterionId": "c_craft", "method": "MANUAL", "value": 6},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "REASON_REQUIRED"

    ok = await client.post(
        f"/submissions/{sub_id}/moderation",
        headers=headers,
        json={
            "criterionId": "c_craft",
            "method": "MANUAL",
            "value": 6,
            "reason": "Consensus after review",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["standardisedValue"] == 6
    assert ok.json()["total"] == 16  # 10 + 6

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "MODERATION_APPLY",
                    AuditEvent.entity_id == str(sub_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.reason == "Consensus after review"
        rows = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == sub_id,
                    Score.criterion_id == "c_craft",
                )
            )
        ).scalars().all()
        assert {r.raw for r in rows} == {3, 8, 9}
        assert all(r.standardised == 6 for r in rows)


@pytest.mark.asyncio
async def test_US_ASM_02_AC4_segregation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_moderation_world(session_manager, competition_id)
    # Promote first expert to also hold moderator capability via CHIEF_EXPERT
    async with session_manager.session() as session:
        scorer = await session.get(User, ctx["experts"][0].id)
        assert scorer is not None
        scorer.role = UserRole.CHIEF_EXPERT
        await session.commit()
        scorer_email = scorer.email

    login = await client.post(
        "/auth/login",
        json={"email": scorer_email, "password": "expert-pass-123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    analyse = await client.post(
        f"/submissions/{ctx['submission_id']}/moderation:analyse",
        headers=headers,
    )
    assert analyse.status_code == 409
    assert analyse.json()["error"]["code"] == "SEGREGATION_VIOLATION"

    apply = await client.post(
        f"/submissions/{ctx['submission_id']}/moderation",
        headers=headers,
        json={"criterionId": "c_craft", "method": "STANDARDISE"},
    )
    assert apply.status_code == 409
    assert apply.json()["error"]["code"] == "SEGREGATION_VIOLATION"

    async with session_manager.session() as session:
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "MODERATE_REFUSED_SOD",
                    AuditEvent.entity_id == str(ctx["submission_id"]),
                )
            )
        ).scalars().all()
        assert len(audits) >= 1
