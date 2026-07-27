"""Admin competitor roster list API."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    Institution,
    MarkingScheme,
    Pathway,
    Skill,
    Zone,
)
from pytest_tests.conftest import competition_payload, region_id_by_name


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post(
        "/competitions",
        json=competition_payload(timeZone="Africa/Accra"),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_competitors(
    session_manager: DBManager,
    competition_id: uuid.UUID,
) -> dict:
    region_id = await region_id_by_name(session_manager, "Greater Accra")
    async with session_manager.session() as session:
        age = AgeRule(
            competition_id=competition_id,
            name="U25",
            max_age=25,
            reference_date=date(2026, 1, 1),
            open_category_enabled=False,
        )
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        inst = Institution(
            name=f"Roster Inst {uuid.uuid4().hex[:6]}",
            region_id=region_id,
            active=True,
        )
        session.add_all([age, path, scheme, zone, inst])
        await session.flush()

        skill_web = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=40,
            active=True,
        )
        skill_cloud = Skill(
            competition_id=competition_id,
            name="Cloud Computing",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=40,
            active=True,
        )
        session.add_all([skill_web, skill_cloud])
        await session.flush()

        a = Competitor(
            competition_id=competition_id,
            skill_id=skill_web.id,
            zone_id=zone.id,
            institution_id=inst.id,
            ref_no=f"REF-A-{uuid.uuid4().hex[:4]}",
            status="REGISTERED",
            eligibility_status="ELIGIBLE",
            given_names="Ada",
            family_name="Webber",
            date_of_birth=date(2005, 1, 1),
            nationality="GH",
            enrolment_attested=True,
            flags=[],
        )
        b = Competitor(
            competition_id=competition_id,
            skill_id=skill_cloud.id,
            zone_id=zone.id,
            institution_id=inst.id,
            ref_no=f"REF-B-{uuid.uuid4().hex[:4]}",
            status="REGISTERED",
            eligibility_status="ELIGIBLE",
            given_names="Ben",
            family_name="Cloud",
            date_of_birth=date(2004, 1, 1),
            nationality="GH",
            enrolment_attested=True,
            flags=[],
        )
        session.add_all([a, b])
        await session.commit()
        return {
            "skill_web_id": skill_web.id,
            "skill_cloud_id": skill_cloud.id,
            "competitor_a_id": a.id,
            "competitor_b_id": b.id,
            "ref_a": a.ref_no,
            "institution_name": inst.name,
        }


@pytest.mark.asyncio
async def test_admin_list_competitors(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_competitors(session_manager, competition_id)

    listed = await client.get(
        f"/competitions/{competition_id}/competitors",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 2
    ids = {r["competitorId"] for r in rows}
    assert str(ctx["competitor_a_id"]) in ids
    assert str(ctx["competitor_b_id"]) in ids
    web = next(r for r in rows if r["competitorId"] == str(ctx["competitor_a_id"]))
    assert web["skillName"] == "Web Development"
    assert web["institutionName"] == ctx["institution_name"]
    assert web["refNo"] == ctx["ref_a"]

    by_skill = await client.get(
        f"/competitions/{competition_id}/competitors",
        params={"skillId": str(ctx["skill_web_id"])},
        headers=auth_headers,
    )
    assert by_skill.status_code == 200, by_skill.text
    skill_rows = by_skill.json()
    assert len(skill_rows) == 1
    assert skill_rows[0]["competitorId"] == str(ctx["competitor_a_id"])

    by_q = await client.get(
        f"/competitions/{competition_id}/competitors",
        params={"q": "Ada"},
        headers=auth_headers,
    )
    assert by_q.status_code == 200, by_q.text
    assert len(by_q.json()) == 1
    assert by_q.json()[0]["givenNames"] == "Ada"

    missing = await client.get(
        f"/competitions/{uuid.uuid4()}/competitors",
        headers=auth_headers,
    )
    assert missing.status_code == 404
