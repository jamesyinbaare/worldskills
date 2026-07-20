"""US-APP-01 — Lodge and rule on an appeal; record disqualification."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AppealsConfig,
    AppealCase,
    AuditEvent,
    Competitor,
    Institution,
    InstitutionCycleMembership,
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
from pytest_tests.conftest import cycle_payload


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_appeals_world(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    window_closes_at: datetime | None = None,
    with_appeals_config: bool = True,
    dq_reasons: list[str] | None = None,
    tie_break_rules: list[str] | None = None,
) -> dict:
    async with session_manager.session() as session:
        age = AgeRule(
            cycle_id=cycle_id,
            name="U25",
            max_age=25,
            reference_date=date(2026, 1, 1),
            open_category_enabled=False,
        )
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        institution = Institution(name=f"Inst-{uuid.uuid4().hex[:6]}", active=True)
        other_inst = Institution(name=f"Other-{uuid.uuid4().hex[:6]}", active=True)
        session.add_all([age, path, scheme, zone, institution, other_inst])
        await session.flush()

        session.add(
            InstitutionCycleMembership(
                cycle_id=cycle_id,
                institution_id=institution.id,
                zone_id=zone.id,
            )
        )

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

        stage = Stage(
            cycle_id=cycle_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            quota=1,
            quota_by_zone={str(zone.id): 1},
            min_score=50,
            scheme_id=scheme.id,
        )
        session.add(stage)
        await session.flush()

        # A = appellant (institution member), B = tied rival, C = waitlist filler
        competitors: dict[str, Competitor] = {}
        specs = {
            "A": {"dob": date(2005, 6, 1), "ref": "REF-A", "inst": institution.id, "score": 90},
            "B": {"dob": date(2004, 1, 1), "ref": "REF-B", "inst": other_inst.id, "score": 90},
            "C": {"dob": date(2003, 1, 1), "ref": "REF-C", "inst": None, "score": 70},
        }
        for label, meta in specs.items():
            comp = Competitor(
                cycle_id=cycle_id,
                skill_id=skill.id,
                zone_id=zone.id,
                institution_id=meta["inst"],
                ref_no=f"{meta['ref']}-{uuid.uuid4().hex[:4]}",
                status="ACTIVE_IN_STAGE",
                eligibility_status="ELIGIBLE",
                given_names=label,
                family_name="Comp",
                date_of_birth=meta["dob"],
                nationality="GH",
                enrolment_attested=True,
                flags=[],
            )
            session.add(comp)
            await session.flush()
            competitors[label] = comp
            session.add(
                Submission(
                    cycle_id=cycle_id,
                    competitor_id=comp.id,
                    stage_id=stage.id,
                    state="ACCEPTED",
                    score_total=meta["score"],
                    submitted_at=datetime.utcnow(),
                )
            )

        if with_appeals_config:
            closes = window_closes_at if window_closes_at is not None else datetime.utcnow() + timedelta(days=7)
            session.add(
                AppealsConfig(
                    cycle_id=cycle_id,
                    appeal_window_opens_at=datetime.utcnow() - timedelta(days=1),
                    appeal_window_closes_at=closes,
                    dq_reasons=dq_reasons or ["CHEATING", "MISCONDUCT", "SAFETY"],
                    tie_break_rules=tie_break_rules
                    or ["SCORE_DESC", "YOUNGER_FIRST", "REF_NO_ASC"],
                )
            )

        competitor_user = User(
            email=f"comp-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Competitor A",
            hashed_password=get_password_hash("comp-pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        inst_user = User(
            email=f"inst-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Institution User",
            hashed_password=get_password_hash("inst-pass-123"),
            role=UserRole.INSTITUTION,
            institution_id=institution.id,
            is_active=True,
        )
        # Conflicted officer shares institution with appellant A
        conflicted_officer = User(
            email=f"coi-off-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Conflicted Officer",
            hashed_password=get_password_hash("off-pass-123"),
            role=UserRole.APPEALS_OFFICER,
            institution_id=institution.id,
            is_active=True,
        )
        clear_officer = User(
            email=f"off-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Clear Officer",
            hashed_password=get_password_hash("off-pass-123"),
            role=UserRole.APPEALS_OFFICER,
            institution_id=other_inst.id,
            is_active=True,
        )
        session.add_all([competitor_user, inst_user, conflicted_officer, clear_officer])
        await session.commit()

        return {
            "zone_id": zone.id,
            "skill_id": skill.id,
            "stage_id": stage.id,
            "institution_id": institution.id,
            "competitors": {k: v.id for k, v in competitors.items()},
            "competitor_refs": {k: v.ref_no for k, v in competitors.items()},
            "competitor_user": competitor_user,
            "competitor_email": competitor_user.email,
            "inst_email": inst_user.email,
            "conflicted_officer_id": conflicted_officer.id,
            "conflicted_email": conflicted_officer.email,
            "clear_officer_id": clear_officer.id,
            "clear_email": clear_officer.email,
        }


async def _login_headers(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_APP_01_AC1_within_window(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(session_manager, cycle_id)
    headers = await _login_headers(client, ctx["inst_email"], "inst-pass-123")

    resp = await client.post(
        f"/cycles/{cycle_id}/appeals",
        json={
            "competitorId": str(ctx["competitors"]["A"]),
            "stageId": str(ctx["stage_id"]),
            "reason": "Score calculation error on criterion 3",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["state"] == "SUBMITTED"
    assert "appealId" in body

    async with session_manager.session() as session:
        case = await session.get(AppealCase, uuid.UUID(body["appealId"]))
        assert case is not None
        assert case.state == "SUBMITTED"
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "APPEAL_LODGED",
                    AuditEvent.entity_id == body["appealId"],
                )
            )
        ).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_US_APP_01_AC2_out_of_window(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(
        session_manager,
        cycle_id,
        window_closes_at=datetime.utcnow() - timedelta(hours=1),
    )
    headers = await _login_headers(client, ctx["inst_email"], "inst-pass-123")

    resp = await client.post(
        f"/cycles/{cycle_id}/appeals",
        json={
            "competitorId": str(ctx["competitors"]["A"]),
            "stageId": str(ctx["stage_id"]),
            "reason": "Too late",
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "APPEAL_WINDOW_CLOSED"


@pytest.mark.asyncio
async def test_US_APP_01_AC3_independent_routing(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(session_manager, cycle_id)
    lodge = await client.post(
        f"/cycles/{cycle_id}/appeals",
        json={
            "competitorId": str(ctx["competitors"]["A"]),
            "stageId": str(ctx["stage_id"]),
            "reason": "Unfair mark",
        },
        headers=await _login_headers(client, ctx["inst_email"], "inst-pass-123"),
    )
    assert lodge.status_code == 201, lodge.text
    aid = lodge.json()["appealId"]

    conflicted = await client.post(
        f"/appeals/{aid}:assign",
        json={"officerId": str(ctx["conflicted_officer_id"])},
        headers=auth_headers,
    )
    assert conflicted.status_code == 409, conflicted.text
    assert conflicted.json()["error"]["code"] == "OFFICER_CONFLICT"

    ok = await client.post(
        f"/appeals/{aid}:assign",
        json={"officerId": str(ctx["clear_officer_id"])},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"] == "UNDER_REVIEW"
    assert ok.json()["officerId"] == str(ctx["clear_officer_id"])


@pytest.mark.asyncio
async def test_US_APP_01_AC4_ruling_and_remedy(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(session_manager, cycle_id)

    # Seed a confirmed shortlist with A ADVANCED; B waitlisted — uphold reinstate+re-rank
    async with session_manager.session() as session:
        shortlist = Shortlist(
            cycle_id=cycle_id,
            stage_id=ctx["stage_id"],
            skill_id=ctx["skill_id"],
            state="CONFIRMED",
            is_final_stage=False,
            confirmed_at=datetime.utcnow(),
        )
        session.add(shortlist)
        await session.flush()
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=ctx["competitors"]["B"],
                zone_id=ctx["zone_id"],
                score=90,
                rank=1,
                outcome="ADVANCE",
                advanced=True,
            )
        )
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=ctx["competitors"]["A"],
                zone_id=ctx["zone_id"],
                score=90,
                rank=2,
                outcome="WAITLIST",
                advanced=False,
            )
        )
        # Mark A eliminated pending appeal
        a = await session.get(Competitor, ctx["competitors"]["A"])
        assert a is not None
        a.status = "ELIMINATED"
        a.flags = ["WAITLIST"]
        await session.commit()

    lodge = await client.post(
        f"/cycles/{cycle_id}/appeals",
        json={
            "competitorId": str(ctx["competitors"]["A"]),
            "stageId": str(ctx["stage_id"]),
            "reason": "Tie-break unfair",
        },
        headers=await _login_headers(client, ctx["inst_email"], "inst-pass-123"),
    )
    assert lodge.status_code == 201, lodge.text
    aid = lodge.json()["appealId"]

    assign = await client.post(
        f"/appeals/{aid}:assign",
        json={"officerId": str(ctx["clear_officer_id"])},
        headers=auth_headers,
    )
    assert assign.status_code == 200, assign.text

    no_reason = await client.post(
        f"/appeals/{aid}:rule",
        json={"outcome": "UPHELD", "remedy": "REINSTATE"},
        headers=await _login_headers(client, ctx["clear_email"], "off-pass-123"),
    )
    assert no_reason.status_code == 422, no_reason.text
    assert no_reason.json()["error"]["code"] == "REASON_REQUIRED"

    rule = await client.post(
        f"/appeals/{aid}:rule",
        json={
            "outcome": "UPHELD",
            "reason": "Younger competitor should have advanced under tie-break",
            "remedy": "REINSTATE",
        },
        headers=await _login_headers(client, ctx["clear_email"], "off-pass-123"),
    )
    assert rule.status_code == 200, rule.text
    body = rule.json()
    assert body["state"] in {"UPHELD", "REMEDIED"}
    assert body["remedy"] == "REINSTATE"

    async with session_manager.session() as session:
        case = await session.get(AppealCase, uuid.UUID(aid))
        assert case is not None
        assert case.state == "REMEDIED"
        assert case.ruling_reason is not None
        a = await session.get(Competitor, ctx["competitors"]["A"])
        assert a is not None
        assert a.status == "ACTIVE_IN_STAGE"
        notes = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.event_key == "APPEAL_OUTCOME",
                    NotificationOutbox.cycle_id == cycle_id,
                )
            )
        ).scalars().all()
        assert len(notes) >= 1
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "APPEAL_RULED")
            )
        ).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_US_APP_01_AC5_disqualification(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(session_manager, cycle_id)
    cid = ctx["competitors"]["A"]

    async with session_manager.session() as session:
        shortlist = Shortlist(
            cycle_id=cycle_id,
            stage_id=ctx["stage_id"],
            skill_id=ctx["skill_id"],
            state="CONFIRMED",
            is_final_stage=False,
            confirmed_at=datetime.utcnow(),
        )
        session.add(shortlist)
        await session.flush()
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=cid,
                zone_id=ctx["zone_id"],
                score=90,
                rank=1,
                outcome="ADVANCE",
                advanced=True,
            )
        )
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=ctx["competitors"]["C"],
                zone_id=ctx["zone_id"],
                score=70,
                rank=2,
                outcome="WAITLIST",
                advanced=False,
            )
        )
        await session.commit()

    bad = await client.post(
        f"/competitors/{cid}:disqualify",
        json={"reason": "NOT_A_REASON"},
        headers=auth_headers,
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "INVALID_DQ_REASON"

    resp = await client.post(
        f"/competitors/{cid}:disqualify",
        json={"reason": "CHEATING"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "DISQUALIFIED"

    async with session_manager.session() as session:
        comp = await session.get(Competitor, cid)
        assert comp is not None
        assert comp.status == "DISQUALIFIED"
        assert comp.dq_reason == "CHEATING"
        entry = (
            await session.execute(
                select(ShortlistEntry).where(ShortlistEntry.competitor_id == cid)
            )
        ).scalar_one()
        assert entry.advanced is False
        assert entry.outcome in {"EXCLUDED", "DISQUALIFIED"} or entry.reason == "DISQUALIFIED"
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "COMPETITOR_DISQUALIFY",
                    AuditEvent.entity_id == str(cid),
                )
            )
        ).scalars().all()
        assert len(audits) >= 1
        assert audits[0].reason == "CHEATING"


@pytest.mark.asyncio
async def test_US_APP_01_AC6_tie_break(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_appeals_world(
        session_manager,
        cycle_id,
        tie_break_rules=["SCORE_DESC", "YOUNGER_FIRST", "REF_NO_ASC"],
    )

    # A (younger, 2005) and B (older, 2004) tied at 90; quota=1 → A advances
    resp = await client.post(
        f"/cycles/{cycle_id}/stages/{ctx['stage_id']}:shortlist",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    zone_key = str(ctx["zone_id"])
    items = body["byZone"][zone_key]
    advanced = [i for i in items if i["outcome"] == "ADVANCE"]
    waitlisted = [i for i in items if i["outcome"] == "WAITLIST"]
    assert len(advanced) == 1
    assert advanced[0]["competitorId"] == str(ctx["competitors"]["A"])
    assert any(i["competitorId"] == str(ctx["competitors"]["B"]) for i in waitlisted)

    # Missing tie-break config with a tie at boundary → CONFIG_INCOMPLETE
    cycle2 = await _create_cycle(client, auth_headers)
    ctx2 = await _seed_appeals_world(session_manager, cycle2, with_appeals_config=False)
    missing = await client.post(
        f"/cycles/{cycle2}/stages/{ctx2['stage_id']}:shortlist",
        headers=auth_headers,
    )
    assert missing.status_code == 409, missing.text
    assert missing.json()["error"]["code"] == "CONFIG_INCOMPLETE"
