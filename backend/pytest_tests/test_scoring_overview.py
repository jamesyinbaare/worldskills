"""Admin scoring overview, multi-assessor resolve-total, release lock."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    CatalogSkill,
    CertificateTemplate,
    Competitor,
    ExpertAssignment,
    ExpertSkillArea,
    Family,
    Institution,
    MarkingScheme,
    Pathway,
    Region,
    ResultPublication,
    ResultsConfig,
    Score,
    Skill,
    Stage,
    Submission,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload

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


async def _seed(
    session_manager: DBManager,
    competition_id: uuid.UUID,
) -> dict:
    async with session_manager.session() as session:
        region = Region(name=f"Region-{uuid.uuid4().hex[:6]}")
        session.add(region)
        await session.flush()
        inst_comp = Institution(
            name=f"Score-Comp-{uuid.uuid4().hex[:6]}",
            region_id=region.id,
        )
        inst_exp = Institution(
            name=f"Score-Exp-{uuid.uuid4().hex[:6]}",
            region_id=region.id,
        )
        session.add_all([inst_comp, inst_exp])
        await session.flush()

        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(
            competition_id=competition_id, name="CIS Rubric", rubric=dict(RUBRIC)
        )
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

        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Module 1",
            order=1,
            quota=5,
            quota_by_zone={str(zone.id): 5},
        )
        session.add(stage)
        await session.flush()

        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            institution_id=inst_comp.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Ada",
            family_name="Competitor",
        )
        session.add(competitor)
        await session.flush()

        submission = Submission(
            competition_id=competition_id,
            competitor_id=competitor.id,
            stage_id=stage.id,
            state="ACCEPTED",
        )
        session.add(submission)

        expert_a = User(
            email=f"ex-a-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Expert A",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=inst_exp.id,
        )
        expert_b = User(
            email=f"ex-b-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Expert B",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=inst_exp.id,
        )
        chief = User(
            email=f"chief-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Chief Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.CHIEF_EXPERT,
            is_active=True,
            institution_id=inst_exp.id,
        )
        session.add_all([expert_a, expert_b, chief])
        await session.flush()

        for u in (expert_a, expert_b, chief):
            session.add(ExpertSkillArea(expert_id=u.id, catalog_skill_id=catalog.id))
            session.add(
                ExpertAssignment(
                    competition_id=competition_id,
                    expert_id=u.id,
                    skill_id=skill.id,
                    zone_id=zone.id,
                    coi_flags=[],
                )
            )

        session.add(
            ResultsConfig(
                competition_id=competition_id,
                release_at=datetime.utcnow() + timedelta(days=7),
                audience=["PUBLIC", "COMPETITOR"],
                neutral_status="IN_PROGRESS",
                award_by_rank={"1": "GOLD", "2": "SILVER"},
                default_outcome="FINALIST",
            )
        )
        for outcome, body in [
            ("GOLD", "Gold for {{name}}"),
            ("SILVER", "Silver for {{name}}"),
            ("FINALIST", "Finalist for {{name}}"),
            ("ADVANCE", "Advance for {{name}}"),
            ("WAITLIST", "Waitlist for {{name}}"),
        ]:
            session.add(
                CertificateTemplate(
                    competition_id=competition_id,
                    outcome=outcome,
                    language="en",
                    body=body,
                )
            )

        await session.commit()
        return {
            "skill_id": skill.id,
            "stage_id": stage.id,
            "submission_id": submission.id,
            "expert_a": expert_a,
            "expert_b": expert_b,
            "chief": chief,
        }


async def _login(client: AsyncClient, user: User) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": user.email, "password": "expert-pass-123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _score(
    client: AsyncClient,
    headers: dict[str, str],
    submission_id: uuid.UUID,
    accuracy: int,
    craft: int,
) -> None:
    resp = await client.put(
        f"/submissions/{submission_id}/scores",
        headers=headers,
        json={
            "finalize": True,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": accuracy},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": craft},
            ],
            "penalties": [],
        },
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_admin_scoring_overview_and_rbac(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    ha = await _login(client, ctx["expert_a"])
    hb = await _login(client, ctx["expert_b"])
    await _score(client, ha, ctx["submission_id"], 10, 6)
    await _score(client, hb, ctx["submission_id"], 14, 9)

    listed = await client.get(
        f"/competitions/{competition_id}/scoring",
        params={"skillId": str(ctx["skill_id"]), "stageId": str(ctx["stage_id"])},
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["assessorCount"] == 2
    assert rows[0]["disagreement"] is True
    totals = sorted(a["total"] for a in rows[0]["assessorTotals"])
    assert totals == [16, 23]

    detail = await client.get(
        f"/submissions/{ctx['submission_id']}/scoring",
        headers=auth_headers,
    )
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["criteria"]) == 2


@pytest.mark.asyncio
async def test_resolve_total_average_and_select(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    ha = await _login(client, ctx["expert_a"])
    hb = await _login(client, ctx["expert_b"])
    await _score(client, ha, ctx["submission_id"], 10, 6)  # 16
    await _score(client, hb, ctx["submission_id"], 14, 8)  # 22

    averaged = await client.post(
        f"/submissions/{ctx['submission_id']}/scoring:resolve-total",
        headers=auth_headers,
        json={"method": "AVERAGE"},
    )
    assert averaged.status_code == 200, averaged.text
    # criterion means: accuracy (10+14)/2=12, craft (6+8)/2=7 → 19
    assert averaged.json()["total"] == 19

    picked = await client.post(
        f"/submissions/{ctx['submission_id']}/scoring:resolve-total",
        headers=auth_headers,
        json={
            "method": "SELECT_ASSESSOR",
            "assessorId": str(ctx["expert_b"].id),
            "reason": "Expert B closer to brief",
        },
    )
    assert picked.status_code == 200, picked.text
    assert picked.json()["total"] == 22

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCORING_RESOLVE_TOTAL",
                    AuditEvent.entity_id == str(ctx["submission_id"]),
                )
            )
        ).scalars().all()
        assert len(audit) >= 2
        sub = await session.get(Submission, ctx["submission_id"])
        assert sub is not None
        assert sub.score_total == 22


@pytest.mark.asyncio
async def test_moderation_select_assessor_and_chief(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    ha = await _login(client, ctx["expert_a"])
    hb = await _login(client, ctx["expert_b"])
    await _score(client, ha, ctx["submission_id"], 10, 3)
    await _score(client, hb, ctx["submission_id"], 10, 9)

    chief_h = await _login(client, ctx["chief"])
    analysed = await client.post(
        f"/submissions/{ctx['submission_id']}/moderation:analyse",
        headers=chief_h,
    )
    assert analysed.status_code == 200, analysed.text

    applied = await client.post(
        f"/submissions/{ctx['submission_id']}/moderation",
        headers=chief_h,
        json={
            "criterionId": "c_craft",
            "method": "SELECT_ASSESSOR",
            "assessorId": str(ctx["expert_b"].id),
            "reason": "Prefer Expert B judgement",
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["standardisedValue"] == 9
    assert applied.json()["method"] == "SELECT_ASSESSOR"


@pytest.mark.asyncio
async def test_put_scores_blocked_when_results_released(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    ha = await _login(client, ctx["expert_a"])
    await _score(client, ha, ctx["submission_id"], 12, 8)

    async with session_manager.session() as session:
        session.add(
            ResultPublication(
                competition_id=competition_id,
                skill_id=ctx["skill_id"],
                stage_id=ctx["stage_id"],
                state="RELEASED",
                release_at=datetime.utcnow() - timedelta(hours=1),
                audience=["PUBLIC"],
                neutral_status="IN_PROGRESS",
                prepared_at=datetime.utcnow(),
                released_at=datetime.utcnow(),
            )
        )
        await session.commit()

    blocked = await client.put(
        f"/submissions/{ctx['submission_id']}/scores",
        headers=ha,
        json={
            "finalize": True,
            "criterionMarks": [
                {"criterionId": "c_accuracy", "type": "MEASUREMENT", "value": 15},
                {"criterionId": "c_craft", "type": "JUDGEMENT", "value": 10},
            ],
            "penalties": [],
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "RESULTS_RELEASED"
