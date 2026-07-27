"""US-PUB-02 — Progression view per skill area (embargo-aware)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    MarkingScheme,
    Pathway,
    PublicPortalConfig,
    ResultEntry,
    ResultPublication,
    ResultsConfig,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    Zone,
)
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_progression_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    with_portal_config: bool = True,
    with_results_config: bool = True,
    confirm_stage1: bool = True,
    release_final_results: bool = False,
) -> dict:
    """Two stages (Regional → Finals), two zones, shortlists + optional results release."""
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
        )
        session.add(skill)
        await session.flush()

        stage1 = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Regional",
            order=1,
            quota=1,
            quota_by_zone={str(zone_a.id): 1, str(zone_b.id): 1},
            min_score=50,
        )
        stage2 = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Finals",
            order=2,
            quota=1,
            quota_by_zone={str(zone_a.id): 1, str(zone_b.id): 1},
            min_score=50,
        )
        session.add_all([stage1, stage2])
        await session.flush()

        if with_portal_config:
            session.add(
                PublicPortalConfig(
                    competition_id=competition_id,
                    public_fields=["displayName", "skill", "stageStatus", "zone"],
                    rate_limit_per_minute=1000,
                    max_page_size=50,
                )
            )
        if with_results_config:
            session.add(
                ResultsConfig(
                    competition_id=competition_id,
                    release_at=datetime.utcnow() + timedelta(days=1),
                    audience=["PUBLIC", "COMPETITOR"],
                    neutral_status="IN_PROGRESS",
                    award_by_rank={"1": "GOLD", "2": "SILVER"},
                    default_outcome="FINALIST",
                )
            )

        # Competitors: A advances zone A; B waitlisted zone A; C advances zone B
        comps: dict[str, Competitor] = {}
        for label, zone, status in (
            ("A", zone_a, "ACTIVE_IN_STAGE"),
            ("B", zone_a, "ELIMINATED"),
            ("C", zone_b, "ACTIVE_IN_STAGE"),
        ):
            c = Competitor(
                competition_id=competition_id,
                skill_id=skill.id,
                zone_id=zone.id,
                ref_no=f"PROG-{label}-{uuid.uuid4().hex[:4]}",
                status=status,
                given_names=label,
                family_name="Prog",
                date_of_birth=date(2005, 1, 1),
                email=f"{label.lower()}@example.com",
                national_id=f"GHA-{label}11111111",
                nationality="GH",
                enrolment_attested=True,
                flags=[],
            )
            session.add(c)
            await session.flush()
            comps[label] = c

        if confirm_stage1:
            sl1 = Shortlist(
                competition_id=competition_id,
                stage_id=stage1.id,
                skill_id=skill.id,
                state="CONFIRMED",
                is_final_stage=False,
                confirmed_at=datetime.utcnow(),
            )
            session.add(sl1)
            await session.flush()
            for rank, (label, outcome, advanced) in enumerate(
                (("A", "ADVANCE", True), ("B", "WAITLIST", False), ("C", "ADVANCE", True)),
                start=1,
            ):
                session.add(
                    ShortlistEntry(
                        shortlist_id=sl1.id,
                        competitor_id=comps[label].id,
                        zone_id=comps[label].zone_id,
                        score=100 - rank,  # must never leak while embargoed
                        rank=rank,
                        outcome=outcome,
                        advanced=advanced,
                    )
                )

            # Final stage shortlist confirmed but results still embargoed unless released
            sl2 = Shortlist(
                competition_id=competition_id,
                stage_id=stage2.id,
                skill_id=skill.id,
                state="CONFIRMED",
                is_final_stage=True,
                confirmed_at=datetime.utcnow(),
            )
            session.add(sl2)
            await session.flush()
            session.add(
                ShortlistEntry(
                    shortlist_id=sl2.id,
                    competitor_id=comps["A"].id,
                    zone_id=zone_a.id,
                    score=95,
                    rank=1,
                    outcome="ADVANCE",
                    advanced=True,
                )
            )
            session.add(
                ShortlistEntry(
                    shortlist_id=sl2.id,
                    competitor_id=comps["C"].id,
                    zone_id=zone_b.id,
                    score=90,
                    rank=1,
                    outcome="ADVANCE",
                    advanced=True,
                )
            )

            pub = ResultPublication(
                competition_id=competition_id,
                skill_id=skill.id,
                state="RELEASED" if release_final_results else "EMBARGOED",
                release_at=datetime.utcnow() - timedelta(hours=1)
                if release_final_results
                else datetime.utcnow() + timedelta(days=1),
                audience=["PUBLIC", "COMPETITOR"],
                neutral_status="IN_PROGRESS",
                prepared_at=datetime.utcnow(),
                released_at=datetime.utcnow() if release_final_results else None,
            )
            session.add(pub)
            await session.flush()
            if release_final_results:
                session.add(
                    ResultEntry(
                        publication_id=pub.id,
                        competition_id=competition_id,
                        skill_id=skill.id,
                        competitor_id=comps["A"].id,
                        outcome="GOLD",
                        score=95,
                        rank=1,
                        version=1,
                        is_current=True,
                    )
                )
                session.add(
                    ResultEntry(
                        publication_id=pub.id,
                        competition_id=competition_id,
                        skill_id=skill.id,
                        competitor_id=comps["C"].id,
                        outcome="SILVER",
                        score=90,
                        rank=2,
                        version=1,
                        is_current=True,
                    )
                )

        await session.commit()
        return {
            "skill_id": skill.id,
            "stage1_id": stage1.id,
            "stage2_id": stage2.id,
            "zone_a_id": zone_a.id,
            "zone_b_id": zone_b.id,
            "competitors": {k: v.id for k, v in comps.items()},
        }


def _stages_for_zone(body: dict, zone_id: uuid.UUID) -> list[dict]:
    for block in body["byZone"]:
        if block["zoneId"] == str(zone_id):
            return block["stages"]
    raise AssertionError(f"zone {zone_id} missing from byZone")


@pytest.mark.asyncio
async def test_US_PUB_02_AC1_pipeline(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_progression_world(session_manager, competition_id)

    resp = await client.get(f"/public/competitions/{competition_id}/skills/{ctx['skill_id']}/progression")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "byZone" in body
    zone_ids = {z["zoneId"] for z in body["byZone"]}
    assert str(ctx["zone_a_id"]) in zone_ids
    assert str(ctx["zone_b_id"]) in zone_ids

    for zone_id in (ctx["zone_a_id"], ctx["zone_b_id"]):
        stages = _stages_for_zone(body, zone_id)
        assert len(stages) == 2
        assert stages[0]["stage"] == "Regional"
        assert stages[0]["order"] == 1
        assert stages[1]["stage"] == "Finals"
        assert stages[1]["order"] == 2

    # Missing portal config fails closed
    cycle2 = await _create_competition(client, auth_headers)
    ctx2 = await _seed_progression_world(session_manager, cycle2, with_portal_config=False)
    missing = await client.get(f"/public/competitions/{cycle2}/skills/{ctx2['skill_id']}/progression")
    assert missing.status_code == 409, missing.text
    assert missing.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_PUB_02_AC2_embargo_aware(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_progression_world(session_manager, competition_id, release_final_results=False)

    resp = await client.get(f"/public/competitions/{competition_id}/skills/{ctx['skill_id']}/progression")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dumped = resp.text.lower()

    # Final stage must be neutral — no scores/rankings/advancement leak
    for zone_id in (ctx["zone_a_id"], ctx["zone_b_id"]):
        finals = _stages_for_zone(body, zone_id)[1]
        assert finals["status"] == "IN_PROGRESS"
        assert finals.get("counts") in (None, {})
        assert "score" not in finals
        assert "rank" not in finals
        assert "advanced" not in (finals.get("counts") or {})

    dumped = resp.text.lower()
    assert "gold" not in dumped
    assert "silver" not in dumped
    assert '"score"' not in dumped
    assert '"rank"' not in dumped

    # Definition of Done — embargo state matches results service
    results = await client.get(f"/public/competitions/{competition_id}/results")
    assert results.status_code == 200, results.text
    assert results.json()["state"] == "EMBARGOED"
    assert results.json()["status"] == "IN_PROGRESS"
    assert results.json()["results"] == []
    finals = _stages_for_zone(body, ctx["zone_a_id"])[1]
    assert finals["status"] == results.json()["status"]


@pytest.mark.asyncio
async def test_US_PUB_02_AC3_released_update(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_progression_world(session_manager, competition_id, release_final_results=True)

    resp = await client.get(f"/public/competitions/{competition_id}/skills/{ctx['skill_id']}/progression")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Stage 1 (non-final, confirmed shortlist) shows advancement counts
    regional_a = _stages_for_zone(body, ctx["zone_a_id"])[0]
    assert regional_a["status"] == "RELEASED"
    assert regional_a["counts"]["advanced"] == 1
    assert regional_a["counts"]["waitlisted"] == 1

    regional_b = _stages_for_zone(body, ctx["zone_b_id"])[0]
    assert regional_b["status"] == "RELEASED"
    assert regional_b["counts"]["advanced"] == 1

    # Final stage released — advancement visible; still no raw score fields on progression
    finals_a = _stages_for_zone(body, ctx["zone_a_id"])[1]
    assert finals_a["status"] == "RELEASED"
    assert finals_a["counts"]["advanced"] >= 1
    assert "score" not in finals_a
    assert "rank" not in finals_a

    results = await client.get(f"/public/competitions/{competition_id}/results")
    assert results.json()["state"] == "RELEASED"
    assert len(results.json()["results"]) >= 1
