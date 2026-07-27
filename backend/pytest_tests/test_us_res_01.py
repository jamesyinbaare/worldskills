"""US-RES-01 — Publish results under embargo and issue certificates."""

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
    Certificate,
    CertificateTemplate,
    Competitor,
    MarkingScheme,
    Pathway,
    ResultEntry,
    ResultPublication,
    ResultsConfig,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    User,
    UserRole,
    Zone,
)
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_results_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    release_at: datetime | None = None,
    with_templates: bool = True,
    with_config: bool = True,
    second_skill: bool = False,
) -> dict:
    """Finalists A(GOLD), B(SILVER) with confirmed final shortlist + results config."""
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
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

        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Finals",
            order=1,
            quota=2,
            quota_by_zone={str(zone.id): 2},
            min_score=50,
        )
        session.add(stage)
        await session.flush()

        competitors: dict[str, Competitor] = {}
        scores = {"A": 95, "B": 88, "C": 70}
        for label, score in scores.items():
            status = "FINALIST" if label in ("A", "B") else "ACTIVE_IN_STAGE"
            comp = Competitor(
                competition_id=competition_id,
                skill_id=skill.id,
                zone_id=zone.id,
                ref_no=f"REF-{label}-{uuid.uuid4().hex[:4]}",
                status=status,
                eligibility_status="ELIGIBLE",
                given_names=label,
                family_name="Comp",
            )
            session.add(comp)
            await session.flush()
            competitors[label] = comp

        shortlist = Shortlist(
            competition_id=competition_id,
            stage_id=stage.id,
            skill_id=skill.id,
            state="CONFIRMED",
            is_final_stage=True,
            confirmed_at=datetime.utcnow(),
        )
        session.add(shortlist)
        await session.flush()

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

        skill2_id = None
        if second_skill:
            skill2 = Skill(
                competition_id=competition_id,
                name="Cloud Computing",
                age_rule_id=age.id,
                pathway_id=path.id,
            scheme_id=scheme.id,
                capacity=20,
                active=True,
            )
            session.add(skill2)
            await session.flush()
            skill2_id = skill2.id
            stage2 = Stage(
                competition_id=competition_id,
                skill_id=skill2.id,
                name="Finals",
                order=1,
                quota=1,
                quota_by_zone={str(zone.id): 1},
                min_score=50,
            )
            session.add(stage2)
            await session.flush()
            comp_d = Competitor(
                competition_id=competition_id,
                skill_id=skill2.id,
                zone_id=zone.id,
                ref_no=f"REF-D-{uuid.uuid4().hex[:4]}",
                status="FINALIST",
                eligibility_status="ELIGIBLE",
                given_names="D",
                family_name="Comp",
            )
            session.add(comp_d)
            await session.flush()
            competitors["D"] = comp_d
            sl2 = Shortlist(
                competition_id=competition_id,
                stage_id=stage2.id,
                skill_id=skill2.id,
                state="CONFIRMED",
                is_final_stage=True,
                confirmed_at=datetime.utcnow(),
            )
            session.add(sl2)
            await session.flush()
            session.add(
                ShortlistEntry(
                    shortlist_id=sl2.id,
                    competitor_id=comp_d.id,
                    zone_id=zone.id,
                    score=91,
                    rank=1,
                    outcome="ADVANCE",
                    advanced=True,
                )
            )

        if with_config:
            session.add(
                ResultsConfig(
                    competition_id=competition_id,
                    release_at=release_at or (datetime.utcnow() + timedelta(days=7)),
                    audience=["PUBLIC", "COMPETITOR"],
                    neutral_status="IN_PROGRESS",
                    award_by_rank={"1": "GOLD", "2": "SILVER", "3": "BRONZE"},
                    default_outcome="FINALIST",
                )
            )

        if with_templates:
            for outcome, body in [
                ("GOLD", "Certificate of Gold for {{name}}"),
                ("SILVER", "Certificate of Silver for {{name}}"),
                ("BRONZE", "Certificate of Bronze for {{name}}"),
                ("FINALIST", "Certificate of Finalist for {{name}}"),
            ]:
                session.add(
                    CertificateTemplate(
                        competition_id=competition_id,
                        outcome=outcome,
                        body=body,
                        language="en",
                    )
                )

        competitor_user = User(
            email=f"comp-res-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Competitor A",
            hashed_password=get_password_hash("comp-pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor_user)
        await session.flush()
        competitors["A"].user_id = competitor_user.id

        await session.commit()
        return {
            "zone_id": zone.id,
            "skill_id": skill.id,
            "skill2_id": skill2_id,
            "stage_id": stage.id,
            "competitors": {k: v.id for k, v in competitors.items()},
            "competitor_user": competitor_user,
            "competitor_email": competitor_user.email,
        }


async def _comp_headers(client: AsyncClient, email: str) -> dict[str, str]:
    login = await client.post("/auth/login", json={"email": email, "password": "comp-pass-123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_RES_01_AC1_embargo_holds(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id)

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers
    )
    assert prep.status_code == 200, prep.text
    assert prep.json()["state"] == "EMBARGOED"

    public = await client.get(f"/public/competitions/{competition_id}/results")
    assert public.status_code == 200, public.text
    pub_body = public.json()
    assert pub_body["state"] == "EMBARGOED"
    assert pub_body["status"] == "IN_PROGRESS"
    assert pub_body.get("results") in (None, [])
    # No rankings/scores leaking
    assert not pub_body.get("results")
    for key in ("rankings", "scores", "certificates"):
        assert key not in pub_body or not pub_body[key]

    comp_headers = await _comp_headers(client, ctx["competitor_email"])
    mine = await client.get(f"/competitions/{competition_id}/results/me", headers=comp_headers)
    assert mine.status_code == 200, mine.text
    mine_body = mine.json()
    assert mine_body["state"] == "EMBARGOED"
    assert mine_body["status"] == "IN_PROGRESS"
    assert mine_body.get("result") is None
    assert mine_body.get("certificate") is None


@pytest.mark.asyncio
async def test_US_RES_01_AC2_release(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(
        session_manager,
        competition_id,
        release_at=datetime.utcnow() + timedelta(days=30),
    )

    await client.post(f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers)

    # Too early without manual → stays embargoed
    early = await client.post(
        f"/competitions/{competition_id}/results:release",
        json={},
        headers=auth_headers,
    )
    assert early.status_code == 409, early.text
    assert early.json()["error"]["code"] == "EMBARGO_ACTIVE"

    public_early = await client.get(f"/public/competitions/{competition_id}/results")
    assert public_early.json()["state"] == "EMBARGOED"

    release = await client.post(
        f"/competitions/{competition_id}/results:release",
        json={"manual": True},
        headers=auth_headers,
    )
    assert release.status_code == 200, release.text
    body = release.json()
    assert body["releasedAt"] is not None

    public = await client.get(f"/public/competitions/{competition_id}/results")
    assert public.status_code == 200, public.text
    pub = public.json()
    assert pub["state"] == "RELEASED"
    assert len(pub["results"]) >= 2
    by_comp = {r["competitorId"]: r for r in pub["results"]}
    assert by_comp[str(ctx["competitors"]["A"])]["outcome"] == "GOLD"
    assert by_comp[str(ctx["competitors"]["A"])]["rank"] == 1
    assert by_comp[str(ctx["competitors"]["B"])]["outcome"] == "SILVER"

    async with session_manager.session() as session:
        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.competition_id == competition_id,
                    AuditEvent.action == "RESULTS_RELEASE",
                )
            )
        ).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_US_RES_01_AC3_certificate_generation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id)

    await client.post(f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers)
    release = await client.post(
        f"/competitions/{competition_id}/results:release",
        json={"manual": True},
        headers=auth_headers,
    )
    assert release.status_code == 200, release.text

    async with session_manager.session() as session:
        certs = (
            await session.execute(
                select(Certificate).where(
                    Certificate.competition_id == competition_id,
                    Certificate.is_current.is_(True),
                )
            )
        ).scalars().all()
        assert len(certs) >= 2
        by_comp = {c.competitor_id: c for c in certs}
        gold = by_comp[ctx["competitors"]["A"]]
        silver = by_comp[ctx["competitors"]["B"]]
        assert gold.outcome == "GOLD"
        assert "Gold" in (gold.rendered_body or "")
        assert silver.outcome == "SILVER"
        assert "Silver" in (silver.rendered_body or "")

    public = await client.get(f"/public/competitions/{competition_id}/results")
    assert all(r.get("certificateId") for r in public.json()["results"])


