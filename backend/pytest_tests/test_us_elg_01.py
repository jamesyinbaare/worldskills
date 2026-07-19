"""US-ELG-01 — Screen a registration for age and eligibility."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    Competitor,
    MarkingScheme,
    Pathway,
    Skill,
    Zone,
)
from pytest_tests.conftest import cycle_payload


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_skills(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    max_a: int = 25,
    max_b: int = 18,
    open_category: bool = False,
    ref: date | None = date(2026, 1, 1),
) -> dict[str, uuid.UUID]:
    async with session_manager.session() as session:
        rule_a = AgeRule(
            cycle_id=cycle_id,
            name=f"U{max_a}",
            max_age=max_a,
            reference_date=ref,
            open_category_enabled=open_category,
        )
        rule_b = AgeRule(
            cycle_id=cycle_id,
            name=f"U{max_b}",
            max_age=max_b,
            reference_date=ref,
            open_category_enabled=False,
        )
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        session.add_all([rule_a, rule_b, path, scheme])
        await session.flush()
        skill_a = Skill(
            cycle_id=cycle_id,
            name="Skill A",
            age_rule_id=rule_a.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
            eligibility_rules={"requireNationality": ["GH"], "requireEnrolmentAttestation": True},
        )
        skill_b = Skill(
            cycle_id=cycle_id,
            name="Skill B",
            age_rule_id=rule_b.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        session.add_all([skill_a, skill_b, zone])
        await session.commit()
        return {
            "skill_a": skill_a.id,
            "skill_b": skill_b.id,
            "zone_id": zone.id,
            "rule_a": rule_a.id,
        }


async def _add_competitor(
    session_manager: DBManager,
    *,
    cycle_id: uuid.UUID,
    skill_id: uuid.UUID,
    zone_id: uuid.UUID,
    dob: date,
    nationality: str | None = "GH",
    enrolment: bool = True,
) -> uuid.UUID:
    async with session_manager.session() as session:
        c = Competitor(
            cycle_id=cycle_id,
            skill_id=skill_id,
            zone_id=zone_id,
            ref_no=f"ELG-{uuid.uuid4().hex[:8].upper()}",
            status="PENDING_REVIEW",
            date_of_birth=dob,
            nationality=nationality,
            enrolment_attested=enrolment,
            given_names="Test",
            family_name="Competitor",
        )
        session.add(c)
        await session.commit()
        return c.id


@pytest.mark.asyncio
async def test_US_ELG_01_AC1_eligible(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, max_a=25)
    # Age exactly 25 on 2026-01-01 → boundary eligible
    cid = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_a"],
        zone_id=ctx["zone_id"],
        dob=date(2001, 1, 1),
    )

    resp = await client.post(f"/competitors/{cid}:screen", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is True
    assert body["status"] == "ELIGIBLE"
    assert body["failedRules"] == []
    assert body["category"] == "COMPETITIVE"
    assert body["ageAtReference"] == 25


@pytest.mark.asyncio
async def test_US_ELG_01_AC2_over_age(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, max_a=25)
    cid = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_a"],
        zone_id=ctx["zone_id"],
        dob=date(1999, 1, 1),  # age 27
    )

    resp = await client.post(f"/competitors/{cid}:screen", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is False
    assert body["status"] == "INELIGIBLE"
    assert "AGE_EXCEEDS_LIMIT" in body["failedRules"]


@pytest.mark.asyncio
async def test_US_ELG_01_AC3_per_skill_limits(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, max_a=25, max_b=18)
    # Age 20 — under A (25), over B (18)
    dob = date(2006, 1, 1)
    cid_a = await _add_competitor(
        session_manager, cycle_id=cycle_id, skill_id=ctx["skill_a"], zone_id=ctx["zone_id"], dob=dob
    )
    cid_b = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_b"],
        zone_id=ctx["zone_id"],
        dob=dob,
        nationality=None,
        enrolment=False,
    )

    a = await client.post(f"/competitors/{cid_a}:screen", headers=auth_headers)
    b = await client.post(f"/competitors/{cid_b}:screen", headers=auth_headers)
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["eligible"] is True
    assert a.json()["ageAtReference"] == 20
    assert b.json()["eligible"] is False
    assert "AGE_EXCEEDS_LIMIT" in b.json()["failedRules"]


@pytest.mark.asyncio
async def test_US_ELG_01_AC4_override(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, max_a=18)
    cid = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_a"],
        zone_id=ctx["zone_id"],
        dob=date(2000, 1, 1),
    )
    screened = await client.post(f"/competitors/{cid}:screen", headers=auth_headers)
    assert screened.json()["eligible"] is False

    missing = await client.post(
        f"/competitors/{cid}/eligibility:override",
        json={"value": True},
        headers=auth_headers,
    )
    assert missing.status_code == 422
    assert any(f["reason"] == "REASON_REQUIRED" for f in missing.json()["error"]["fields"])

    ok = await client.post(
        f"/competitors/{cid}/eligibility:override",
        json={"value": True, "reason": "DOB document verified — year typo", "category": "COMPETITIVE"},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["eligible"] is True
    assert ok.json()["status"] == "ELIGIBLE"
    assert ok.json()["reason"] == "DOB document verified — year typo"

    async with session_manager.session() as session:
        c = await session.get(Competitor, cid)
        assert c is not None
        assert c.eligibility_override_reason is not None
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ELIGIBILITY_OVERRIDE",
                    AuditEvent.entity_id == str(cid),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.reason == "DOB document verified — year typo"


@pytest.mark.asyncio
async def test_US_ELG_01_AC5_open_category(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, max_a=18, open_category=True)
    cid = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_a"],
        zone_id=ctx["zone_id"],
        dob=date(2000, 1, 1),  # age 26 > 18
    )

    resp = await client.post(f"/competitors/{cid}:screen", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is True
    assert body["status"] == "OPEN_CATEGORY"
    assert body["category"] == "OPEN"
    assert "AGE_EXCEEDS_LIMIT" in body["failedRules"]


@pytest.mark.asyncio
async def test_US_ELG_01_missing_reference_date_fail_closed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_skills(session_manager, cycle_id, ref=None)
    cid = await _add_competitor(
        session_manager,
        cycle_id=cycle_id,
        skill_id=ctx["skill_a"],
        zone_id=ctx["zone_id"],
        dob=date(2005, 1, 1),
    )
    resp = await client.post(f"/competitors/{cid}:screen", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFIG_INCOMPLETE"
