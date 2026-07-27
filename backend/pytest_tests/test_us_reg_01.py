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
        "hasPassport": False,
        "passportNumber": None,
        "passportExpiresOn": None,
        "institutionId": str(ctx["institution_id"]),
        "skillIds": [str(ctx["skill_id"])],
        "coach": {"name": "Kojo"},
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
    assert body["competitorRef"].startswith("WSG-")

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

        note = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "REGISTRATION_CONFIRMATION",
                    NotificationOutbox.competition_id == competition_id,
                    NotificationOutbox.recipient_id == uuid.UUID(body["competitorId"]),
                )
            )
        ).scalar_one_or_none()
        assert note is not None

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
