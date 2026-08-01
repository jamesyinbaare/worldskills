"""Institution portal roster/quotas + registration gender + school nomination quotas."""

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
    competition_payload,
    create_competitor_account,
    enable_institution_registration,
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


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    limit: int = 1,
) -> dict[str, uuid.UUID | str]:
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
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
            school_quota=limit,
        )
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        inst = Institution(
            code=f"PORT-{uuid.uuid4().hex[:8].upper()}",
            name=f"Portal Inst {uuid.uuid4().hex[:6]}",
            region_id=region_id,
            active=True,
        )
        session.add_all([skill, zone, inst])
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
                max_nominations=limit,
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
                fields=[
                    {"name": "givenNames", "type": "string", "required": True},
                    {"name": "familyName", "type": "string", "required": True},
                    {"name": "dateOfBirth", "type": "date", "required": True},
                    {"name": "email", "type": "email", "required": True},
                    {"name": "mobile", "type": "phone", "required": True},
                    {"name": "nationalId", "type": "string", "required": True},
                    {"name": "skillIds", "type": "array", "required": True},
                    {"name": "declarationAccepted", "type": "boolean", "required": True},
                    {"name": "photo", "type": "file", "required": True},
                ],
                max_skills=1,
                photo_max_mb=2,
                photo_formats=["image/jpeg", "image/png"],
                national_id_pattern=r"GHA-\d{9}",
                minor_age_under=18,
                minor_reference_date=date(2026, 1, 1),
            )
        )
        from app.models import Competition

        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        out = {
            "skill_id": skill.id,
            "zone_id": zone.id,
            "institution_id": inst.id,
            "region_id": region_id,
            "school_code": inst.code,
        }
    await map_region_to_zone(session_manager, competition_id, region_id, out["zone_id"])
    return out


def _payload(ctx: dict[str, uuid.UUID | str], **overrides: object) -> dict:
    base: dict = {
        "givenNames": "Ama",
        "familyName": "Mensah",
        "gender": "Female",
        "dateOfBirth": "2005-03-15",
        "email": f"ama-{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+233241234567",
        "whatsapp": "+233241234567",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "idDocumentKind": "GHANA_CARD",
        "affiliationType": "school",
        "organizationPhone": "+233302123456",
        "organizationEmail": "school@example.com",
        "heardAbout": "Newspaper",
        "guardianName": "Kofi Mensah",
        "guardianPhone": "+233241000111",
        "skillIds": [str(ctx["skill_id"])],
        "coach": {
            "surname": "Asante",
            "firstName": "Kojo",
            "contactNumber": "+233201112233",
            "email": "coach@example.com",
            "whatsapp": "+233201112233",
            "dateOfBirth": "1985-04-12",
        },
        "declarationAccepted": True,
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
        "captchaToken": "ok",
        "hasPassport": False,
    }
    base.update(overrides)
    return base


async def _claim_institution(
    client: AsyncClient, session_manager: DBManager, school_code: str
) -> dict[str, str]:
    await enable_institution_registration(session_manager)
    email = f"head-{uuid.uuid4().hex[:8]}@school.edu"
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": email,
            "fullName": "School Head",
            "phoneNumber": f"055{uuid.uuid4().int % 10**7:07d}",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school_code,
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 201, resp.text
    return await login_as(client, email, "Institution1!")


