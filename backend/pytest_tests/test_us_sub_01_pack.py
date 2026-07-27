"""US-SUB-01 pack ACs + US-SUB-03 scheme documents."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AgeRule, MarkingScheme, Pathway, Skill, Stage, Zone
from app.services.storage import EICAR_SIGNATURE
from pytest_tests.conftest import create_competitor_account, competition_payload, login_as


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_stage(
    session_manager: DBManager, competition_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
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
            max_age=25,
            open_category_enabled=False,
            capacity=40,
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
            quota=20,
            quota_by_zone={str(zone.id): 20},
        )
        session.add(stage)
        await session.commit()
        return stage.id, scheme.id


def _exercise_body(scheme_id: uuid.UUID) -> dict:
    return {
        "title": "Regional challenge",
        "brief": "Build a web page",
        "deliverables": [
            {
                "code": "main",
                "label": "Main package",
                "required": True,
                "allowedTypes": ["pdf", "zip"],
                "maxSizeBytes": 20_000_000,
            }
        ],
        "schemeId": str(scheme_id),
        "latePolicy": "block",
    }


_PDF_BYTES = b"%PDF-1.4 minimal pack content"


@pytest.mark.asyncio
async def test_US_SUB_01_AC8_upload_pack(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    put = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text

    resp = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("challenge.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["packFileName"] == "challenge.pdf"
    assert body["packScanStatus"] == "CLEAN"


@pytest.mark.asyncio
async def test_US_SUB_01_AC9_reject_bad_pack(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    # Seed a clean pack first
    ok = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("ok.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    assert ok.status_code == 200

    bad = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "FILE_TYPE"

    infected = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("evil.pdf", EICAR_SIGNATURE + b"%PDF", "application/pdf")},
        headers=auth_headers,
    )
    assert infected.status_code == 400
    assert infected.json()["error"]["code"] == "FILE_INFECTED"

    # Prior pack unchanged
    got = await client.get(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise", headers=auth_headers
    )
    assert got.json()["packFileName"] == "ok.pdf"


@pytest.mark.asyncio
async def test_US_SUB_01_AC10_download_published_pack(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("challenge.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    pub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub.status_code == 200, pub.text

    user, password = await create_competitor_account(session_manager)
    # Bind competitor row so download eligibility passes
    async with session_manager.session() as session:
        from app.models import Competitor, Institution
        from pytest_tests.conftest import region_id_by_name

        region_id = await region_id_by_name(session_manager)
        stage = await session.get(Stage, stage_id)
        assert stage is not None
        inst = Institution(name=f"P {uuid.uuid4().hex[:6]}", region_id=region_id)
        session.add(inst)
        await session.flush()
        zone = (
            await session.execute(
                __import__("sqlalchemy").select(Zone).where(Zone.competition_id == competition_id)
            )
        ).scalar_one()
        session.add(
            Competitor(
                competition_id=competition_id,
                user_id=user.id,
                skill_id=stage.skill_id,
                zone_id=zone.id,
                region_id=region_id,
                institution_id=inst.id,
                ref_no=f"WSG-T-{uuid.uuid4().hex[:6]}",
                status="REGISTERED",
                given_names="A",
                family_name="B",
                date_of_birth=__import__("datetime").date(2005, 1, 1),
                email=user.email,
            )
        )
        await session.commit()

    comp = await login_as(client, user.email, password)
    dl = await client.get(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack", headers=comp
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == _PDF_BYTES


@pytest.mark.asyncio
async def test_US_SUB_01_AC11_pack_blocked_when_unpublished(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    stage_id, scheme_id = await _seed_stage(session_manager, competition_id)
    await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json=_exercise_body(scheme_id),
        headers=auth_headers,
    )
    await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack",
        files={"file": ("challenge.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    user, password = await create_competitor_account(session_manager)
    comp = await login_as(client, user.email, password)
    dl = await client.get(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise/pack", headers=comp
    )
    assert dl.status_code == 403
    assert dl.json()["error"]["code"] in {"EXERCISE_NOT_PUBLISHED", "UNAUTHORIZED"}


@pytest.mark.asyncio
async def test_US_SUB_03_AC1_create_scheme(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    resp = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": f"Scheme {uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    listed = await client.get(f"/competitions/{competition_id}/marking-schemes", headers=auth_headers)
    assert listed.status_code == 200
    assert any(s["schemeId"] == resp.json()["schemeId"] for s in listed.json())


@pytest.mark.asyncio
async def test_US_SUB_03_AC2_upload_scheme_document(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    created = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": f"Doc {uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    sid = created.json()["schemeId"]
    resp = await client.post(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document",
        files={"file": ("rubric.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["documentFileName"] == "rubric.pdf"
    assert resp.json()["documentScanStatus"] == "CLEAN"


@pytest.mark.asyncio
async def test_US_SUB_03_AC3_reject_bad_document(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    created = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": f"Bad {uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    sid = created.json()["schemeId"]
    await client.post(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document",
        files={"file": ("ok.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    bad = await client.post(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document",
        files={"file": ("x.csv", b"a,b", "text/csv")},
        headers=auth_headers,
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "FILE_TYPE"


@pytest.mark.asyncio
async def test_US_SUB_03_AC4_expert_download(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    from app.core.security import get_password_hash
    from app.models import User, UserRole

    competition_id = await _create_draft_cycle(client, auth_headers)
    created = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": f"Exp {uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    sid = created.json()["schemeId"]
    await client.post(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document",
        files={"file": ("rubric.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )

    async with session_manager.session() as session:
        email = f"exp-{uuid.uuid4().hex[:8]}@example.com"
        expert = User(
            email=email,
            full_name="Expert",
            hashed_password=get_password_hash("ExpertPass1!"),
            role=UserRole.EXPERT,
            is_active=True,
        )
        session.add(expert)
        await session.commit()

    exp_headers = await login_as(client, email, "ExpertPass1!")
    dl = await client.get(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document", headers=exp_headers
    )
    # MVP: experts with role may download when document exists (assignment check soft)
    assert dl.status_code == 200, dl.text
    assert dl.content == _PDF_BYTES


@pytest.mark.asyncio
async def test_US_SUB_03_AC5_competitor_denied(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    created = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": f"Deny {uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    sid = created.json()["schemeId"]
    await client.post(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document",
        files={"file": ("rubric.pdf", _PDF_BYTES, "application/pdf")},
        headers=auth_headers,
    )
    user, password = await create_competitor_account(session_manager)
    comp = await login_as(client, user.email, password)
    dl = await client.get(
        f"/competitions/{competition_id}/marking-schemes/{sid}/document", headers=comp
    )
    assert dl.status_code == 401
    assert dl.json()["error"]["code"] == "UNAUTHORIZED"
