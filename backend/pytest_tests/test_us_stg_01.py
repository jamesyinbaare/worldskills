"""US-STG-01 — Configure a branching stage pathway with quotas and thresholds."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    CompetitionStatus,
    Competitor,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    Submission,
    User,
    Zone,
)
from app.services.pathway_engine import (
    Candidate,
    StageNode,
    apply_quota_threshold,
    compute_finalists_per_skill,
    resolve_next_stage,
)
from pytest_tests.conftest import competition_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_skill_scheme_zones(
    session_manager: DBManager, competition_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns skill_id, scheme_id, zone_a_id, zone_b_id."""
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone_a = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        zone_b = Zone(competition_id=competition_id, name="Ashanti", active=True)
        session.add_all([age, path, scheme, zone_a, zone_b])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=40,
            active=True,
            family_id="it",
        )
        session.add(skill)
        await session.commit()
        return skill.id, scheme.id, zone_a.id, zone_b.id


def _opens_closes() -> tuple[str, str]:
    now = datetime.utcnow()
    return (
        (now + timedelta(days=1)).isoformat() + "Z",
        (now + timedelta(days=30)).isoformat() + "Z",
    )


def _pathway_payload(
    scheme_id: uuid.UUID,
    zone_a: uuid.UUID,
    zone_b: uuid.UUID,
    *,
    with_branch: bool = False,
    controlled_change_reason: str | None = None,
) -> dict:
    opens, closes = _opens_closes()
    za, zb = str(zone_a), str(zone_b)
    stages: list[dict] = [
        {
            "order": 1,
            "type": "VIRTUAL",
            "schemeId": str(scheme_id),
            "opensAt": opens,
            "closesAt": closes,
            "quotaByZone": {za: 10, zb: 10},
            "minScore": 40,
        },
        {
            "order": 2,
            "type": "VIRTUAL",
            "schemeId": str(scheme_id),
            "opensAt": opens,
            "closesAt": closes,
            "quotaByZone": {za: 5, zb: 5},
            "minScore": 50,
        },
    ]
    if with_branch:
        stages[1]["branch"] = {
            "default": 3,
            "byFamily": {"practical_trades": 4},
        }
        stages.append(
            {
                "order": 3,
                "type": "VIRTUAL",
                "schemeId": str(scheme_id),
                "opensAt": opens,
                "closesAt": closes,
                "quotaByZone": {za: 2, zb: 2},
                "minScore": 60,
            }
        )
        stages.append(
            {
                "order": 4,
                "type": "PHYSICAL",
                "schemeId": str(scheme_id),
                "opensAt": opens,
                "closesAt": closes,
                "quotaByZone": {za: 3, zb: 3},
                "minScore": 55,
            }
        )
    else:
        stages.append(
            {
                "order": 3,
                "type": "VIRTUAL",
                "schemeId": str(scheme_id),
                "opensAt": opens,
                "closesAt": closes,
                "quotaByZone": {za: 2, zb: 2},
                "minScore": 60,
            }
        )
    body: dict = {"stages": stages}
    if controlled_change_reason is not None:
        body["controlledChangeReason"] = controlled_change_reason
    return body


