"""System settings — public/admin API and enforcement."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    Competition,
    CompetitionStatus,
    RegistrationFormDefinition,
    RegistrationWindow,
)
from pytest_tests.conftest import (
    VALID_COACH,
    competition_payload,
    set_system_settings,
)
from pytest_tests.test_us_sec_04 import _seed_school


@pytest.mark.asyncio
async def test_public_settings_defaults(client: AsyncClient) -> None:
    resp = await client.get("/settings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["institutionRegistrationEnabled"] is False
    assert body["allowMultipleActiveCompetitions"] is True


@pytest.mark.asyncio
async def test_admin_can_patch_settings(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    patch = await client.patch(
        "/admin/settings",
        headers=auth_headers,
        json={
            "institutionRegistrationEnabled": True,
            "allowMultipleActiveCompetitions": False,
        },
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["institutionRegistrationEnabled"] is True
    assert patch.json()["allowMultipleActiveCompetitions"] is False

    public = await client.get("/settings")
    assert public.status_code == 200
    assert public.json()["institutionRegistrationEnabled"] is True
    assert public.json()["allowMultipleActiveCompetitions"] is False


@pytest.mark.asyncio
async def test_institution_signup_blocked_when_disabled(
    client: AsyncClient, session_manager: DBManager
) -> None:
    await set_system_settings(session_manager, institution_registration_enabled=False)
    school = await _seed_school(session_manager)
    resp = await client.post(
        "/auth/register-institution",
        json={
            "email": f"blocked-{uuid.uuid4().hex[:8]}@school.edu",
            "fullName": "Head",
            "password": "Institution1!",
            "passwordConfirm": "Institution1!",
            "schoolCode": school.code,
            "captchaToken": "ok",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSTITUTION_REGISTRATION_DISABLED"


@pytest.mark.asyncio
async def test_activate_blocked_when_single_active_mode(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    await set_system_settings(session_manager, allow_multiple_active_competitions=False)

    first = await client.post(
        "/competitions", json=competition_payload(), headers=auth_headers
    )
    assert first.status_code == 201, first.text
    first_id = uuid.UUID(first.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, first_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        await session.commit()

    second = await client.post(
        "/competitions", json=competition_payload(), headers=auth_headers
    )
    assert second.status_code == 201, second.text
    second_id = uuid.UUID(second.json()["competitionId"])

    now = datetime.utcnow()
    async with session_manager.session() as session:
        session.add(
            RegistrationWindow(
                competition_id=second_id,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
            )
        )
        session.add(
            RegistrationFormDefinition(
                competition_id=second_id,
                fields=[{"name": "givenNames", "type": "string", "required": True}],
                max_skills=1,
                photo_max_mb=2,
                photo_formats=["image/jpeg", "image/png"],
            )
        )
        await session.commit()

    activate = await client.post(
        f"/competitions/{second_id}:activate", headers=auth_headers
    )
    assert activate.status_code == 409, activate.text
    assert activate.json()["error"]["code"] == "MULTIPLE_ACTIVE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_registration_requires_coach_biodata(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from pytest_tests.test_us_reg_01 import (
        _comp_headers,
        _create_competition,
        _payload,
        _seed_reg,
    )

    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_reg(session_manager, competition_id)
    comp = await _comp_headers(client, session_manager)

    bad = _payload(ctx)
    bad.pop("coach", None)
    resp = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=bad,
        headers={**comp, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert resp.status_code == 422, resp.text
    assert any(f["name"].startswith("coach") for f in resp.json()["error"]["fields"])

    good = await client.post(
        f"/competitions/{competition_id}/registrations",
        json=_payload(ctx, coach=VALID_COACH),
        headers={**comp, "Idempotency-Key": f"idem-{uuid.uuid4()}"},
    )
    assert good.status_code == 201, good.text
