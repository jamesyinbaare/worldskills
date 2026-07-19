"""US-REG-01 — Competitor completes online registration."""

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
from pytest_tests.conftest import cycle_payload

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


async def _create_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_reg(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    *,
    window_open: bool = True,
    max_skills: int = 1,
    photo_max_mb: int = 2,
) -> dict[str, uuid.UUID]:
    async with session_manager.session() as session:
        age = AgeRule(cycle_id=cycle_id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        skill = Skill(
            cycle_id=cycle_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        skill2 = Skill(
            cycle_id=cycle_id,
            name="Cloud Computing",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            active=True,
        )
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        inst = Institution(name=f"Reg Inst {uuid.uuid4().hex[:6]}")
        session.add_all([skill, skill2, zone, inst])
        await session.flush()

        now = datetime.utcnow()
        if window_open:
            opens, closes = now - timedelta(days=1), now + timedelta(days=30)
        else:
            opens, closes = now - timedelta(days=60), now - timedelta(days=1)

        session.add(RegistrationWindow(cycle_id=cycle_id, opens_at=opens, closes_at=closes))
        session.add(
            RegistrationFormDefinition(
                cycle_id=cycle_id,
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
        return {
            "skill_id": skill.id,
            "skill2_id": skill2.id,
            "zone_id": zone.id,
            "institution_id": inst.id,
        }


def _payload(ctx: dict[str, uuid.UUID], **overrides: object) -> dict:
    base: dict = {
        "givenNames": "Ama",
        "familyName": "Mensah",
        "dateOfBirth": "2005-03-15",
        "email": f"ama-{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+233241234567",
        "whatsapp": "+233241234567",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "institutionId": str(ctx["institution_id"]),
        "zoneId": str(ctx["zone_id"]),
        "skillIds": [str(ctx["skill_id"])],
        "coach": {"name": "Kojo"},
        "declarationAccepted": True,
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
        "captchaToken": "ok",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_US_REG_01_AC1_successful_registration(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id)

    form = await client.get(f"/cycles/{cycle_id}/registration-form")
    assert form.status_code == 200
    assert form.json()["readOnly"] is False
    assert any(f["name"] == "givenNames" for f in form.json()["fields"])

    key = f"idem-{uuid.uuid4()}"
    resp = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx),
        headers={"Idempotency-Key": key},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["competitorRef"].startswith("WSG-")

    # Idempotent replay
    replay = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx),
        headers={"Idempotency-Key": key},
    )
    assert replay.status_code == 201
    assert replay.json()["competitorRef"] == body["competitorRef"]

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.cycle_id == cycle_id))
        ).scalar_one()
        assert int(count) == 1

        note = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template == "REGISTRATION_CONFIRMATION",
                    NotificationOutbox.cycle_id == cycle_id,
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
        assert "email" not in str(audit.after).lower() or audit.after.get("competitorRef")


@pytest.mark.asyncio
async def test_US_REG_01_AC2_window_closed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id, window_open=False)

    form = await client.get(f"/cycles/{cycle_id}/registration-form")
    assert form.status_code == 200
    assert form.json()["readOnly"] is True

    resp = await client.post(f"/cycles/{cycle_id}/registrations", json=_payload(ctx))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "WINDOW_CLOSED"


@pytest.mark.asyncio
async def test_US_REG_01_AC3_missing_required_field(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id)
    payload = _payload(ctx, givenNames="")

    resp = await client.post(f"/cycles/{cycle_id}/registrations", json=payload)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert any(f["name"] == "givenNames" and f["reason"] == "REQUIRED" for f in err["fields"])

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.cycle_id == cycle_id))
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC4_invalid_photo(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id, photo_max_mb=1)

    # Wrong format
    bad_type = _payload(
        ctx,
        photo={"contentBase64": _PNG_1X1, "contentType": "image/gif"},
    )
    resp = await client.post(f"/cycles/{cycle_id}/registrations", json=bad_type)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PHOTO_INVALID"
    assert "max" in resp.json()["error"]["message"].lower() or "format" in resp.json()["error"]["message"].lower()

    # Too large (>1MB)
    huge = base64.b64encode(b"x" * (1024 * 1024 + 10)).decode()
    bad_size = _payload(ctx, photo={"contentBase64": huge, "contentType": "image/png"})
    resp2 = await client.post(f"/cycles/{cycle_id}/registrations", json=bad_size)
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "PHOTO_INVALID"


@pytest.mark.asyncio
async def test_US_REG_01_AC5_abuse(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id)

    captcha_fail = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx, captchaToken="invalid"),
    )
    assert captcha_fail.status_code == 403
    assert captcha_fail.json()["error"]["code"] == "ABUSE_SUSPECTED"

    rate = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx, captchaToken="rate-limited"),
    )
    assert rate.status_code == 429
    assert rate.json()["error"]["code"] == "ABUSE_SUSPECTED"

    async with session_manager.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(Competitor).where(Competitor.cycle_id == cycle_id))
        ).scalar_one()
        assert int(count) == 0


@pytest.mark.asyncio
async def test_US_REG_01_AC6_suspected_duplicate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id)
    nid = "GHA-123456789"
    dob = "2005-03-15"

    first = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx, nationalId=nid, dateOfBirth=dob),
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx, nationalId=nid, dateOfBirth=dob, email="other@example.com"),
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
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed_reg(session_manager, cycle_id, max_skills=1)

    resp = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_payload(ctx, skillIds=[str(ctx["skill_id"]), str(ctx["skill2_id"])]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SKILL_SELECTION_INVALID"
