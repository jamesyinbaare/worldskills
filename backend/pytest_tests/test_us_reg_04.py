"""US-REG-04 — Institution on-behalf registration + school-optional competitor path."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    CompetitionStatus,
    Institution,
    InstitutionCompetitionMembership,
    MarkingScheme,
    NominationLimit,
    Pathway,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    Zone,
)
from pytest_tests.conftest import (
    create_competitor_account,
    competition_payload,
    login_as,
    map_region_to_zone,
    region_id_by_name,
)

_PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
).decode()

DEFAULT_FIELDS = [
    {"name": "givenNames", "type": "string", "required": True, "maxLength": 100},
    {"name": "familyName", "type": "string", "required": True, "maxLength": 100},
    {"name": "dateOfBirth", "type": "date", "required": True},
    {"name": "email", "type": "email", "required": True},
    {"name": "mobile", "type": "phone", "required": True},
    {"name": "nationalId", "type": "string", "required": True},
    {"name": "institutionId", "type": "uuid", "required": True},
    {"name": "zoneId", "type": "uuid", "required": True},
    {"name": "skillIds", "type": "array", "required": True},
    {"name": "declarationAccepted", "type": "boolean", "required": True},
    {"name": "photo", "type": "file", "required": True},
]


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_reg(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    activate: bool = True,
) -> dict[str, uuid.UUID]:
    region_id = await region_id_by_name(session_manager, "Greater Accra")
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
            school_quota=5,
        )
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        inst = Institution(
            code=f"REG-{uuid.uuid4().hex[:8].upper()}",
            name=f"Reg Inst {uuid.uuid4().hex[:6]}",
            region_id=region_id,
            active=True,
        )
        other = Institution(
            code=f"OTH-{uuid.uuid4().hex[:8].upper()}",
            name=f"Other Inst {uuid.uuid4().hex[:6]}",
            region_id=region_id,
            active=True,
        )
        session.add_all([skill, zone, inst, other])
        await session.flush()
        session.add(
            InstitutionCompetitionMembership(
                competition_id=competition_id,
                institution_id=inst.id,
                zone_id=zone.id,
            )
        )
        session.add(
            NominationLimit(
                competition_id=competition_id,
                institution_id=inst.id,
                skill_id=skill.id,
                max_nominations=5,
            )
        )
        now = datetime.utcnow()
        session.add(
            RegistrationWindow(
                competition_id=competition_id,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
            )
        )
        session.add(
            RegistrationFormDefinition(
                competition_id=competition_id,
                fields=DEFAULT_FIELDS,
                max_skills=1,
                photo_max_mb=2,
                photo_formats=["image/jpeg", "image/png"],
                national_id_pattern=r"GHA-\d{9}",
                minor_age_under=18,
                minor_reference_date=date(2026, 1, 1),
            )
        )
        if activate:
            from app.models import Competition

            cycle = await session.get(Competition, competition_id)
            assert cycle is not None
            cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        out = {
            "skill_id": skill.id,
            "zone_id": zone.id,
            "institution_id": inst.id,
            "other_institution_id": other.id,
            "region_id": region_id,
            "school_code": inst.code,
        }
    await map_region_to_zone(session_manager, competition_id, region_id, out["zone_id"])
    return out


def _payload(ctx: dict[str, uuid.UUID], **overrides: object) -> dict:
    base: dict = {
        "givenNames": "Ama",
        "familyName": "Mensah",
        "gender": "Female",
        "dateOfBirth": "2005-03-15",
        "email": f"ama-{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+233241234567",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "hasPassport": False,
        "institutionId": str(ctx["institution_id"]),
        "skillIds": [str(ctx["skill_id"])],
        "declarationAccepted": True,
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
        "captchaToken": "ok",
    }
    base.update(overrides)
    return base


async def _claim_institution(
    client: AsyncClient, session_manager: DBManager, school_code: str
) -> dict[str, str]:
    email = f"head-{uuid.uuid4().hex[:8]}@school.edu"
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": email,
            "fullName": "School Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school_code,
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 201, resp.text
    return await login_as(client, email, "Institution1!")


@pytest.mark.asyncio
async def test_US_REG_04_AC1_institution_registers_on_behalf(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    inst_headers = await _claim_institution(
        client, session_manager, str(ctx["school_code"])
    )

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, institutionId=None),
        headers={**inst_headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    async with session_manager.session() as session:
        row = (
            await session.execute(
                select(Competitor).where(Competitor.id == uuid.UUID(body["competitorId"]))
            )
        ).scalar_one()
        assert row.user_id is None
        assert row.institution_id == ctx["institution_id"]


@pytest.mark.asyncio
async def test_US_REG_04_institution_registers_minor_without_guardian_consent(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Institution on-behalf registration skips guardian consent for minors."""
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    inst_headers = await _claim_institution(
        client, session_manager, str(ctx["school_code"])
    )

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            dateOfBirth="2010-06-15",  # minor vs minor_reference_date 2026-01-01
        ),
        headers={**inst_headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert "Guardian consent" not in (body.get("message") or "")

    async with session_manager.session() as session:
        row = (
            await session.execute(
                select(Competitor).where(Competitor.id == uuid.UUID(body["competitorId"]))
            )
        ).scalar_one()
        assert row.status == "PENDING_REVIEW"
        assert "CONSENT_PENDING" not in (row.flags or [])
        assert row.consent_participation_at is None


@pytest.mark.asyncio
async def test_US_REG_04_AC2_cannot_register_other_school(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    inst_headers = await _claim_institution(
        client, session_manager, str(ctx["school_code"])
    )

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, institutionId=str(ctx["other_institution_id"])),
        headers=inst_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_US_REG_04_AC3_competitor_without_school(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    user, password = await create_competitor_account(session_manager)
    comp = await login_as(client, user.email, password)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            regionId=str(ctx["region_id"]),
        ),
        headers={**comp, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    async with session_manager.session() as session:
        row = (
            await session.execute(
                select(Competitor).where(Competitor.id == uuid.UUID(body["competitorId"]))
            )
        ).scalar_one()
        assert row.user_id == user.id
        assert row.institution_id is None
        assert row.region_id == ctx["region_id"]


@pytest.mark.asyncio
async def test_US_REG_04_AC4_competitor_no_school_no_region(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    user, password = await create_competitor_account(session_manager)
    comp = await login_as(client, user.email, password)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, institutionId=None),
        headers=comp,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REGION_REQUIRED"


@pytest.mark.asyncio
async def test_US_REG_04_AC5_open_cycles_and_available_skills(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    user, password = await create_competitor_account(session_manager)
    comp = await login_as(client, user.email, password)

    open_cycles = await client.get("/competitions:open-for-registration", headers=comp)
    assert open_cycles.status_code == 200, open_cycles.text
    ids = {c["competitionId"] for c in open_cycles.json()}
    assert str(competition_id) in ids

    skills = await client.get(f"/competitions/{competition_id}/skills:available", headers=comp)
    assert skills.status_code == 200, skills.text
    skill_ids = {s["skillId"] for s in skills.json()}
    assert str(ctx["skill_id"]) in skill_ids

    # Public discovery — available without auth (and to any role)
    anon = await client.get("/competitions:open-for-registration")
    assert anon.status_code == 200, anon.text
    assert str(competition_id) in {c["competitionId"] for c in anon.json()}
