"""US-ZON-01 — Zones, regions, region→zone map, registration derive, clone remap."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    CompetitionRegionZone,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    Zone,
)
from app.services.pathway_engine import Candidate, rank_for_national_pool
from pytest_tests.conftest import (
    create_competitor_account,
    competition_payload,
    login_as,
    map_region_to_zone,
    region_id_by_name,
)


async def _comp(client: AsyncClient, session_manager: DBManager) -> dict[str, str]:
    user, password = await create_competitor_account(session_manager)
    return await login_as(client, user.email, password)


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


@pytest.mark.asyncio
async def test_US_ZON_01_AC1_create_zone(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    resp = await client.post(
        f"/competitions/{competition_id}/zones",
        json={"name": "Greater Accra"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Greater Accra"
    assert body["active"] is True


@pytest.mark.asyncio
async def test_US_ZON_01_AC2_region_zone_map(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    z1 = await client.post(
        f"/competitions/{competition_id}/zones",
        json={"name": "Zone A"},
        headers=auth_headers,
    )
    assert z1.status_code == 201
    zone_id = uuid.UUID(z1.json()["zoneId"])
    region_id = await region_id_by_name(session_manager, "Ashanti")

    put = await client.put(
        f"/competitions/{competition_id}/region-zone-map",
        json={"mappings": [{"regionId": str(region_id), "zoneId": str(zone_id)}]},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    assert len(put.json()["mappings"]) == 1

    dup = await client.put(
        f"/competitions/{competition_id}/region-zone-map",
        json={
            "mappings": [
                {"regionId": str(region_id), "zoneId": str(zone_id)},
                {"regionId": str(region_id), "zoneId": str(zone_id)},
            ]
        },
        headers=auth_headers,
    )
    assert dup.status_code == 422
    assert dup.json()["error"]["code"] in {"DUPLICATE", "VALIDATION_ERROR"}


@pytest.mark.asyncio
async def test_US_ZON_01_AC3_registration_derives_zone(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from pytest_tests.test_us_reg_01 import _payload, _seed_reg

    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp(client, session_manager)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, captchaToken="ok"),
        headers=comp,
    )
    assert resp.status_code == 201, resp.text

    async with session_manager.session() as session:
        comp_row = await session.get(Competitor, uuid.UUID(resp.json()["competitorId"]))
        assert comp_row is not None
        assert comp_row.zone_id == ctx["zone_id"]
        assert comp_row.region_id == ctx["region_id"]

    bad_zone = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, zoneId=str(ctx["zone_id"]), captchaToken="ok", email="z@example.com"),
        headers=await _comp(client, session_manager),
    )
    assert bad_zone.status_code == 422
    assert bad_zone.json()["error"]["fields"][0]["name"] == "zoneId"


@pytest.mark.asyncio
async def test_US_ZON_01_AC4_region_precedence(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from pytest_tests.test_us_reg_01 import _payload, _seed_reg

    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    ashanti_region = await region_id_by_name(session_manager, "Ashanti")

    async with session_manager.session() as session:
        zone_b = Zone(competition_id=competition_id, name="Ashanti Zone", active=True)
        session.add(zone_b)
        await session.flush()
        await session.commit()
        zone_b_id = zone_b.id

    await map_region_to_zone(session_manager, competition_id, ashanti_region, zone_b_id)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            regionId=str(ashanti_region),
            captchaToken="ok",
            email=f"override-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers=await _comp(client, session_manager),
    )
    assert resp.status_code == 201, resp.text
    async with session_manager.session() as session:
        comp = await session.get(Competitor, uuid.UUID(resp.json()["competitorId"]))
        assert comp is not None
        assert comp.region_id == ashanti_region
        assert comp.zone_id == zone_b_id


@pytest.mark.asyncio
async def test_US_ZON_01_AC5_unmapped_region(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from pytest_tests.test_us_reg_01 import _payload, _seed_reg

    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    volta = await region_id_by_name(session_manager, "Volta")

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            regionId=str(volta),
            captchaToken="ok",
            email=f"volta-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers=await _comp(client, session_manager),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_ZON_01_AC6_clone_remaps_zones(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    region_id = await region_id_by_name(session_manager, "Greater Accra")

    z_resp = await client.post(
        f"/competitions/{competition_id}/zones",
        json={"name": "GA Zone"},
        headers=auth_headers,
    )
    zone_id = uuid.UUID(z_resp.json()["zoneId"])
    await map_region_to_zone(session_manager, competition_id, region_id, zone_id)

    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        session.add(skill)
        await session.flush()
        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            stage_type="VIRTUAL",
            quota=5,
            quota_by_zone={str(zone_id): 5},
        )
        session.add(stage)
        await session.commit()
        source_stage_id = stage.id

    clone = await client.post(f"/competitions/{competition_id}:clone", headers=auth_headers)
    assert clone.status_code == 201, clone.text
    body = clone.json()
    new_competition_id = uuid.UUID(body.get("newCompetitionId") or body.get("competitionId"))

    async with session_manager.session() as session:
        new_zones = (
            await session.execute(select(Zone).where(Zone.competition_id == new_competition_id))
        ).scalars().all()
        assert len(new_zones) == 1
        new_zone_id = new_zones[0].id
        assert new_zone_id != zone_id

        new_stage = (
            await session.execute(
                select(Stage).where(Stage.competition_id == new_competition_id, Stage.skill_id.is_not(None))
            )
        ).scalar_one()
        assert new_stage.id != source_stage_id
        assert new_stage.quota_by_zone == {str(new_zone_id): 5}

        maps = (
            await session.execute(
                select(CompetitionRegionZone).where(CompetitionRegionZone.competition_id == new_competition_id)
            )
        ).scalars().all()
        assert len(maps) == 1
        assert maps[0].zone_id == new_zone_id


@pytest.mark.asyncio
async def test_US_ZON_01_list_regions(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get("/regions", headers=auth_headers)
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()}
    assert "Greater Accra" in names
    assert "Ashanti" in names


def test_US_ZON_01_national_pool_ranking_unit() -> None:
    candidates = [
        Candidate(competitor_id="a", zone_id="z1", score=90),
        Candidate(competitor_id="b", zone_id="z2", score=85),
        Candidate(competitor_id="c", zone_id="z1", score=80),
        Candidate(competitor_id="d", zone_id="z2", score=70),
    ]
    ranked = rank_for_national_pool(candidates, quota=2, min_score=75)
    advanced = [r for r in ranked if r.outcome == "ADVANCE"]
    assert len(advanced) == 2
    assert {r.competitor_id for r in advanced} == {"a", "b"}
    excluded = [r for r in ranked if r.outcome == "EXCLUDED"]
    assert any(r.competitor_id == "d" for r in excluded)
