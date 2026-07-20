"""US-LCY-01 — Withdraw, substitute, and promote from the waitlist."""

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
    AuditEvent,
    Competitor,
    Institution,
    InstitutionCycleMembership,
    LifecycleConfig,
    MarkingScheme,
    NotificationOutbox,
    Pathway,
    ResultEntry,
    ResultPublication,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import cycle_payload


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_lifecycle_world(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    cutoff: datetime | None = None,
    with_lifecycle_config: bool = True,
    with_shortlist: bool = True,
) -> dict:
    """A=ADVANCE, B=ADVANCE, C=WAITLIST; institution owns A."""
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
        session.add_all([age, path, scheme, zone, institution])
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
            eligibility_rules={"requireNationality": ["GH"]},
        )
        session.add(skill)
        await session.flush()

        stage = Stage(
            cycle_id=cycle_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            quota=2,
            quota_by_zone={str(zone.id): 2},
            min_score=50,
            scheme_id=scheme.id,
        )
        session.add(stage)
        await session.flush()

        scores = {"A": 90, "B": 80, "C": 70}
        competitors: dict[str, Competitor] = {}
        for label, score in scores.items():
            status = "ACTIVE_IN_STAGE" if label in ("A", "B") else "ACTIVE_IN_STAGE"
            flags = ["WAITLIST"] if label == "C" else []
            # C stays waitlisted after confirm — status ACTIVE_IN_STAGE with WAITLIST flag
            comp = Competitor(
                cycle_id=cycle_id,
                skill_id=skill.id,
                zone_id=zone.id,
                institution_id=institution.id if label == "A" else None,
                ref_no=f"REF-{label}-{uuid.uuid4().hex[:4]}",
                status=status,
                eligibility_status="ELIGIBLE",
                given_names=label,
                family_name="Comp",
                date_of_birth=date(2005, 6, 1),
                nationality="GH",
                enrolment_attested=True,
                flags=flags,
            )
            session.add(comp)
            await session.flush()
            competitors[label] = comp

        shortlist_id = None
        if with_shortlist:
            shortlist = Shortlist(
                cycle_id=cycle_id,
                stage_id=stage.id,
                skill_id=skill.id,
                state="CONFIRMED",
                is_final_stage=False,
                confirmed_at=datetime.utcnow(),
            )
            session.add(shortlist)
            await session.flush()
            shortlist_id = shortlist.id
            for i, label in enumerate(("A", "B", "C"), start=1):
                outcome = "ADVANCE" if label in ("A", "B") else "WAITLIST"
                session.add(
                    ShortlistEntry(
                        shortlist_id=shortlist.id,
                        competitor_id=competitors[label].id,
                        zone_id=zone.id,
                        score=scores[label],
                        rank=i,
                        outcome=outcome,
                        advanced=label in ("A", "B"),
                    )
                )

        if with_lifecycle_config:
            session.add(
                LifecycleConfig(
                    cycle_id=cycle_id,
                    substitution_cutoff_at=cutoff
                    if cutoff is not None
                    else datetime.utcnow() + timedelta(days=14),
                    waitlist_order="RANK",
                )
            )

        inst_user = User(
            email=f"inst-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Institution User",
            hashed_password=get_password_hash("inst-pass-123"),
            role=UserRole.INSTITUTION,
            institution_id=institution.id,
            is_active=True,
        )
        session.add(inst_user)
        await session.commit()

        return {
            "zone_id": zone.id,
            "skill_id": skill.id,
            "stage_id": stage.id,
            "shortlist_id": shortlist_id,
            "institution_id": institution.id,
            "competitors": {k: v.id for k, v in competitors.items()},
            "inst_user": inst_user,
            "inst_email": inst_user.email,
        }


