"""US-REG-01 — Competitor completes online registration (auth-required)."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    Competitor,
    Institution,
    MarkingScheme,
    NotificationOutbox,
    Pathway,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    SmsDelivery,
    Zone,
)
from pytest_tests.conftest import (
    create_competitor_account,
    competition_payload,
    login_as,
    map_region_to_zone,
    region_id_by_name,
)

# 1x1 PNG
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
    window_open: bool = True,
    max_skills: int = 1,
    photo_max_mb: int = 2,
) -> dict[str, uuid.UUID]:
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
        )
        skill2 = Skill(
            competition_id=competition_id,
            name="Cloud Computing",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        inst = Institution(name=f"Reg Inst {uuid.uuid4().hex[:6]}", region_id=region_id)
        session.add_all([skill, skill2, zone, inst])
        await session.flush()

        now = datetime.utcnow()
        if window_open:
            opens, closes = now - timedelta(days=1), now + timedelta(days=30)
        else:
            opens, closes = now - timedelta(days=60), now - timedelta(days=1)

        session.add(RegistrationWindow(competition_id=competition_id, opens_at=opens, closes_at=closes))
        session.add(
            RegistrationFormDefinition(
                competition_id=competition_id,
                fields=DEFAULT_FIELDS,
                max_skills=max_skills,
                photo_max_mb=photo_max_mb,
                photo_formats=["image/jpeg", "image/png"],
                national_id_pattern=r"GHA-\d{9}",
                minor_age_under=18,
                minor_reference_date=date(2026, 1, 1),
            )
        )
        await session.commit()
        out = {
            "skill_id": skill.id,
            "skill2_id": skill2.id,
            "zone_id": zone.id,
            "institution_id": inst.id,
            "region_id": region_id,
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
        "whatsapp": "+233241234567",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "idDocumentKind": "GHANA_CARD",
        "otherIdType": None,
        "affiliationType": "school",
        "organizationPhone": "+233302123456",
        "organizationEmail": "school@example.com",
        "heardAbout": "Social media",
        "guardianName": "Kofi Mensah",
        "guardianPhone": "+233241000111",
        "hasPassport": False,
        "passportNumber": None,
        "passportExpiresOn": None,
        "institutionId": str(ctx["institution_id"]),
        "skillIds": [str(ctx["skill_id"])],
        "coach": {
            "surname": "Asante",
            "firstName": "Kojo",
            "otherName": "Mensah",
            "contactNumber": "+233201112233",
            "email": "coach@example.com",
            "whatsapp": "+233201112233",
            "dateOfBirth": "1985-04-12",
        },
        "declarationAccepted": True,
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
        "captchaToken": "ok",
    }
    base.update(overrides)
    return base


async def _comp_headers(client: AsyncClient, session_manager: DBManager) -> dict[str, str]:
    user, password = await create_competitor_account(session_manager)
    return await login_as(client, user.email, password)


@pytest.mark.asyncio
async def test_US_REG_01_AC1_successful_registration(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    form = await client.get(f"/competitions/{competition_id}/registration-form", headers=comp)
    assert form.status_code == 200
    assert form.json()["readOnly"] is False
    assert any(f["name"] == "givenNames" for f in form.json()["fields"])

    key = f"idem-{uuid.uuid4()}"
    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx),
        headers={**comp, "Idempotency-Key": key},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["competitorRef"].startswith("WSGH-")

    # Idempotent replay
    replay = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx),
        headers={**comp, "Idempotency-Key": key},
    )
    assert replay.status_code == 201
    assert replay.json()["competitorRef"] == body["competitorRef"]

    async with session_manager.session() as session:
        row = (
            await session.execute(select(Competitor).where(Competitor.competition_id == competition_id))
        ).scalar_one()
        assert row.user_id is not None
        assert row.eligibility_status == "ELIGIBLE"
        assert row.enrolment_attested is True

        notes = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "REGISTRATION_CONFIRMATION",
                    NotificationOutbox.competition_id == competition_id,
                    NotificationOutbox.recipient_id == uuid.UUID(body["competitorId"]),
                )
            )
        ).scalars().all()
        assert len(notes) >= 1
        assert any((n.channel or "").upper() == "SMS" for n in notes) or any(
            n.status == "QUEUED" for n in notes
        )

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "REGISTRATION_CREATE",
                    AuditEvent.entity_id == body["competitorId"],
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.after.get("userId") is not None

        sms_rows = (
            await session.execute(
                select(SmsDelivery).where(
                    SmsDelivery.competitor_id == uuid.UUID(body["competitorId"]),
                    SmsDelivery.message_type == "REGISTRATION_CONFIRMATION",
                )
            )
        ).scalars().all()
        assert len(sms_rows) == 1
        assert sms_rows[0].recipient_role == "competitor"
        assert sms_rows[0].status == "sent"
        assert sms_rows[0].msisdn


@pytest.mark.asyncio
async def test_registration_rejects_non_ghana_phone(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Competitor mobile/WhatsApp must be Ghana numbers."""
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            mobile="+15551234567",
            whatsapp="+15551234567",
        ),
        headers={**comp, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert resp.status_code == 422, resp.text
    fields = {f["name"]: f["reason"] for f in resp.json()["error"]["fields"]}
    assert fields.get("mobile") == "PHONE_INVALID"
    assert fields.get("whatsapp") == "PHONE_INVALID"


@pytest.mark.asyncio
async def test_US_REG_01_eligibility_rejected_at_registration(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    # Age 36 on 2026-01-01 reference with max_age 25 → INELIGIBLE
    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, dateOfBirth="1990-01-01"),
        headers=comp,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "ELIGIBILITY_FAILED"

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Competitor).where(
                    Competitor.competition_id == competition_id
                )
            )
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC2_window_closed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id, window_open=False)
    comp = await _comp_headers(client, session_manager)

    form = await client.get(f"/competitions/{competition_id}/registration-form", headers=comp)
    assert form.status_code == 200
    assert form.json()["readOnly"] is True

    resp = await client.post(
        f"/competitions/{competition_id}/registrations", json=_payload(ctx), headers=comp
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "WINDOW_CLOSED"


@pytest.mark.asyncio
async def test_US_REG_01_AC3_missing_required_field(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)
    payload = _payload(ctx, givenNames="")

    resp = await client.post(
        f"/competitions/{competition_id}/registrations", json=payload, headers=comp
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert any(f["name"] == "givenNames" and f["reason"] == "REQUIRED" for f in err["fields"])

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.competition_id == competition_id))
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC4_invalid_photo(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id, photo_max_mb=1)
    comp = await _comp_headers(client, session_manager)

    bad_type = _payload(
        ctx,
        photo={"contentBase64": _PNG_1X1, "contentType": "image/gif"},
    )
    resp = await client.post(
        f"/competitions/{competition_id}/registrations", json=bad_type, headers=comp
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PHOTO_INVALID"

    huge = base64.b64encode(b"x" * (1024 * 1024 + 10)).decode()
    bad_size = _payload(ctx, photo={"contentBase64": huge, "contentType": "image/png"})
    resp2 = await client.post(
        f"/competitions/{competition_id}/registrations", json=bad_size, headers=comp
    )
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "PHOTO_INVALID"


@pytest.mark.asyncio
async def test_US_REG_01_AC5_abuse(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    captcha_fail = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, captchaToken="invalid"),
        headers=comp,
    )
    assert captcha_fail.status_code == 403
    assert captcha_fail.json()["error"]["code"] == "ABUSE_SUSPECTED"

    rate = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, captchaToken="rate-limited"),
        headers=comp,
    )
    assert rate.status_code == 429
    assert rate.json()["error"]["code"] == "ABUSE_SUSPECTED"

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.competition_id == competition_id))
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC6_suspected_duplicate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp1 = await _comp_headers(client, session_manager)
    comp2 = await _comp_headers(client, session_manager)
    nid = "GHA-123456789"
    dob = "2005-03-15"

    first = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, nationalId=nid, dateOfBirth=dob),
        headers=comp1,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, nationalId=nid, dateOfBirth=dob, email="other@example.com"),
        headers=comp2,
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert "DUPLICATE_SUSPECTED" in body["flags"]
    assert body["message"] is not None


