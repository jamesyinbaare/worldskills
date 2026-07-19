"""US-REG-02 — Capture and verify guardian consent for a minor."""

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
    AuditEvent,
    Competitor,
    Institution,
    MarkingScheme,
    Pathway,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    Zone,
)
from app.services.consent import can_progress_past_pending_review, is_public_profile_visible
from pytest_tests.conftest import cycle_payload

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


async def _seed(session_manager: DBManager, cycle_id: uuid.UUID) -> dict[str, uuid.UUID]:
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
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        inst = Institution(name=f"Consent Inst {uuid.uuid4().hex[:6]}")
        session.add_all([skill, zone, inst])
        await session.flush()
        now = datetime.utcnow()
        session.add(
            RegistrationWindow(
                cycle_id=cycle_id,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
            )
        )
        session.add(
            RegistrationFormDefinition(
                cycle_id=cycle_id,
                fields=DEFAULT_FIELDS,
                max_skills=1,
                photo_max_mb=2,
                photo_formats=["image/jpeg", "image/png"],
                national_id_pattern=r"GHA-\d{9}",
                minor_age_under=18,
                minor_reference_date=date(2026, 1, 1),
            )
        )
        await session.commit()
        return {"skill_id": skill.id, "zone_id": zone.id, "institution_id": inst.id}


def _reg_payload(ctx: dict[str, uuid.UUID], *, dob: str, **overrides: object) -> dict:
    base: dict = {
        "givenNames": "Kofi",
        "familyName": "Minor",
        "dateOfBirth": dob,
        "email": f"kofi-{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+233241111111",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "institutionId": str(ctx["institution_id"]),
        "zoneId": str(ctx["zone_id"]),
        "skillIds": [str(ctx["skill_id"])],
        "declarationAccepted": True,
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
        "captchaToken": "ok",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_US_REG_02_AC1_consent_required_for_minor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed(session_manager, cycle_id)

    # Age 16 on 2026-01-01
    resp = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "CONSENT_PENDING"
    assert "CONSENT_PENDING" in body["flags"]

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(body["competitorId"]))
        assert competitor is not None
        assert competitor.status == "CONSENT_PENDING"
        assert not can_progress_past_pending_review(competitor)
        assert is_public_profile_visible(competitor) is False


@pytest.mark.asyncio
async def test_US_REG_02_AC2_participation_consent_lifts_block(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed(session_manager, cycle_id)

    created = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
    )
    assert created.status_code == 201, created.text
    cid = created.json()["competitorId"]

    req = await client.post(
        f"/competitors/{cid}/consent-request",
        json={
            "guardianName": "Ama Guardian",
            "guardianEmail": "ama.guardian@example.com",
            "guardianPhone": "+233200000000",
        },
    )
    assert req.status_code == 200, req.text
    token = req.json()["token"]

    missing_scope = await client.post(f"/consent/{token}:grant", json={"scopes": []})
    assert missing_scope.status_code == 422
    assert missing_scope.json()["error"]["code"] == "CONSENT_SCOPE_MISSING"

    bad_token = await client.post("/consent/not-a-real-token:grant", json={"scopes": ["participation"]})
    assert bad_token.status_code == 400
    assert bad_token.json()["error"]["code"] == "CONSENT_TOKEN_INVALID"

    granted = await client.post(
        f"/consent/{token}:grant",
        json={"scopes": ["participation"], "grantedBy": "Ama Guardian"},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["status"] == "PENDING_REVIEW"
    assert "participation" in granted.json()["scopesGranted"]
    assert granted.json()["publicProfileVisible"] is False

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(cid))
        assert competitor is not None
        assert competitor.consent_participation_at is not None
        assert competitor.consent_participation_by == "Ama Guardian"
        assert can_progress_past_pending_review(competitor)
        assert "CONSENT_PENDING" not in (competitor.flags or [])

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "CONSENT_GRANT",
                    AuditEvent.entity_id == cid,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_REG_02_AC3_public_display_default_off(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed(session_manager, cycle_id)

    created = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
    )
    cid = created.json()["competitorId"]
    ref = created.json()["competitorRef"]

    req = await client.post(
        f"/competitors/{cid}/consent-request",
        json={"guardianName": "Guardian", "guardianEmail": "g@example.com"},
    )
    token = req.json()["token"]
    await client.post(f"/consent/{token}:grant", json={"scopes": ["participation"]})

    hidden = await client.get(f"/public/competitors/{ref}")
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "PROFILE_NOT_PUBLIC"

    # New token after consumption — need fresh request for public scope
    req2 = await client.post(
        f"/competitors/{cid}/consent-request",
        json={"guardianName": "Guardian", "guardianEmail": "g@example.com"},
    )
    token2 = req2.json()["token"]
    pub = await client.post(f"/consent/{token2}:grant", json={"scopes": ["public"]})
    assert pub.status_code == 200, pub.text
    assert pub.json()["publicProfileVisible"] is True

    visible = await client.get(f"/public/competitors/{ref}")
    assert visible.status_code == 200, visible.text
    assert visible.json()["public"] is True
    assert visible.json()["competitorRef"] == ref


@pytest.mark.asyncio
async def test_US_REG_02_AC4_withdrawal(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    cycle_id = await _create_cycle(client, auth_headers)
    ctx = await _seed(session_manager, cycle_id)

    created = await client.post(
        f"/cycles/{cycle_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
    )
    cid = created.json()["competitorId"]
    ref = created.json()["competitorRef"]

    req = await client.post(
        f"/competitors/{cid}/consent-request",
        json={"guardianName": "Guardian", "guardianEmail": "g@example.com"},
    )
    token = req.json()["token"]
    await client.post(
        f"/consent/{token}:grant",
        json={"scopes": ["participation", "public"]},
    )
    assert (await client.get(f"/public/competitors/{ref}")).status_code == 200

    withdrawn = await client.post(f"/competitors/{cid}/consent:withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    body = withdrawn.json()
    assert body["publicProfileVisible"] is False
    assert "CONSENT_WITHDRAWN" in body["flags"]
    assert body["status"] == "CONSENT_PENDING"

    assert (await client.get(f"/public/competitors/{ref}")).status_code == 404

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(cid))
        assert competitor is not None
        assert competitor.consent_participation_at is None
        assert competitor.consent_public_at is None
        assert not can_progress_past_pending_review(competitor)

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "CONSENT_WITHDRAW",
                    AuditEvent.entity_id == cid,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