async def _inst_headers(client: AsyncClient, email: str) -> dict[str, str]:
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "inst-pass-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _replacement_payload(**overrides: object) -> dict:
    base = {
        "refNo": f"REP-{uuid.uuid4().hex[:6]}",
        "givenNames": "Replacement",
        "familyName": "Athlete",
        "dateOfBirth": "2004-03-15",
        "nationality": "GH",
        "enrolmentAttested": True,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_US_LCY_01_AC1_withdrawal(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(session_manager, cycle_id)
    cid = ctx["competitors"]["B"]

    missing = await client.post(
        f"/competitors/{cid}:withdraw",
        json={},
        headers=auth_headers,
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["code"] == "REASON_REQUIRED"

    resp = await client.post(
        f"/competitors/{cid}:withdraw",
        json={"reason": "Injury"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "WITHDRAWN"
    assert body["competitorId"] == str(cid)

    async with session_manager.session() as session:
        comp = await session.get(Competitor, cid)
        assert comp is not None
        assert comp.status == "WITHDRAWN"
        assert comp.withdrawn_reason == "Injury"
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "COMPETITOR_WITHDRAW",
                    AuditEvent.entity_id == str(cid),
                )
            )
        ).scalars().all()
        assert len(audits) >= 1
        assert audits[0].reason == "Injury"


@pytest.mark.asyncio
async def test_US_LCY_01_AC2_substitution_in_window(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(
        session_manager,
        cycle_id,
        cutoff=datetime.utcnow() + timedelta(days=7),
    )
    headers = await _inst_headers(client, ctx["inst_email"])
    cid = ctx["competitors"]["A"]

    resp = await client.post(
        f"/competitors/{cid}:substitute",
        json={"replacement": _replacement_payload()},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["withdrawnCompetitorId"] == str(cid)
    assert body["replacementCompetitorId"]
    assert body["eligible"] is True

    async with session_manager.session() as session:
        old = await session.get(Competitor, cid)
        new = await session.get(Competitor, uuid.UUID(body["replacementCompetitorId"]))
        assert old is not None and new is not None
        assert old.status == "WITHDRAWN"
        assert new.status == "ACTIVE_IN_STAGE"
        assert new.eligibility_status == "ELIGIBLE"
        assert new.institution_id == ctx["institution_id"]
        assert new.skill_id == ctx["skill_id"]
        assert new.substitutes_id == cid

        entry_old = (
            await session.execute(
                select(ShortlistEntry).where(ShortlistEntry.competitor_id == cid)
            )
        ).scalar_one()
        assert entry_old.outcome == "ADVANCE"
        assert entry_old.advanced is False

        entry_new = (
            await session.execute(
                select(ShortlistEntry).where(ShortlistEntry.competitor_id == new.id)
            )
        ).scalar_one()
        assert entry_new.outcome == "ADVANCE"
        assert entry_new.advanced is True
        assert entry_new.rank == entry_old.rank


@pytest.mark.asyncio
async def test_US_LCY_01_AC3_substitution_after_cutoff(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(
        session_manager,
        cycle_id,
        cutoff=datetime.utcnow() - timedelta(days=1),
    )
    headers = await _inst_headers(client, ctx["inst_email"])

    resp = await client.post(
        f"/competitors/{ctx['competitors']['A']}:substitute",
        json={"replacement": _replacement_payload()},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "SUBSTITUTION_CLOSED"


@pytest.mark.asyncio
async def test_US_LCY_01_AC4_waitlist_promotion(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(session_manager, cycle_id)
    vacating = ctx["competitors"]["A"]
    waitlisted = ctx["competitors"]["C"]

    resp = await client.post(
        f"/competitors/{vacating}:withdraw",
        json={"reason": "Withdrew from finals"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["promotedCompetitorId"] == str(waitlisted)

    async with session_manager.session() as session:
        promoted = await session.get(Competitor, waitlisted)
        assert promoted is not None
        assert promoted.status == "ACTIVE_IN_STAGE"
        assert "WAITLIST" not in (promoted.flags or [])

        entry = (
            await session.execute(
                select(ShortlistEntry).where(ShortlistEntry.competitor_id == waitlisted)
            )
        ).scalar_one()
        assert entry.outcome == "ADVANCE"
        assert entry.advanced is True

        notes = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "WAITLIST_PROMOTED",
                    NotificationOutbox.recipient_id == waitlisted,
                )
            )
        ).scalars().all()
        assert len(notes) >= 1


@pytest.mark.asyncio
async def test_US_LCY_01_substitute_eligibility_failed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(session_manager, cycle_id)
    headers = await _inst_headers(client, ctx["inst_email"])

    resp = await client.post(
        f"/competitors/{ctx['competitors']['A']}:substitute",
        json={
            "replacement": _replacement_payload(
                nationality="NG",  # skill requires GH
                dateOfBirth="2004-01-01",
            )
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "ELIGIBILITY_FAILED"

    async with session_manager.session() as session:
        old = await session.get(Competitor, ctx["competitors"]["A"])
        assert old is not None
        assert old.status == "ACTIVE_IN_STAGE"


@pytest.mark.asyncio
async def test_US_LCY_01_config_incomplete_on_substitute(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(
        session_manager, cycle_id, with_lifecycle_config=False
    )
    headers = await _inst_headers(client, ctx["inst_email"])

    resp = await client.post(
        f"/competitors/{ctx['competitors']['A']}:substitute",
        json={"replacement": _replacement_payload()},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_LCY_01_withdraw_after_results_preserves_history(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_lifecycle_world(session_manager, cycle_id)
    cid = ctx["competitors"]["A"]

    async with session_manager.session() as session:
        pub = ResultPublication(
            cycle_id=cycle_id,
            skill_id=ctx["skill_id"],
            state="RELEASED",
            release_at=datetime.utcnow() - timedelta(days=1),
            audience=["PUBLIC"],
            neutral_status="IN_PROGRESS",
            prepared_at=datetime.utcnow(),
            released_at=datetime.utcnow(),
        )
        session.add(pub)
        await session.flush()
        entry = ResultEntry(
            publication_id=pub.id,
            cycle_id=cycle_id,
            skill_id=ctx["skill_id"],
            competitor_id=cid,
            outcome="GOLD",
            score=90,
            rank=1,
            version=1,
            is_current=True,
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    await client.post(
        f"/competitors/{cid}:withdraw",
        json={"reason": "Post-release withdrawal"},
        headers=auth_headers,
    )

    async with session_manager.session() as session:
        entry = await session.get(ResultEntry, entry_id)
        assert entry is not None
        assert entry.is_current is True
        assert entry.outcome == "GOLD"
        assert entry.score == 90