@pytest.mark.asyncio
async def test_US_REG_01_AC7_single_skill_rule(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id, max_skills=1)
    comp = await _comp_headers(client, session_manager)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, skillIds=[str(ctx["skill_id"]), str(ctx["skill2_id"])]),
        headers=comp,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SKILL_SELECTION_INVALID"


@pytest.mark.asyncio
async def test_US_REG_01_AC9_unauthenticated_refused(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)

    resp = await client.post(f"/competitions/{competition_id}/registrations", json=_payload(ctx))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.competition_id == competition_id))
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC10_one_registration_per_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    first = await client.post(
        f"/competitions/{competition_id}/registrations", json=_payload(ctx), headers=comp
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/competitions/{competition_id}/registrations", json=_payload(ctx), headers=comp
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_registration_company_affiliation_and_other_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            affiliationType="company",
            organizationName="Acme Workshop Co",
            organizationCity="Tema",
            regionId=str(ctx["region_id"]),
            idDocumentKind="OTHER",
            otherIdType="Passport",
            nationalId="P99887766",
            heardAbout="Other means",
        ),
        headers=comp,
    )
    assert resp.status_code == 201, resp.text
    async with session_manager.session() as session:
        row = await session.get(Competitor, uuid.UUID(resp.json()["competitorId"]))
        assert row is not None
        assert row.affiliation_type == "company"
        assert row.organization_name == "Acme Workshop Co"
        assert row.organization_city == "Tema"
        assert row.id_document_kind == "OTHER"
        assert row.other_id_type == "Passport"
        assert row.national_id == "P99887766"
        assert row.heard_about == "Other means"
        assert row.institution_id is None


