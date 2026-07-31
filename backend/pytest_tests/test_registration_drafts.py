"""Registration draft save / resume / submit-from-draft."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import Competitor, Skill
from pytest_tests.conftest import create_competitor_account, login_as
from pytest_tests.test_us_reg_01 import _PNG_1X1, _create_competition, _seed_reg


def _adult_payload(skill_id: uuid.UUID, institution_id: uuid.UUID, region_id: uuid.UUID) -> dict:
    return {
        "givenNames": "Ama",
        "familyName": "Mensah",
        "gender": "Female",
        "dateOfBirth": "2000-05-01",
        "email": "ama@example.com",
        "mobile": "+233201112233",
        "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
        "nationality": "GH",
        "hasPassport": False,
        "institutionId": str(institution_id),
        "regionId": str(region_id),
        "skillIds": [str(skill_id)],
        "declarationAccepted": True,
        "captchaToken": "ok",
        "coach": {
            "surname": "Owusu",
            "firstName": "Kwame",
            "contactNumber": "+233209998877",
            "email": "coach@example.com",
            "whatsapp": "+233209998877",
            "dateOfBirth": "1985-03-12",
        },
        "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
    }


@pytest.mark.asyncio
async def test_registration_draft_upsert_get_and_submit(
    client: AsyncClient,
    session_manager: DBManager,
    auth_headers: dict[str, str],
):
    competition_id = await _create_competition(client, auth_headers)
    ids = await _seed_reg(session_manager, competition_id)
    skill_id = ids["skill_id"]
    institution_id = ids["institution_id"]
    region_id = ids["region_id"]

    user, password = await create_competitor_account(session_manager)
    headers = await login_as(client, user.email, password)

    missing = await client.get(
        f"/competitions/{competition_id}/registrations/draft", headers=headers
    )
    assert missing.status_code == 404

    save = await client.put(
        f"/competitions/{competition_id}/registrations/draft",
        headers=headers,
        json={
            "givenNames": "Ama",
            "familyName": "Mensah",
            "gender": "Female",
            "dateOfBirth": "2000-05-01",
            "email": "ama@example.com",
            "mobile": "+233201112233",
            "nationalId": f"GHA-{uuid.uuid4().int % 10**9:09d}",
            "currentStep": 1,
        },
    )
    assert save.status_code == 200, save.text
    body = save.json()
    assert body["status"] == "DRAFT"
    assert body["givenNames"] == "Ama"
    assert body["currentStep"] == 1
    draft_id = body["competitorId"]

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Competitor)
                .where(Competitor.competition_id == competition_id)
            )
        ).scalar_one()
        assert int(count) == 1
        draft = await session.get(Competitor, uuid.UUID(draft_id))
        assert draft is not None
        assert draft.status == "DRAFT"
        assert draft.ref_no is None

    got = await client.get(
        f"/competitions/{competition_id}/registrations/draft", headers=headers
    )
    assert got.status_code == 200
    assert got.json()["competitorId"] == draft_id

    save2 = await client.put(
        f"/competitions/{competition_id}/registrations/draft",
        headers=headers,
        json={
            "hasPassport": False,
            "institutionId": str(institution_id),
            "regionId": str(region_id),
            "skillIds": [str(skill_id)],
            "coach": {
                "surname": "Owusu",
                "firstName": "Kwame",
                "contactNumber": "+233209998877",
                "email": "coach@example.com",
                "whatsapp": "+233209998877",
                "dateOfBirth": "1985-03-12",
            },
            "currentStep": 4,
        },
    )
    assert save2.status_code == 200, save2.text
    assert save2.json()["competitorId"] == draft_id
    assert save2.json()["currentStep"] == 4
    assert save2.json()["institutionId"] == str(institution_id)
    assert save2.json()["institutionName"]
    assert save2.json()["institutionCode"]

    photo_missing = await client.get(
        f"/competitions/{competition_id}/registrations/draft/photo",
        headers=headers,
    )
    assert photo_missing.status_code == 404

    with_photo = await client.put(
        f"/competitions/{competition_id}/registrations/draft",
        headers=headers,
        json={
            "photo": {"contentBase64": _PNG_1X1, "contentType": "image/png"},
            "currentStep": 1,
        },
    )
    assert with_photo.status_code == 200, with_photo.text
    assert with_photo.json()["hasPhoto"] is True

    photo = await client.get(
        f"/competitions/{competition_id}/registrations/draft/photo",
        headers=headers,
    )
    assert photo.status_code == 200, photo.text
    assert photo.headers["content-type"].startswith("image/")
    assert photo.content.startswith(b"\x89PNG")

    async with session_manager.session() as session:
        skill = await session.get(Skill, skill_id)
        assert skill is not None
        skill.school_quota = 1
        await session.commit()

    # Submit without re-uploading photo — draft photo must satisfy the required field.
    submit_payload = _adult_payload(skill_id, institution_id, region_id)
    del submit_payload["photo"]
    submit = await client.post(
        f"/competitions/{competition_id}/registrations",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json=submit_payload,
    )
    assert submit.status_code == 201, submit.text
    out = submit.json()
    assert out["competitorId"] == draft_id
    assert out["status"] == "PENDING_REVIEW"
    assert out["competitorRef"].startswith("WSG-")

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Competitor)
                .where(Competitor.competition_id == competition_id)
            )
        ).scalar_one()
        assert int(count) == 1
        finalized = await session.get(Competitor, uuid.UUID(draft_id))
        assert finalized is not None
        assert finalized.status == "PENDING_REVIEW"
        assert finalized.ref_no is not None

    after = await client.get(
        f"/competitions/{competition_id}/registrations/draft", headers=headers
    )
    assert after.status_code == 404

    again = await client.post(
        f"/competitions/{competition_id}/registrations",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json=_adult_payload(skill_id, institution_id, region_id),
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_draft_excluded_from_quota_until_submit(
    client: AsyncClient,
    session_manager: DBManager,
    auth_headers: dict[str, str],
):
    competition_id = await _create_competition(client, auth_headers)
    ids = await _seed_reg(session_manager, competition_id)
    skill_id = ids["skill_id"]
    institution_id = ids["institution_id"]
    region_id = ids["region_id"]

    async with session_manager.session() as session:
        skill = await session.get(Skill, skill_id)
        assert skill is not None
        skill.school_quota = 1
        await session.commit()

    user1, password1 = await create_competitor_account(session_manager)
    headers = await login_as(client, user1.email, password1)

    draft = await client.put(
        f"/competitions/{competition_id}/registrations/draft",
        headers=headers,
        json={
            "skillIds": [str(skill_id)],
            "institutionId": str(institution_id),
            "regionId": str(region_id),
            "currentStep": 3,
        },
    )
    assert draft.status_code == 200, draft.text

    user2, password2 = await create_competitor_account(session_manager)
    headers2 = await login_as(client, user2.email, password2)
    payload = _adult_payload(skill_id, institution_id, region_id)
    payload["email"] = user2.email
    created = await client.post(
        f"/competitions/{competition_id}/registrations",
        headers={**headers2, "Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    assert created.status_code == 201, created.text
