"""US-SHL-01 — Generate, confirm and apply a shortlist."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    MarkingScheme,
    NotificationOutbox,
    Pathway,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    Submission,
    User,
    UserRole,
    Zone,
)
from app.services.pathway_engine import Candidate, rank_for_shortlist
from pytest_tests.conftest import cycle_payload

# Fixture: zone quota 2, minScore 50
# Scores: A=90, B=80, C=70, D=40 (below min) → advance A,B; waitlist C; exclude D


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_shortlist_world(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    with_next_stage: bool = True,
    min_score: int = 50,
    quota: int = 2,
) -> dict:
    async with session_manager.session() as session:
        age = AgeRule(cycle_id=cycle_id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()

        skill = Skill(
            cycle_id=cycle_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=40,
            active=True,
        )
        session.add(skill)
        await session.flush()

        stage1 = Stage(
            cycle_id=cycle_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            quota=quota,
            quota_by_zone={str(zone.id): quota},
            min_score=min_score,
            scheme_id=scheme.id,
        )
        session.add(stage1)
        await session.flush()

        stage2 = None
        if with_next_stage:
            stage2 = Stage(
                cycle_id=cycle_id,
                skill_id=skill.id,
                name="National",
                order=2,
                quota=1,
                quota_by_zone={str(zone.id): 1},
                min_score=min_score,
                scheme_id=scheme.id,
            )
            session.add(stage2)
            await session.flush()

        scores = {"A": 90, "B": 80, "C": 70, "D": 40}
        competitors: dict[str, Competitor] = {}
        submissions: dict[str, Submission] = {}
        for label, score in scores.items():
            comp = Competitor(
                cycle_id=cycle_id,
                skill_id=skill.id,
                zone_id=zone.id,
                ref_no=f"REF-{label}-{uuid.uuid4().hex[:4]}",
                status="ACTIVE_IN_STAGE",
                eligibility_status="ELIGIBLE",
                given_names=label,
                family_name="Comp",
            )
            session.add(comp)
            await session.flush()
            sub = Submission(
                cycle_id=cycle_id,
                competitor_id=comp.id,
                stage_id=stage1.id,
                state="ACCEPTED",
                score_total=score,
            )
            session.add(sub)
            competitors[label] = comp
            submissions[label] = sub

        chief = User(
            email=f"chief-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Chief Expert",
            hashed_password=get_password_hash("chief-pass-123"),
            role=UserRole.CHIEF_EXPERT,
            is_active=True,
        )
        session.add(chief)
        await session.commit()

        return {
            "zone_id": zone.id,
            "skill_id": skill.id,
            "stage1_id": stage1.id,
            "stage2_id": stage2.id if stage2 else None,
            "competitors": {k: v.id for k, v in competitors.items()},
            "chief": chief,
        }


async def _chief_headers(client: AsyncClient, chief: User) -> dict[str, str]:
    login = await client.post(
        "/auth/login",
        json={"email": chief.email, "password": "chief-pass-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_SHL_01_AC1_provisional_shortlist(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_shortlist_world(session_manager, cycle_id)
    headers = await _chief_headers(client, ctx["chief"])

    resp = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "PROVISIONAL"
    zone_key = str(ctx["zone_id"])
    ranked = body["byZone"][zone_key]
    by_comp = {r["competitorId"]: r for r in ranked}

    assert by_comp[str(ctx["competitors"]["A"])]["outcome"] == "ADVANCE"
    assert by_comp[str(ctx["competitors"]["B"])]["outcome"] == "ADVANCE"
    assert by_comp[str(ctx["competitors"]["C"])]["outcome"] == "WAITLIST"
    assert by_comp[str(ctx["competitors"]["D"])]["outcome"] == "EXCLUDED"
    assert by_comp[str(ctx["competitors"]["D"])]["reason"] == "BELOW_MIN_SCORE"

    # Engine fixture agreement
    engine = rank_for_shortlist(
        [
            Candidate(str(ctx["competitors"]["A"]), str(ctx["zone_id"]), 90),
            Candidate(str(ctx["competitors"]["B"]), str(ctx["zone_id"]), 80),
            Candidate(str(ctx["competitors"]["C"]), str(ctx["zone_id"]), 70),
            Candidate(str(ctx["competitors"]["D"]), str(ctx["zone_id"]), 40),
        ],
        quota_by_zone={str(ctx["zone_id"]): 2},
        min_score=50,
    )
    assert {e.competitor_id for e in engine if e.outcome == "ADVANCE"} == {
        str(ctx["competitors"]["A"]),
        str(ctx["competitors"]["B"]),
    }


@pytest.mark.asyncio
async def test_US_SHL_01_AC2_confirmation_gate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_shortlist_world(session_manager, cycle_id)
    headers = await _chief_headers(client, ctx["chief"])

    await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )

    async with session_manager.session() as session:
        for cid in ctx["competitors"].values():
            comp = await session.get(Competitor, cid)
            assert comp is not None
            assert comp.status == "ACTIVE_IN_STAGE"
        notes = (await session.execute(select(NotificationOutbox))).scalars().all()
        assert notes == []
        shortlist = (
            await session.execute(
                select(Shortlist).where(Shortlist.stage_id == ctx["stage1_id"])
            )
        ).scalar_one()
        assert shortlist.state == "PROVISIONAL"
        entries = (
            await session.execute(
                select(ShortlistEntry).where(ShortlistEntry.shortlist_id == shortlist.id)
            )
        ).scalars().all()
        assert all(e.advanced is False for e in entries)


@pytest.mark.asyncio
async def test_US_SHL_01_AC3_advance_on_confirm(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_shortlist_world(session_manager, cycle_id, with_next_stage=True)
    headers = await _chief_headers(client, ctx["chief"])

    await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )
    confirm = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:confirm-shortlist",
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["state"] == "CONFIRMED"
    advanced = {str(x) for x in body["advanced"]}
    waitlist = {str(x) for x in body["waitlist"]}
    assert advanced == {str(ctx["competitors"]["A"]), str(ctx["competitors"]["B"])}
    assert str(ctx["competitors"]["C"]) in waitlist
    assert body["notified"] >= 3

    async with session_manager.session() as session:
        for label in ("A", "B"):
            comp = await session.get(Competitor, ctx["competitors"][label])
            assert comp is not None
            assert comp.status == "ACTIVE_IN_STAGE"
        c = await session.get(Competitor, ctx["competitors"]["C"])
        assert c is not None
        assert "WAITLIST" in (c.flags or [])
        notes = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.cycle_id == cycle_id,
                    NotificationOutbox.template.in_(
                        ["SHORTLIST_ADVANCED", "SHORTLIST_WAITLIST"]
                    ),
                )
            )
        ).scalars().all()
        assert len(notes) >= 3


@pytest.mark.asyncio
async def test_US_SHL_01_AC4_threshold_excludes(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_shortlist_world(session_manager, cycle_id)
    headers = await _chief_headers(client, ctx["chief"])

    resp = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    ranked = resp.json()["byZone"][str(ctx["zone_id"])]
    d = next(r for r in ranked if r["competitorId"] == str(ctx["competitors"]["D"]))
    assert d["outcome"] == "EXCLUDED"
    assert d["reason"] == "BELOW_MIN_SCORE"
    # Would have been within quota top-2 by rank if threshold ignored — score order D is last anyway,
    # so also verify engine excludes mid-rank below threshold:
    below = rank_for_shortlist(
        [
            Candidate("1", "z", 90),
            Candidate("2", "z", 45),  # within top-2 by score among eligible? no — below min
            Candidate("3", "z", 80),
        ],
        quota_by_zone={"z": 2},
        min_score=50,
    )
    by_id = {e.competitor_id: e for e in below}
    assert by_id["2"].outcome == "EXCLUDED"
    assert by_id["2"].reason == "BELOW_MIN_SCORE"
    assert by_id["1"].outcome == "ADVANCE"
    assert by_id["3"].outcome == "ADVANCE"


@pytest.mark.asyncio
async def test_US_SHL_01_AC5_finalist_output(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    # Final stage only (no next)
    ctx = await _seed_shortlist_world(session_manager, cycle_id, with_next_stage=False)
    headers = await _chief_headers(client, ctx["chief"])

    gen = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )
    assert gen.status_code == 200, gen.text
    assert gen.json()["isFinalStage"] is True

    confirm = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:confirm-shortlist",
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["finalists"] is not None
    finalist_ids = {str(f["competitorId"]) for f in body["finalists"]}
    assert finalist_ids == {str(ctx["competitors"]["A"]), str(ctx["competitors"]["B"])}

    async with session_manager.session() as session:
        for label in ("A", "B"):
            comp = await session.get(Competitor, ctx["competitors"][label])
            assert comp is not None
            assert comp.status == "FINALIST"


@pytest.mark.asyncio
async def test_US_SHL_01_not_authorised_for_competitor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_shortlist_world(session_manager, cycle_id)
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage1_id']}:shortlist",
        headers=headers,
    )
    assert denied.status_code == 403