@pytest.mark.asyncio
async def test_registration_unaffiliated_requires_region(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    missing_region = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            affiliationType="none",
            organizationName=None,
            organizationCity=None,
            organizationPhone=None,
            organizationEmail=None,
            regionId=None,
        ),
        headers=comp,
    )
    assert missing_region.status_code == 422, missing_region.text
    reasons = {f["name"] for f in missing_region.json()["error"]["fields"]}
    assert "regionId" in reasons

    ok = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            affiliationType="none",
            organizationName=None,
            organizationCity=None,
            organizationPhone=None,
            organizationEmail=None,
            regionId=str(ctx["region_id"]),
            email=f"solo-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers=comp,
    )
    assert ok.status_code == 201, ok.text
    async with session_manager.session() as session:
        row = await session.get(Competitor, uuid.UUID(ok.json()["competitorId"]))
        assert row is not None
        assert row.affiliation_type is None
        assert row.institution_id is None
        assert row.organization_name is None
        assert row.organization_phone is None
        assert str(row.region_id) == str(ctx["region_id"])


@pytest.mark.asyncio
async def test_available_skills_include_age_limits(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    async with session_manager.session() as session:
        skill = await session.get(Skill, ctx["skill_id"])
        assert skill is not None
        skill.max_age = 23
        skill.age_reference_date = date(2026, 1, 1)
        skill.open_category_enabled = False
        await session.commit()

    comp = await _comp_headers(client, session_manager)
    resp = await client.get(
        f"/competitions/{competition_id}/skills:available",
        headers=comp,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    match = next(i for i in items if i["skillId"] == str(ctx["skill_id"]))
    assert match["maxAge"] == 23
    assert match["referenceDate"] == "2026-01-01"
    assert match["openCategoryEnabled"] is False


@pytest.mark.asyncio
async def test_registration_manual_school_requires_region(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    missing_region = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            affiliationType="school",
            organizationName="Unlisted SHS",
            regionId=None,
        ),
        headers=comp,
    )
    assert missing_region.status_code == 422
    reasons = {f["name"] for f in missing_region.json()["error"]["fields"]}
    assert "regionId" in reasons

    ok = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            institutionId=None,
            affiliationType="school",
            organizationName="Unlisted SHS",
            regionId=str(ctx["region_id"]),
            email=f"manual-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers=comp,
    )
    assert ok.status_code == 201, ok.text
    async with session_manager.session() as session:
        row = await session.get(Competitor, uuid.UUID(ok.json()["competitorId"]))
        assert row is not None
        assert row.organization_name == "Unlisted SHS"
        assert row.region_id == ctx["region_id"]


