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
    PublicPortalConfig,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    Zone,
)
from app.services.consent import can_progress_past_pending_review, is_public_profile_visible
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

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def _upload_consent(
    client: AsyncClient,
    competitor_id: str,
    headers: dict[str, str],
    *,
    scopes: list[str],
    granted_by: str | None = "Ama Guardian",
) -> object:
    # httpx 0.28: keep all multipart parts in `files` to avoid sync stream errors
    parts: list[tuple[str, tuple]] = [
        ("file", ("signed-consent.pdf", _MINIMAL_PDF, "application/pdf")),
    ]
    for scope in scopes:
        parts.append(("scopes", (None, scope)))
    if granted_by:
        parts.append(("grantedBy", (None, granted_by)))
    return await client.post(
        f"/competitors/{competitor_id}/consent-form",
        headers=headers,
        files=parts,
    )

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


async def _seed(session_manager: DBManager, competition_id: uuid.UUID) -> dict[str, uuid.UUID]:
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
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        inst = Institution(name=f"Consent Inst {uuid.uuid4().hex[:6]}", region_id=region_id)
        session.add_all([skill, zone, inst])
        await session.flush()
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
        session.add(
            PublicPortalConfig(
                competition_id=competition_id,
                public_fields=["displayName", "photo", "institution", "skill", "stageStatus", "zone", "competitorRef"],
                rate_limit_per_minute=1000,
                max_page_size=50,
            )
        )
        await session.commit()
        out = {"skill_id": skill.id, "zone_id": zone.id, "institution_id": inst.id}
    await map_region_to_zone(session_manager, competition_id, region_id, out["zone_id"])
    return out


def _reg_payload(ctx: dict[str, uuid.UUID], *, dob: str, **overrides: object) -> dict:
    base: dict = {
        "givenNames": "Kofi",
        "familyName": "Minor",
        "gender": "Male",
        "dateOfBirth": dob,
        "email": f"kofi-{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+233241111111",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "hasPassport": False,
        "institutionId": str(ctx["institution_id"]),
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
    }
    base.update(overrides)
    return base


async def _comp(client: AsyncClient, session_manager: DBManager) -> dict[str, str]:
    user, password = await create_competitor_account(session_manager)
    return await login_as(client, user.email, password)


@pytest.mark.asyncio
async def test_US_REG_02_AC1_consent_required_for_minor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    comp = await _comp(client, session_manager)

    # Age 16 on 2026-01-01
    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
        headers=comp,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert "CONSENT_PENDING" in body["flags"]

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(body["competitorId"]))
        assert competitor is not None
        assert competitor.status == "PENDING_REVIEW"
        assert "CONSENT_PENDING" in (competitor.flags or [])
        assert can_progress_past_pending_review(competitor)
        assert is_public_profile_visible(competitor) is False


@pytest.mark.asyncio
async def test_US_REG_02_AC2_participation_consent_lifts_block(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    comp = await _comp(client, session_manager)

    created = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
        headers=comp,
    )
    assert created.status_code == 201, created.text
    cid = created.json()["competitorId"]

    monkeypatch.setattr(
        "app.services.consent.render_consent_form_pdf",
        lambda **kwargs: _MINIMAL_PDF,
    )
    pdf = await client.get(f"/competitors/{cid}/consent-form.pdf", headers=comp)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    missing_scope = await _upload_consent(client, cid, comp, scopes=[])
    assert missing_scope.status_code == 422
    assert missing_scope.json()["error"]["code"] == "CONSENT_SCOPE_MISSING"

    bad_file = await client.post(
        f"/competitors/{cid}/consent-form",
        headers=comp,
        files=[
            ("scopes", (None, "participation")),
            ("file", ("notes.txt", b"not-a-pdf", "text/plain")),
        ],
    )
    assert bad_file.status_code == 422
    assert bad_file.json()["error"]["code"] == "INVALID_FILE_TYPE"

    granted = await _upload_consent(
        client,
        cid,
        comp,
        scopes=["participation"],
        granted_by="Ama Guardian",
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["status"] == "PENDING_REVIEW"
    assert "participation" in granted.json()["scopesGranted"]
    assert granted.json()["publicProfileVisible"] is False

    signed = await client.get(
        f"/competitors/{cid}/consent-form/signed.pdf",
        headers=comp,
    )
    assert signed.status_code == 200, signed.text
    assert signed.headers["content-type"].startswith("application/pdf")
    assert signed.content.startswith(b"%PDF")
    assert "inline" in signed.headers.get("content-disposition", "")

    signed_dl = await client.get(
        f"/competitors/{cid}/consent-form/signed.pdf?download=true",
        headers=comp,
    )
    assert signed_dl.status_code == 200, signed_dl.text
    assert "attachment" in signed_dl.headers.get("content-disposition", "")

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(cid))
        assert competitor is not None
        assert competitor.consent_participation_at is not None
        assert competitor.consent_participation_by == "Ama Guardian"
        assert competitor.consent_form_key is not None
        assert competitor.consent_form_sha256 is not None
        assert competitor.consent_verification_status == "PENDING"
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

    admin_view = await client.get(
        f"/admin/competitors/{cid}/consent-form/signed.pdf",
        headers=auth_headers,
    )
    assert admin_view.status_code == 200, admin_view.text
    assert admin_view.content.startswith(b"%PDF")

    verified = await client.post(
        f"/admin/competitors/{cid}/consent:verify",
        json={"outcome": "VERIFIED"},
        headers=auth_headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["consentVerificationStatus"] == "VERIFIED"

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(cid))
        assert competitor is not None
        assert competitor.consent_verification_status == "VERIFIED"
        assert competitor.consent_verified_at is not None
        assert competitor.status == "REGISTERED"


@pytest.mark.asyncio
async def test_US_REG_02_AC3_public_display_default_off(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    comp = await _comp(client, session_manager)

    created = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
        headers=comp,
    )
    cid = created.json()["competitorId"]
    ref = created.json()["competitorRef"]

    await _upload_consent(client, cid, comp, scopes=["participation"])

    hidden = await client.get(f"/public/competitors/{ref}")
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "PROFILE_NOT_PUBLIC"

    pub = await _upload_consent(client, cid, comp, scopes=["public"])
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
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed(session_manager, competition_id)
    comp = await _comp(client, session_manager)

    created = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_reg_payload(ctx, dob="2010-06-15"),
        headers=comp,
    )
    cid = created.json()["competitorId"]
    ref = created.json()["competitorRef"]

    await _upload_consent(
        client,
        cid,
        comp,
        scopes=["participation", "public"],
    )
    assert (await client.get(f"/public/competitors/{ref}")).status_code == 200

    withdrawn = await client.post(f"/competitors/{cid}/consent:withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    body = withdrawn.json()
    assert body["publicProfileVisible"] is False
    assert "CONSENT_WITHDRAWN" in body["flags"]
    assert "CONSENT_PENDING" in body["flags"]

    assert (await client.get(f"/public/competitors/{ref}")).status_code == 404

    async with session_manager.session() as session:
        competitor = await session.get(Competitor, uuid.UUID(cid))
        assert competitor is not None
        assert competitor.consent_participation_at is None
        assert competitor.consent_public_at is None
        assert competitor.consent_form_key is None
        assert can_progress_past_pending_review(competitor)
        assert "CONSENT_PENDING" in (competitor.flags or [])
        # Status must not be forced back to a blocking CONSENT_PENDING state.
        assert competitor.status != "CONSENT_PENDING"

        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "CONSENT_WITHDRAW",
                    AuditEvent.entity_id == cid,
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