@pytest.mark.asyncio
async def test_US_STG_01_AC1_ordered_pathway(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(session_manager, competition_id)
    payload = _pathway_payload(scheme_id, zone_a, zone_b)

    resp = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "stages" in body
    orders = [s["order"] for s in body["stages"]]
    assert orders == [1, 2, 3]

    async with session_manager.session() as session:
        rows = (
            await session.execute(
                select(Stage).where(Stage.skill_id == skill_id).order_by(Stage.order)
            )
        ).scalars().all()
        assert [r.order for r in rows] == [1, 2, 3]
        assert len({r.order for r in rows}) == 3

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "PATHWAY_UPDATE",
                    AuditEvent.entity_id == str(skill_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None

    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200
    denied = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_US_STG_01_AC2_branching() -> None:
    stages = [
        StageNode(order=1, stage_type="PROJECT", branch=None, quota_by_zone={}, min_score=None),
        StageNode(
            order=2,
            stage_type="PROJECT",
            branch={"default": 3, "byFamily": {"practical_trades": 4}},
            quota_by_zone={},
            min_score=None,
        ),
        StageNode(order=3, stage_type="PROJECT", branch=None, quota_by_zone={}, min_score=None),
        StageNode(order=4, stage_type="PHYSICAL", branch=None, quota_by_zone={}, min_score=None),
    ]
    next_it = resolve_next_stage(stages, current_order=2, family_id="it")
    assert next_it.order == 3
    next_practical = resolve_next_stage(stages, current_order=2, family_id="practical_trades")
    assert next_practical.order == 4


@pytest.mark.asyncio
async def test_US_STG_01_AC3_quota_and_threshold() -> None:
    zone_a = str(uuid.uuid4())
    zone_b = str(uuid.uuid4())
    candidates = [
        Candidate(competitor_id="c1", zone_id=zone_a, score=90),
        Candidate(competitor_id="c2", zone_id=zone_a, score=80),
        Candidate(competitor_id="c3", zone_id=zone_a, score=70),
        Candidate(competitor_id="c4", zone_id=zone_a, score=45),  # below min
        Candidate(competitor_id="c5", zone_id=zone_b, score=95),
        Candidate(competitor_id="c6", zone_id=zone_b, score=60),
        Candidate(competitor_id="c7", zone_id=zone_b, score=55),
    ]
    advanced = apply_quota_threshold(
        candidates,
        quota_by_zone={zone_a: 2, zone_b: 2},
        min_score=50,
    )
    ids = {c.competitor_id for c in advanced}
    assert ids == {"c1", "c2", "c5", "c6"}
    assert "c4" not in ids  # below threshold
    assert "c3" not in ids  # outside top-N
    assert "c7" not in ids  # outside top-N after threshold filter


@pytest.mark.asyncio
async def test_US_STG_01_AC4_finalist_computation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(session_manager, competition_id)
    payload = _pathway_payload(scheme_id, zone_a, zone_b)

    resp = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Terminal stage quota 2+2 = 4
    assert body["finalistsPerSkill"] == 4

    # Engine agreement on same graph
    nodes = [
        StageNode(
            order=s["order"],
            stage_type=s["type"],
            branch=s.get("branch"),
            quota_by_zone=s["quotaByZone"],
            min_score=s.get("minScore"),
        )
        for s in payload["stages"]
    ]
    assert compute_finalists_per_skill(nodes) == 4


@pytest.mark.asyncio
async def test_US_STG_01_AC5_reorder_while_active(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(session_manager, competition_id)
    payload = _pathway_payload(scheme_id, zone_a, zone_b)
    first = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text

    async with session_manager.session() as session:
        from app.models import Competition

        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        await session.commit()

    # ACTIVE edits no longer require controlledChangeReason
    without_reason = _pathway_payload(scheme_id, zone_a, zone_b)
    without_reason["stages"][2]["type"] = "PHYSICAL"
    ok = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=without_reason,
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert any(s["type"] == "PHYSICAL" for s in ok.json()["stages"])

    # Optional reason still recorded when provided
    with_reason = _pathway_payload(
        scheme_id, zone_a, zone_b, controlled_change_reason="Add national fine-tune"
    )
    with_reason["stages"][2]["type"] = "VIRTUAL"
    ok2 = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=with_reason,
        headers=auth_headers,
    )
    assert ok2.status_code == 200, ok2.text

    async with session_manager.session() as session:
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "PATHWAY_UPDATE",
                    AuditEvent.entity_id == str(skill_id),
                    AuditEvent.reason == "Add national fine-tune",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None

        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.LOCKED
        await session.commit()

    # LOCKED status also allows pathway edits
    locked_ok = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=_pathway_payload(scheme_id, zone_a, zone_b),
        headers=auth_headers,
    )
    assert locked_ok.status_code == 200, locked_ok.text


@pytest.mark.asyncio
async def test_US_STG_01_validation_failures(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(session_manager, competition_id)
    opens, closes = _opens_closes()
    za, zb = str(zone_a), str(zone_b)
    base_stage = {
        "type": "VIRTUAL",
        "schemeId": str(scheme_id),
        "opensAt": opens,
        "closesAt": closes,
        "quotaByZone": {za: 5, zb: 5},
    }

    # Non-contiguous order
    bad_order = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json={
            "stages": [
                {**base_stage, "order": 1},
                {**base_stage, "order": 3},
            ]
        },
        headers=auth_headers,
    )
    assert bad_order.status_code == 422
    err = bad_order.json()["error"]
    assert err["code"] == "ORDER_INVALID" or any(
        f["reason"] == "ORDER_INVALID" for f in err["fields"]
    )

    # Negative quota
    bad_quota = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json={
            "stages": [
                {**base_stage, "order": 1, "quotaByZone": {za: -1, zb: 5}},
            ]
        },
        headers=auth_headers,
    )
    assert bad_quota.status_code == 422
    assert bad_quota.json()["error"]["code"] == "QUOTA_INVALID" or any(
        f["reason"] == "QUOTA_INVALID" for f in bad_quota.json()["error"]["fields"]
    )

    # minScore out of range
    bad_score = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json={
            "stages": [
                {**base_stage, "order": 1, "minScore": 101},
            ]
        },
        headers=auth_headers,
    )
    assert bad_score.status_code == 422
    assert bad_score.json()["error"]["code"] == "SCORE_RANGE" or any(
        f["reason"] == "SCORE_RANGE" for f in bad_score.json()["error"]["fields"]
    )

    # Branch target missing
    bad_branch = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json={
            "stages": [
                {
                    **base_stage,
                    "order": 1,
                    "branch": {"default": 99},
                },
                {**base_stage, "order": 2},
            ]
        },
        headers=auth_headers,
    )
    assert bad_branch.status_code == 422
    assert bad_branch.json()["error"]["code"] == "BRANCH_TARGET_MISSING" or any(
        f["reason"] == "BRANCH_TARGET_MISSING" for f in bad_branch.json()["error"]["fields"]
    )

    # closesAt before opensAt
    bad_window = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json={
            "stages": [
                {
                    **base_stage,
                    "order": 1,
                    "opensAt": closes,
                    "closesAt": opens,
                },
            ]
        },
        headers=auth_headers,
    )
    assert bad_window.status_code == 422
    assert bad_window.json()["error"]["code"] == "BEFORE_OPENS" or any(
        f["reason"] == "BEFORE_OPENS" for f in bad_window.json()["error"]["fields"]
    )