@pytest.mark.asyncio
async def test_registration_ghana_card_pattern_skipped_for_other_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    bad_ghana = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            idDocumentKind="GHANA_CARD",
            nationalId="NOT-A-Ghana-Card",
        ),
        headers=comp,
    )
    assert bad_ghana.status_code == 422
    assert any(
        f["name"] == "nationalId" and f["reason"] == "ID_INVALID"
        for f in bad_ghana.json()["error"]["fields"]
    )

    missing_org_phone = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, organizationPhone=""),
        headers=comp,
    )
    assert missing_org_phone.status_code == 422
    assert any(
        f["name"] == "organizationPhone"
        for f in missing_org_phone.json()["error"]["fields"]
    )


@pytest.mark.asyncio
async def test_registration_without_id_document_allowed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Competitors may submit without providing an ID document."""
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            idDocumentKind=None,
            otherIdType=None,
            nationalId=None,
        ),
        headers={**comp, "Idempotency-Key": f"no-id-{uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    async with session_manager.session() as session:
        row = await session.get(Competitor, uuid.UUID(resp.json()["competitorId"]))
        assert row is not None
        assert row.national_id is None
        assert row.id_document_kind is None


@pytest.mark.asyncio
async def test_registration_form_injects_profile_fields_for_legacy_config(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Older stored form JSON omits WhatsApp/guardian/heardAbout; GET still returns them."""
    competition_id = await _create_competition(client, auth_headers)
    await _seed_reg(session_manager, competition_id)
    # Confirm seed still uses the legacy field list without profile fields.
    assert not any(f["name"] == "whatsapp" for f in DEFAULT_FIELDS)
    assert not any(f["name"] == "heardAbout" for f in DEFAULT_FIELDS)

    comp = await _comp_headers(client, session_manager)
    form = await client.get(
        f"/competitions/{competition_id}/registration-form", headers=comp
    )
    assert form.status_code == 200, form.text
    names = {f["name"] for f in form.json()["fields"]}
    for required_name in (
        "whatsapp",
        "guardianName",
        "guardianPhone",
        "heardAbout",
        "gender",
    ):
        assert required_name in names, f"missing injected field: {required_name}"

    heard = next(f for f in form.json()["fields"] if f["name"] == "heardAbout")
    assert heard["required"] is True
    assert heard["allowedValues"] == [
        "Social media",
        "Newspaper",
        "Friend",
        "Radio",
        "Television",
        "Website (CTVET/WorldSkills)",
        "Other means",
    ]
    assert form.json().get("minorAgeUnder") == 18

    guardian_name = next(f for f in form.json()["fields"] if f["name"] == "guardianName")
    assert guardian_name["required"] is False


@pytest.mark.asyncio
async def test_guardian_contacts_optional_for_all_ages(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Guardian contacts are optional; consent is not enforced for minors or adults."""
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)

    # Adult without guardian
    adult_headers = await _comp_headers(client, session_manager)
    adult = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            dateOfBirth="2005-03-15",
            guardianName=None,
            guardianPhone=None,
            email=f"adult-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers={**adult_headers, "Idempotency-Key": f"adult-{uuid.uuid4()}"},
    )
    assert adult.status_code == 201, adult.text
    assert "CONSENT_PENDING" not in (adult.json().get("flags") or [])

    # Minor without guardian — still accepted; no consent flag
    minor_headers = await _comp_headers(client, session_manager)
    minor = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            dateOfBirth="2010-06-15",
            guardianName=None,
            guardianPhone=None,
            email=f"minor-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers={**minor_headers, "Idempotency-Key": f"minor-{uuid.uuid4()}"},
    )
    assert minor.status_code == 201, minor.text
    assert "CONSENT_PENDING" not in (minor.json().get("flags") or [])

    # Minor with guardian — stored as informational only
    with_g = await _comp_headers(client, session_manager)
    ok = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(
            ctx,
            dateOfBirth="2010-06-15",
            guardianName="Parent Mensah",
            guardianPhone="+233241000222",
            email=f"minor-g-{uuid.uuid4().hex[:6]}@example.com",
            nationalId=f"GHA-{uuid.uuid4().int % 10**9:09d}",
        ),
        headers={**with_g, "Idempotency-Key": f"minor-g-{uuid.uuid4()}"},
    )
    assert ok.status_code == 201, ok.text
    assert "CONSENT_PENDING" not in (ok.json().get("flags") or [])
    async with session_manager.session() as session:
        row = await session.get(Competitor, uuid.UUID(ok.json()["competitorId"]))
        assert row is not None
        assert row.guardian_name == "Parent Mensah"
        assert row.guardian_phone == "+233241000222"