@pytest.mark.asyncio
async def test_US_RES_01_AC4_correction(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id)

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers
    )
    assert prep.status_code == 200, prep.text
    await client.post(
        f"/competitions/{competition_id}/results:release",
        json={"manual": True},
        headers=auth_headers,
    )

    async with session_manager.session() as session:
        entry = (
            await session.execute(
                select(ResultEntry).where(
                    ResultEntry.competitor_id == ctx["competitors"]["A"],
                    ResultEntry.is_current.is_(True),
                )
            )
        ).scalar_one()
        rid = entry.id

    corrected = await client.post(
        f"/results/{rid}:correct",
        json={"changes": {"outcome": "SILVER", "rank": 2, "score": 87}, "reason": "Recount"},
        headers=auth_headers,
    )
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body["version"] == 2
    assert body["resultId"] != str(rid)

    async with session_manager.session() as session:
        old = await session.get(ResultEntry, rid)
        assert old is not None
        assert old.is_current is False
        new = await session.get(ResultEntry, uuid.UUID(body["resultId"]))
        assert new is not None
        assert new.is_current is True
        assert new.version == 2
        assert new.outcome == "SILVER"
        assert new.supersedes_id == rid

        certs = (
            await session.execute(
                select(Certificate).where(Certificate.competitor_id == ctx["competitors"]["A"])
            )
        ).scalars().all()
        current = [c for c in certs if c.is_current]
        assert len(current) == 1
        assert current[0].outcome == "SILVER"
        assert current[0].version == 2

        audits = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "RESULTS_CORRECT",
                    AuditEvent.entity_id == body["resultId"],
                )
            )
        ).scalars().all()
        assert len(audits) >= 1
        assert audits[0].reason == "Recount"