@pytest.mark.asyncio
async def test_registration_requires_male_or_female_gender(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=5)
    user, password = await create_competitor_account(session_manager)
    headers = await login_as(client, user.email, password)

    form = await client.get(
        f"/competitions/{competition_id}/registration-form", headers=headers
    )
    assert form.status_code == 200, form.text
    names = [f["name"] for f in form.json()["fields"]]
    assert "gender" in names
    gender_field = next(f for f in form.json()["fields"] if f["name"] == "gender")
    assert gender_field["allowedValues"] == ["Male", "Female"]

    bad = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, gender="Other", institutionId=str(ctx["institution_id"])),
        headers={**headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert bad.status_code == 422, bad.text
    assert any(f["name"] == "gender" for f in bad.json()["error"]["fields"])

    ok = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, gender="Male", institutionId=str(ctx["institution_id"])),
        headers={**headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert ok.status_code == 201, ok.text
    async with session_manager.session() as session:
        row = (
            await session.execute(
                select(Competitor).where(
                    Competitor.id == uuid.UUID(ok.json()["competitorId"])
                )
            )
        ).scalar_one()
        assert row.gender == "Male"


@pytest.mark.asyncio
async def test_institution_registration_enforces_skill_quota(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=1)
    inst_headers = await _claim_institution(client, session_manager, str(ctx["school_code"]))

    first = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx),
        headers={**inst_headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, email=f"two-{uuid.uuid4().hex[:6]}@example.com"),
        headers={**inst_headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "NOMINATION_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_institution_portal_roster_and_quotas(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=3)
    inst_headers = await _claim_institution(client, session_manager, str(ctx["school_code"]))

    created = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, gender="Female"),
        headers={**inst_headers, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert created.status_code == 201, created.text

    roster = await client.get("/institutions/me/registrations", headers=inst_headers)
    assert roster.status_code == 200, roster.text
    rows = roster.json()
    assert len(rows) == 1
    assert rows[0]["competitionId"] == str(competition_id)
    assert rows[0]["competitionStatus"] == "ACTIVE"
    assert rows[0]["gender"] == "Female"
    assert rows[0]["skillId"] == str(ctx["skill_id"])

    quotas = await client.get(
        f"/competitions/{competition_id}/nomination-quotas",
        headers=inst_headers,
    )
    assert quotas.status_code == 200, quotas.text
    body = quotas.json()
    assert body["institutionId"] == str(ctx["institution_id"])
    assert len(body["quotas"]) == 1
    assert body["quotas"][0]["max"] == 3
    assert body["quotas"][0]["used"] == 1
    assert body["quotas"][0]["remaining"] == 2
    assert body["quotas"][0]["configured"] is True


@pytest.mark.asyncio
async def test_institution_competitions_catalog_excludes_draft(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    active_competition_id = await _create_competition(client, auth_headers)
    closed_competition_id = await _create_competition(client, auth_headers)
    draft_competition_id = await _create_competition(client, auth_headers)

    active_ctx = await _seed(session_manager, active_competition_id, limit=2)
    await _seed(session_manager, closed_competition_id, limit=2)

    async with session_manager.session() as session:
        from app.models import Competition

        closed_cycle = await session.get(Competition, closed_competition_id)
        draft_cycle = await session.get(Competition, draft_competition_id)
        assert closed_cycle is not None
        assert draft_cycle is not None
        closed_cycle.status = CompetitionStatus.CLOSED
        draft_cycle.status = CompetitionStatus.DRAFT
        await session.commit()

    inst_headers = await _claim_institution(client, session_manager, str(active_ctx["school_code"]))

    resp = await client.get("/institutions/me/competitions", headers=inst_headers)
    assert resp.status_code == 200, resp.text

    rows = resp.json()
    ids = {row["competitionId"] for row in rows}
    assert str(active_competition_id) in ids
    assert str(closed_competition_id) in ids
    assert str(draft_competition_id) not in ids


@pytest.mark.asyncio
async def test_institution_competitions_catalog_requires_institution_role(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/institutions/me/competitions", headers=auth_headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_upsert_school_quotas(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=1)

    resp = await client.put(
        f"/admin/competitions/{competition_id}/school-quotas",
        json={
            "limits": [
                {"skillId": str(ctx["skill_id"]), "maxNominations": 7},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["competitionId"] == str(competition_id)
    assert body["quotas"][0]["max"] == 7
    assert body["quotas"][0]["configured"] is True

    got = await client.get(
        f"/admin/competitions/{competition_id}/school-quotas",
        headers=auth_headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["quotas"][0]["max"] == 7


@pytest.mark.asyncio
async def test_admin_upsert_nomination_limits(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=1)

    resp = await client.put(
        f"/admin/competitions/{competition_id}/institutions/{ctx['institution_id']}/nomination-limits",
        json={
            "zoneId": str(ctx["zone_id"]),
            "limits": [
                {"skillId": str(ctx["skill_id"]), "maxNominations": 7},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["limits"][0]["max"] == 7


@pytest.mark.asyncio
async def test_admin_get_nomination_limits(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=3)

    resp = await client.get(
        f"/admin/competitions/{competition_id}/institutions/{ctx['institution_id']}/nomination-limits",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["competitionId"] == str(competition_id)
    assert body["institutionId"] == str(ctx["institution_id"])
    assert body["zoneId"] == str(ctx["zone_id"])
    assert len(body["limits"]) == 1
    assert body["limits"][0]["skillId"] == str(ctx["skill_id"])
    assert body["limits"][0]["max"] == 3
    assert body["limits"][0]["configured"] is True


@pytest.mark.asyncio
async def test_admin_get_nomination_limits_competition_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=1)
    missing = uuid.uuid4()

    resp = await client.get(
        f"/admin/competitions/{missing}/institutions/{ctx['institution_id']}/nomination-limits",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "COMPETITION_NOT_FOUND"


@pytest.mark.asyncio
async def test_admin_list_institution_memberships(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id, limit=2)

    resp = await client.get(
        f"/admin/competitions/{competition_id}/institution-memberships",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["institutionId"] == str(ctx["institution_id"])
    assert rows[0]["institutionCode"] == ctx["school_code"]
    assert rows[0]["zoneId"] == str(ctx["zone_id"])
    assert rows[0]["configuredSkillCount"] == 1


@pytest.mark.asyncio
async def test_admin_list_institution_memberships_competition_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    missing = uuid.uuid4()
    resp = await client.get(
        f"/admin/competitions/{missing}/institution-memberships",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "COMPETITION_NOT_FOUND"


@pytest.mark.asyncio
async def test_admin_nomination_limits_requires_admin(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    await _seed(session_manager, competition_id, limit=1)
    user, password = await create_competitor_account(session_manager)
    competitor_headers = await login_as(client, user.email, password)

    resp = await client.get(
        f"/admin/competitions/{competition_id}/institution-memberships",
        headers=competitor_headers,
    )
    assert resp.status_code == 403
