"""US-SCH-01 — Schedule physical-stage sessions and assign workstations."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    Competitor,
    HealthSafetyIncident,
    MarkingScheme,
    NotificationOutbox,
    Pathway,
    ScheduleSession,
    Shortlist,
    ShortlistEntry,
    Skill,
    SlotAssignment,
    Stage,
    Venue,
    Zone,
)
from pytest_tests.conftest import cycle_payload


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_schedule_world(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    venue_capacity: int = 2,
    shortlist_confirmed: bool = True,
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

        stage = Stage(
            cycle_id=cycle_id,
            skill_id=skill.id,
            name="National Finals",
            order=1,
            stage_type="PHYSICAL",
            quota=2,
            quota_by_zone={str(zone.id): 2},
            min_score=50,
            scheme_id=scheme.id,
        )
        session.add(stage)
        await session.flush()

        venue = Venue(
            cycle_id=cycle_id,
            zone_id=zone.id,
            name=f"Venue-{uuid.uuid4().hex[:6]}",
            capacity=venue_capacity,
            workstations=venue_capacity,
            active=True,
        )
        session.add(venue)
        await session.flush()

        competitors: dict[str, Competitor] = {}
        for label in ("A", "B", "C"):
            comp = Competitor(
                cycle_id=cycle_id,
                skill_id=skill.id,
                zone_id=zone.id,
                ref_no=f"REF-{label}-{uuid.uuid4().hex[:4]}",
                status="ACTIVE_IN_STAGE",
                eligibility_status="ELIGIBLE",
                given_names=label,
                family_name="Comp",
                date_of_birth=date(2005, 1, 1),
                nationality="GH",
                enrolment_attested=True,
                flags=[],
            )
            session.add(comp)
            await session.flush()
            competitors[label] = comp

        shortlist = Shortlist(
            cycle_id=cycle_id,
            stage_id=stage.id,
            skill_id=skill.id,
            state="CONFIRMED" if shortlist_confirmed else "PROVISIONAL",
            is_final_stage=True,
            confirmed_at=datetime.utcnow() if shortlist_confirmed else None,
        )
        session.add(shortlist)
        await session.flush()

        # A and B advanced; C waitlisted (not assignable when confirmed)
        for rank, (label, outcome, advanced) in enumerate(
            (("A", "ADVANCE", True), ("B", "ADVANCE", True), ("C", "WAITLIST", False)),
            start=1,
        ):
            session.add(
                ShortlistEntry(
                    shortlist_id=shortlist.id,
                    competitor_id=competitors[label].id,
                    zone_id=zone.id,
                    score=100 - rank,
                    rank=rank,
                    outcome=outcome,
                    advanced=advanced,
                )
            )

        await session.commit()
        return {
            "zone_id": zone.id,
            "skill_id": skill.id,
            "stage_id": stage.id,
            "venue_id": venue.id,
            "venue_capacity": venue_capacity,
            "shortlist_id": shortlist.id,
            "competitors": {k: v.id for k, v in competitors.items()},
        }


def _session_body(venue_id: uuid.UUID, workstations: int = 2) -> dict:
    start = datetime.utcnow() + timedelta(days=1)
    return {
        "venueId": str(venue_id),
        "startsAt": start.isoformat(),
        "endsAt": (start + timedelta(hours=4)).isoformat(),
        "workstations": workstations,
    }


@pytest.mark.asyncio
async def test_US_SCH_01_AC1_create_session(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id, venue_capacity=2)

    ok = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=2),
        headers=auth_headers,
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert "sessionId" in body
    assert body["workstations"] == 2
    assert body["venueId"] == str(ctx["venue_id"])

    async with session_manager.session() as session:
        row = await session.get(ScheduleSession, uuid.UUID(body["sessionId"]))
        assert row is not None
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCHEDULE_SESSION_CREATE",
                    AuditEvent.entity_id == body["sessionId"],
                )
            )
        ).scalars().all()
        assert len(audits) >= 1

    # Exceed venue capacity → CAPACITY_EXCEEDED
    over = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=3),
        headers=auth_headers,
    )
    assert over.status_code == 409, over.text
    assert over.json()["error"]["code"] == "CAPACITY_EXCEEDED"


@pytest.mark.asyncio
async def test_US_SCH_01_AC2_assign_slot(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id)
    created = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=2),
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    ssid = created.json()["sessionId"]

    resp = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["A"]), "workstation": "WS-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["workstation"] == "WS-1"
    assert body["competitorId"] == str(ctx["competitors"]["A"])

    async with session_manager.session() as session:
        assignment = await session.get(SlotAssignment, uuid.UUID(body["assignmentId"]))
        assert assignment is not None
        notes = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.event_key == "SCHEDULE_SLOT_ASSIGNED",
                    NotificationOutbox.cycle_id == cycle_id,
                )
            )
        ).scalars().all()
        assert len(notes) >= 1
        assert notes[0].recipient_id == ctx["competitors"]["A"]
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "SCHEDULE_SLOT_ASSIGN")
            )
        ).scalars().all()
        assert len(audits) >= 1

    # Waitlisted competitor not assignable
    waitlisted = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["C"]), "workstation": "WS-2"},
        headers=auth_headers,
    )
    assert waitlisted.status_code == 409, waitlisted.text
    assert waitlisted.json()["error"]["code"] == "NOT_SHORTLISTED"


@pytest.mark.asyncio
async def test_US_SCH_01_AC3_double_booking_prevented(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id)
    created = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=2),
        headers=auth_headers,
    )
    ssid = created.json()["sessionId"]

    first = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["A"]), "workstation": "WS-1"},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    conflict = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["B"]), "workstation": "WS-1"},
        headers=auth_headers,
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "SLOT_CONFLICT"


@pytest.mark.asyncio
async def test_US_SCH_01_AC4_over_capacity_prevented(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id, venue_capacity=1)
    created = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=1),
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    ssid = created.json()["sessionId"]

    first = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["A"]), "workstation": "WS-1"},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    extra = await client.post(
        f"/schedule/sessions/{ssid}/assignments",
        json={"competitorId": str(ctx["competitors"]["B"]), "workstation": "WS-2"},
        headers=auth_headers,
    )
    assert extra.status_code == 409, extra.text
    assert extra.json()["error"]["code"] == "CAPACITY_EXCEEDED"


@pytest.mark.asyncio
async def test_US_SCH_01_AC5_incident_log(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id)
    created = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=2),
        headers=auth_headers,
    )
    ssid = created.json()["sessionId"]

    resp = await client.post(
        f"/schedule/sessions/{ssid}/incidents",
        json={"summary": "Cable trip hazard near WS-1", "severity": "MEDIUM"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "incidentId" in body
    assert body["sessionId"] == ssid

    async with session_manager.session() as session:
        incident = await session.get(HealthSafetyIncident, uuid.UUID(body["incidentId"]))
        assert incident is not None
        assert incident.summary.startswith("Cable trip")
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SCHEDULE_INCIDENT_RECORD",
                    AuditEvent.entity_id == body["incidentId"],
                )
            )
        ).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_US_SCH_01_concurrency_no_double_booking(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Definition of Done: concurrency proves no double-booking under parallel assignment."""
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_schedule_world(session_manager, cycle_id)
    created = await client.post(
        f"/cycles/{cycle_id}/schedule/sessions",
        json=_session_body(ctx["venue_id"], workstations=2),
        headers=auth_headers,
    )
    ssid = created.json()["sessionId"]

    async def assign(competitor_key: str):
        return await client.post(
            f"/schedule/sessions/{ssid}/assignments",
            json={
                "competitorId": str(ctx["competitors"][competitor_key]),
                "workstation": "WS-1",
            },
            headers=auth_headers,
        )

    r1, r2 = await asyncio.gather(assign("A"), assign("B"))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [201, 409]
    loser = r1 if r1.status_code == 409 else r2
    assert loser.json()["error"]["code"] == "SLOT_CONFLICT"

    async with session_manager.session() as session:
        rows = (
            await session.execute(
                select(SlotAssignment).where(
                    SlotAssignment.session_id == uuid.UUID(ssid),
                    SlotAssignment.workstation == "WS-1",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