@pytest.mark.asyncio
async def test_US_RES_01_template_missing(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed_results_world(session_manager, competition_id, with_templates=False)

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers
    )
    assert prep.status_code == 422, prep.text
    assert prep.json()["error"]["code"] == "TEMPLATE_MISSING"


@pytest.mark.asyncio
async def test_US_RES_01_config_incomplete(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed_results_world(session_manager, competition_id, with_config=False)

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers
    )
    assert prep.status_code == 409, prep.text
    assert prep.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_RES_01_scheduled_release_when_due(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed_results_world(
        session_manager,
        competition_id,
        release_at=datetime.utcnow() - timedelta(minutes=5),
    )

    await client.post(f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers)
    release = await client.post(
        f"/competitions/{competition_id}/results:release",
        json={},
        headers=auth_headers,
    )
    assert release.status_code == 200, release.text
    assert release.json()["releasedAt"] is not None


@pytest.mark.asyncio
async def test_US_RES_01_partial_skill_release(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id, second_skill=True)

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare",
        json={"skillId": str(ctx["skill_id"])},
        headers=auth_headers,
    )
    assert prep.status_code == 200, prep.text

    await client.post(
        f"/competitions/{competition_id}/results:release",
        json={"manual": True, "skillId": str(ctx["skill_id"])},
        headers=auth_headers,
    )

    public = await client.get(f"/public/competitions/{competition_id}/results")
    body = public.json()
    # Cycle-level view may show per-skill states; released skill has outcomes
    released = [r for r in body.get("results", []) if r.get("skillId") == str(ctx["skill_id"])]
    assert len(released) >= 2
    # Skill 2 not prepared — must not appear with scores
    skill2_rows = [r for r in body.get("results", []) if r.get("skillId") == str(ctx["skill2_id"])]
    assert skill2_rows == []


@pytest.mark.asyncio
async def test_US_RES_01_admin_list_results(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id)

    empty = await client.get(
        f"/competitions/{competition_id}/results",
        headers=auth_headers,
    )
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    await client.post(
        f"/competitions/{competition_id}/results:prepare",
        json={},
        headers=auth_headers,
    )

    listed = await client.get(
        f"/competitions/{competition_id}/results",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) >= 1
    assert all(r["publicationState"] == "EMBARGOED" for r in rows)

    by_skill = await client.get(
        f"/competitions/{competition_id}/results",
        params={"skillId": str(ctx["skill_id"])},
        headers=auth_headers,
    )
    assert by_skill.status_code == 200, by_skill.text
    assert len(by_skill.json()) >= 1
    assert all(r["skillId"] == str(ctx["skill_id"]) for r in by_skill.json())


@pytest.mark.asyncio
async def test_US_RES_01_results_config_upsert(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed_results_world(session_manager, competition_id, with_config=False, with_templates=False)

    missing = await client.get(
        f"/competitions/{competition_id}/results-config", headers=auth_headers
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["configured"] is False

    release_at = (datetime.utcnow() + timedelta(days=1)).isoformat()
    saved = await client.put(
        f"/competitions/{competition_id}/results-config",
        json={
            "releaseAt": release_at,
            "audience": ["PUBLIC", "COMPETITOR"],
            "neutralStatus": "IN_PROGRESS",
            "awardByRank": {"1": "GOLD", "2": "SILVER", "3": "BRONZE"},
            "defaultOutcome": "FINALIST",
            "ensureTemplates": True,
        },
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert "PUBLIC" in body["audience"]

    # Prepare should work after config + auto templates
    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare", json={}, headers=auth_headers
    )
    assert prep.status_code == 200, prep.text


@pytest.mark.asyncio
async def test_US_RES_01_stage_prepare_and_release(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_results_world(session_manager, competition_id)

    # Ensure ADVANCE/WAITLIST templates exist via config upsert
    await client.put(
        f"/competitions/{competition_id}/results-config",
        json={
            "releaseAt": (datetime.utcnow() + timedelta(days=3)).isoformat(),
            "audience": ["PUBLIC", "COMPETITOR"],
            "ensureTemplates": True,
        },
        headers=auth_headers,
    )

    prep = await client.post(
        f"/competitions/{competition_id}/results:prepare",
        json={"stageId": str(ctx["stage_id"])},
        headers=auth_headers,
    )
    assert prep.status_code == 200, prep.text
    assert prep.json()["stageId"] == str(ctx["stage_id"])
    assert prep.json()["entryCount"] >= 2

    release = await client.post(
        f"/competitions/{competition_id}/results:release",
        json={"manual": True, "stageId": str(ctx["stage_id"])},
        headers=auth_headers,
    )
    assert release.status_code == 200, release.text
    assert release.json()["certificateCount"] >= 2

    listed = await client.get(
        f"/competitions/{competition_id}/results",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert any(r.get("stageId") == str(ctx["stage_id"]) for r in rows)
    assert all(
        r["publicationState"] == "RELEASED"
        for r in rows
        if r.get("stageId") == str(ctx["stage_id"])
    )