@pytest.mark.asyncio
async def test_US_STG_01_pathway_engine_boundary_and_branch_finalists() -> None:
    """Story DoD: pathway engine unit-tested for both branch types and boundary quotas."""
    zone_a = str(uuid.uuid4())
    # Quota exceeds available → advance all available
    candidates = [
        Candidate(competitor_id="a", zone_id=zone_a, score=90),
        Candidate(competitor_id="b", zone_id=zone_a, score=80),
    ]
    advanced = apply_quota_threshold(
        candidates, quota_by_zone={zone_a: 10}, min_score=None
    )
    assert {c.competitor_id for c in advanced} == {"a", "b"}

    za, zb = str(uuid.uuid4()), str(uuid.uuid4())
    branched = [
        StageNode(
            order=1,
            stage_type="PROJECT",
            branch={"default": 2, "byFamily": {"practical_trades": 3}},
            quota_by_zone={za: 10, zb: 10},
            min_score=None,
        ),
        StageNode(
            order=2,
            stage_type="PROJECT",
            branch=None,
            quota_by_zone={za: 2, zb: 2},
            min_score=None,
        ),
        StageNode(
            order=3,
            stage_type="PHYSICAL",
            branch=None,
            quota_by_zone={za: 3, zb: 3},
            min_score=None,
        ),
    ]
    # Both leaf stages contribute: (2+2) + (3+3) = 10
    assert compute_finalists_per_skill(branched) == 10


@pytest.mark.asyncio
async def test_pathway_update_preserves_stage_ids(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Re-saving a pathway must upsert by order — not delete/recreate stages."""
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(
        session_manager, competition_id
    )
    payload = _pathway_payload(scheme_id, zone_a, zone_b)

    first = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    ids_before = {s["order"]: s["stageId"] for s in first.json()["stages"]}

    payload["stages"][0]["minScore"] = 55
    second = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert second.status_code == 200, second.text
    ids_after = {s["order"]: s["stageId"] for s in second.json()["stages"]}
    assert ids_before == ids_after
    assert second.json()["stages"][0]["minScore"] == 55


@pytest.mark.asyncio
async def test_pathway_cannot_remove_stage_with_submissions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    skill_id, scheme_id, zone_a, zone_b = await _seed_skill_scheme_zones(
        session_manager, competition_id
    )
    payload = _pathway_payload(scheme_id, zone_a, zone_b)
    created = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=payload,
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    stage_3_id = uuid.UUID(
        next(s["stageId"] for s in created.json()["stages"] if s["order"] == 3)
    )

    async with session_manager.session() as session:
        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill_id,
            zone_id=zone_a,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Path",
            family_name="Lock",
        )
        session.add(competitor)
        await session.flush()
        session.add(
            Submission(
                competition_id=competition_id,
                competitor_id=competitor.id,
                stage_id=stage_3_id,
                state="ACCEPTED",
            )
        )
        await session.commit()

    # Drop stage 3 from pathway
    reduced = _pathway_payload(scheme_id, zone_a, zone_b)
    reduced["stages"] = [s for s in reduced["stages"] if s["order"] != 3]
    # Fix contiguous orders for remaining (orders 1,2 stay)
    blocked = await client.put(
        f"/competitions/{competition_id}/skills/{skill_id}/pathway",
        json=reduced,
        headers=auth_headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "PATHWAY_LOCKED"
