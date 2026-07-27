"""US-PUB-01 — Public competitor directory and privacy-controlled profile."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Competitor,
    Institution,
    MarkingScheme,
    Pathway,
    PublicPortalConfig,
    Skill,
    Zone,
)
from app.services import public_portal as portal_service
from pytest_tests.conftest import competition_payload

_SENSITIVE_KEYS = {
    "dateOfBirth",
    "date_of_birth",
    "dob",
    "nationalId",
    "national_id",
    "passport",
    "email",
    "mobile",
    "whatsapp",
    "phone",
    "guardianName",
    "guardianEmail",
    "guardianPhone",
    "guardian_name",
    "guardian_email",
    "guardian_phone",
    "contacts",
    "registrationPayload",
}


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(timeZone="Africa/Accra"), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_portal_world(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    *,
    rate_limit_per_minute: int = 1000,
    max_page_size: int = 50,
    public_fields: list[str] | None = None,
    with_config: bool = True,
) -> dict:
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
        inst = Institution(name=f"Public Inst {uuid.uuid4().hex[:6]}", active=True)
        session.add_all([age, path, scheme, zone_a, zone_b, inst])
        await session.flush()

        skill_web = Skill(
            competition_id=competition_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=40,
            active=True,
        )
        skill_cook = Skill(
            competition_id=competition_id,
            name="Cooking",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=20,
            active=True,
        )
        session.add_all([skill_web, skill_cook])
        await session.flush()

        if with_config:
            session.add(
                PublicPortalConfig(
                    competition_id=competition_id,
                    public_fields=public_fields
                    or ["displayName", "photo", "institution", "skill", "stageStatus", "zone"],
                    rate_limit_per_minute=rate_limit_per_minute,
                    max_page_size=max_page_size,
                )
            )

        # Visible (consent) in web / Accra
        visible = Competitor(
            competition_id=competition_id,
            skill_id=skill_web.id,
            zone_id=zone_a.id,
            institution_id=inst.id,
            ref_no=f"PUB-VIS-{uuid.uuid4().hex[:6]}",
            status="ACTIVE_IN_STAGE",
            given_names="Ama",
            family_name="Visible",
            date_of_birth=date(2005, 3, 1),
            email="ama@example.com",
            mobile="+233200000001",
            national_id="GHA-111111111",
            photo_key="photos/ama.png",
            guardian_name="Secret Guardian",
            guardian_email="g@example.com",
            guardian_phone="+233200000099",
            consent_public_at=datetime.utcnow(),
            consent_public_by="guardian@example.com",
            public_profile_visible=True,
            nationality="GH",
            enrolment_attested=True,
            flags=[],
        )
        # Visible in cooking / Ashanti
        visible_b = Competitor(
            competition_id=competition_id,
            skill_id=skill_cook.id,
            zone_id=zone_b.id,
            institution_id=inst.id,
            ref_no=f"PUB-VISB-{uuid.uuid4().hex[:6]}",
            status="REGISTERED",
            given_names="Kwesi",
            family_name="Cook",
            date_of_birth=date(2004, 1, 1),
            email="kwesi@example.com",
            mobile="+233200000002",
            national_id="GHA-222222222",
            consent_public_at=datetime.utcnow(),
            consent_public_by="self",
            public_profile_visible=True,
            nationality="GH",
            enrolment_attested=True,
            flags=[],
        )
        # Hidden — no public consent (minor default)
        hidden = Competitor(
            competition_id=competition_id,
            skill_id=skill_web.id,
            zone_id=zone_a.id,
            institution_id=inst.id,
            ref_no=f"PUB-HID-{uuid.uuid4().hex[:6]}",
            status="ACTIVE_IN_STAGE",
            given_names="Hidden",
            family_name="Minor",
            date_of_birth=date(2012, 6, 1),
            email="hidden@example.com",
            mobile="+233200000003",
            national_id="GHA-333333333",
            guardian_name="Parent",
            guardian_email="parent@example.com",
            public_profile_visible=False,
            consent_public_at=None,
            nationality="GH",
            enrolment_attested=True,
            flags=["CONSENT_PENDING"],
        )
        session.add_all([visible, visible_b, hidden])
        await session.commit()

        return {
            "skill_web_id": skill_web.id,
            "skill_cook_id": skill_cook.id,
            "zone_a_id": zone_a.id,
            "zone_b_id": zone_b.id,
            "institution_id": inst.id,
            "institution_name": inst.name,
            "visible_id": visible.id,
            "visible_ref": visible.ref_no,
            "visible_b_id": visible_b.id,
            "hidden_id": hidden.id,
            "hidden_ref": hidden.ref_no,
        }


def _assert_no_sensitive(payload: object) -> None:
    """Definition of Done — negative proof no sensitive field is serialised."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in _SENSITIVE_KEYS, f"sensitive key leaked: {key}"
            # Also catch nested camel/snake variants in string values dump
            _assert_no_sensitive(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_sensitive(item)


@pytest.mark.asyncio
async def test_US_PUB_01_AC1_directory_filter(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_portal_world(session_manager, competition_id)

    resp = await client.get(
        f"/public/competitions/{competition_id}/competitors",
        params={"skill": str(ctx["skill_web_id"])},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    ids = {item["competitorId"] for item in body["items"]}
    assert str(ctx["visible_id"]) in ids
    assert str(ctx["visible_b_id"]) not in ids  # different skill
    assert str(ctx["hidden_id"]) not in ids
    for item in body["items"]:
        assert "displayName" in item
        assert item["skill"] == "Web Development"
        _assert_no_sensitive(item)

    # Missing portal config → CONFIG_INCOMPLETE
    cycle2 = await _create_competition(client, auth_headers)
    await _seed_portal_world(session_manager, cycle2, with_config=False)
    missing = await client.get(f"/public/competitions/{cycle2}/competitors")
    assert missing.status_code == 409, missing.text
    assert missing.json()["error"]["code"] == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_US_PUB_01_AC2_consent_gate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_portal_world(session_manager, competition_id)

    listing = await client.get(f"/public/competitions/{competition_id}/competitors")
    assert listing.status_code == 200, listing.text
    ids = {item["competitorId"] for item in listing.json()["items"]}
    assert str(ctx["hidden_id"]) not in ids
    assert str(ctx["visible_id"]) in ids

    # Direct profile lookup must not oracle non-public competitors
    hidden_profile = await client.get(f"/public/competitors/{ctx['hidden_id']}")
    assert hidden_profile.status_code == 404, hidden_profile.text
    assert hidden_profile.json()["error"]["code"] in {"PROFILE_NOT_PUBLIC", "NOT_FOUND"}


@pytest.mark.asyncio
async def test_US_PUB_01_AC3_no_sensitive_data(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_portal_world(session_manager, competition_id)

    profile = await client.get(f"/public/competitors/{ctx['visible_id']}")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    _assert_no_sensitive(body)
    # Explicit forbidden values must not appear as JSON values either
    dumped = profile.text.lower()
    assert "ama@example.com" not in dumped
    assert "gha-111111111" not in dumped
    assert "secret guardian" not in dumped
    assert "+233200000001" not in dumped
    assert "2005-03-01" not in dumped
    assert "guardian" not in dumped or "guardian" not in body  # key absent
    assert "dateOfBirth" not in body
    assert "nationalId" not in body
    assert "email" not in body
    assert "mobile" not in body
    assert body.get("displayName") == "Ama Visible"


@pytest.mark.asyncio
async def test_US_PUB_01_AC4_anti_scraping(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_portal_world(
        session_manager,
        competition_id,
        rate_limit_per_minute=3,
        max_page_size=2,
    )
    portal_service.reset_rate_limits()

    # Bulk export / oversized page refused
    export = await client.get(
        f"/public/competitions/{competition_id}/competitors",
        params={"limit": 100},
    )
    assert export.status_code == 429, export.text
    assert export.json()["error"]["code"] in {"RATE_LIMITED", "ABUSE_SUSPECTED", "EXPORT_REFUSED"}

    export_fmt = await client.get(
        f"/public/competitions/{competition_id}/competitors",
        params={"format": "csv"},
    )
    assert export_fmt.status_code == 429, export_fmt.text
    assert export_fmt.json()["error"]["code"] in {"RATE_LIMITED", "ABUSE_SUSPECTED", "EXPORT_REFUSED"}

    # Volume throttle
    portal_service.reset_rate_limits()
    codes = []
    for _ in range(5):
        r = await client.get(
            f"/public/competitions/{competition_id}/competitors",
            params={"skill": str(ctx["skill_web_id"])},
            headers={"X-Forwarded-For": "203.0.113.50"},
        )
        codes.append(r.status_code)
    assert 429 in codes
    throttled = [c for c in codes if c == 429]
    assert len(throttled) >= 1
    last = await client.get(
        f"/public/competitions/{competition_id}/competitors",
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    # After limit, continued abuse stays blocked
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "RATE_LIMITED"
