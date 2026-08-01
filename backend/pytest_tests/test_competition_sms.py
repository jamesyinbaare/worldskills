"""Competition soft-activate + competitor/coach SMS communications."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    Competition,
    CompetitionStatus,
    Competitor,
    Exercise,
    MarkingScheme,
    SmsDelivery,
    Stage,
    User,
    UserRole,
)
from app.services.sms.phone import normalize_msisdn
from pytest_tests.conftest import competition_payload, seed_complete_config


def test_normalize_msisdn_ghana() -> None:
    assert normalize_msisdn("0551234567") == "233551234567"
    assert normalize_msisdn("+233551234567") == "233551234567"
    assert normalize_msisdn("233551234567") == "233551234567"
    assert normalize_msisdn("551234567") == "233551234567"
    with pytest.raises(ValueError):
        normalize_msisdn("")
    with pytest.raises(ValueError):
        normalize_msisdn("12345")


@pytest.mark.asyncio
async def test_activate_without_exercises_advisory_only(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    competition_id = uuid.UUID(create.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        await seed_complete_config(session, cycle, with_exercises=False)

    validate = await client.post(f"/competitions/{competition_id}:validate", headers=auth_headers)
    assert validate.status_code == 200, validate.text
    body = validate.json()
    assert body["ok"] is True
    advisories = [i for i in body["issues"] if i.get("severity") == "advisory"]
    assert any(i["code"] == "EXERCISE_PENDING" for i in advisories)
    assert not any(i.get("severity") != "advisory" for i in body["issues"])

    activate = await client.post(f"/competitions/{competition_id}:activate", headers=auth_headers)
    assert activate.status_code == 200, activate.text
    assert activate.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_exercise_available_sms_on_publish_and_dedupe(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    competition_id = uuid.UUID(create.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        await seed_complete_config(session, cycle, with_exercises=False)
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        stage = (
            await session.execute(
                select(Stage).where(Stage.competition_id == competition_id).order_by(Stage.order)
            )
        ).scalars().first()
        assert stage is not None
        scheme = (
            await session.execute(
                select(MarkingScheme).where(MarkingScheme.competition_id == competition_id)
            )
        ).scalar_one()
        competitor_user = User(
            email=f"sms-comp-{uuid.uuid4().hex[:8]}@example.com",
            full_name="SMS Comp",
            hashed_password=get_password_hash("comp-pass-1234"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor_user)
        await session.flush()
        session.add(
            Competitor(
                competition_id=competition_id,
                skill_id=stage.skill_id,
                zone_id=None,
                ref_no=f"REF-{uuid.uuid4().hex[:8]}",
                status="REGISTERED",
                eligibility_status="ELIGIBLE",
                given_names="Ama",
                family_name="Mensah",
                mobile="0551112233",
                whatsapp="0551112233",
                coach={
                    "surname": "Coach",
                    "firstName": "Kwame",
                    "contactNumber": "0559998877",
                    "whatsapp": "0559998877",
                    "email": "coach@example.com",
                    "dateOfBirth": "1980-01-01",
                },
                user_id=competitor_user.id,
            )
        )
        await session.commit()
        stage_id = stage.id
        scheme_uuid = scheme.id

    put = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json={
            "title": "Regional challenge",
            "brief": "Build it",
            "deliverables": [
                {
                    "code": "main",
                    "label": "Main",
                    "required": True,
                    "allowedTypes": ["pdf"],
                    "maxSizeBytes": None,
                }
            ],
            "schemeId": str(scheme_uuid),
            "latePolicy": "block",
        },
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text

    pub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub.status_code == 200, pub.text

    async with session_manager.session() as session:
        rows = (
            await session.execute(
                select(SmsDelivery).where(
                    SmsDelivery.competition_id == competition_id,
                    SmsDelivery.message_type == "EXERCISE_AVAILABLE",
                    SmsDelivery.status == "sent",
                )
            )
        ).scalars().all()
        roles = {r.recipient_role for r in rows}
        assert "competitor" in roles
        assert "coach" in roles
        assert len(rows) == 2

    # Admin re-notify should send again (force bypasses dedupe)
    notify = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:notify",
        headers=auth_headers,
    )
    assert notify.status_code == 200, notify.text
    assert notify.json()["competitorSent"] == 1
    assert notify.json()["coachSent"] == 1

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(SmsDelivery)
                .where(
                    SmsDelivery.competition_id == competition_id,
                    SmsDelivery.message_type == "EXERCISE_AVAILABLE",
                    SmsDelivery.status == "sent",
                )
            )
        ).scalar_one()
        assert count == 4


@pytest.mark.asyncio
async def test_exercise_available_deferred_until_window_opens(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    competition_id = uuid.UUID(create.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        await seed_complete_config(session, cycle, with_exercises=False)
        stage = (
            await session.execute(
                select(Stage).where(Stage.competition_id == competition_id).order_by(Stage.order)
            )
        ).scalars().first()
        assert stage is not None
        stage.opens_at = datetime.utcnow() + timedelta(days=2)
        scheme = (
            await session.execute(
                select(MarkingScheme).where(MarkingScheme.competition_id == competition_id)
            )
        ).scalar_one()
        session.add(
            Competitor(
                competition_id=competition_id,
                skill_id=stage.skill_id,
                ref_no=f"REF-{uuid.uuid4().hex[:8]}",
                status="REGISTERED",
                given_names="Deferred",
                family_name="Comp",
                mobile="0552223344",
                coach={
                    "surname": "C",
                    "firstName": "D",
                    "contactNumber": "0553334455",
                    "whatsapp": "0553334455",
                    "email": "c@example.com",
                    "dateOfBirth": "1975-05-05",
                },
            )
        )
        await session.commit()
        stage_id = stage.id
        scheme_id = scheme.id

    put = await client.put(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise",
        json={
            "title": "Future challenge",
            "deliverables": [
                {
                    "code": "main",
                    "required": True,
                    "allowedTypes": ["pdf"],
                }
            ],
            "schemeId": str(scheme_id),
        },
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    pub = await client.post(
        f"/competitions/{competition_id}/stages/{stage_id}/exercise:publish",
        headers=auth_headers,
    )
    assert pub.status_code == 200, pub.text

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(SmsDelivery)
                .where(
                    SmsDelivery.competition_id == competition_id,
                    SmsDelivery.message_type == "EXERCISE_AVAILABLE",
                )
            )
        ).scalar_one()
        assert count == 0
        ex = (
            await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
        ).scalar_one()
        assert ex.availability_notified_at is None

    # Open the window then poll
    async with session_manager.session() as session:
        stage = await session.get(Stage, stage_id)
        assert stage is not None
        stage.opens_at = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()

    poll = await client.post(
        "/competitions:poll-exercise-availability-notifications",
        headers=auth_headers,
    )
    assert poll.status_code == 200, poll.text
    assert len(poll.json()["results"]) >= 1

    async with session_manager.session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(SmsDelivery)
                .where(
                    SmsDelivery.competition_id == competition_id,
                    SmsDelivery.message_type == "EXERCISE_AVAILABLE",
                    SmsDelivery.status == "sent",
                )
            )
        ).scalar_one()
        assert count == 2


@pytest.mark.asyncio
async def test_submission_received_sms(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    """Finalise triggers SUBMISSION_RECEIVED SMS; invalid phone still accepts submission."""
    from app.models import Artefact, Submission

    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    competition_id = uuid.UUID(create.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        await seed_complete_config(session, cycle, with_exercises=True)
        stage = (
            await session.execute(
                select(Stage).where(Stage.competition_id == competition_id).order_by(Stage.order)
            )
        ).scalars().first()
        assert stage is not None
        stage.closes_at = datetime.utcnow() + timedelta(days=7)
        competitor_user = User(
            email=f"sub-sms-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Sub SMS",
            hashed_password=get_password_hash("comp-pass-1234"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor_user)
        await session.flush()
        competitor = Competitor(
            competition_id=competition_id,
            skill_id=stage.skill_id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="ACTIVE_IN_STAGE",
            eligibility_status="ELIGIBLE",
            given_names="Kofi",
            family_name="Boateng",
            mobile="0554445566",
            coach={
                "surname": "Coach",
                "firstName": "Bad",
                "contactNumber": "not-a-phone",
                "whatsapp": "bad",
                "email": "bad@example.com",
                "dateOfBirth": "1970-01-01",
            },
            user_id=competitor_user.id,
        )
        session.add(competitor)
        await session.flush()
        submission = Submission(
            competition_id=competition_id,
            competitor_id=competitor.id,
            stage_id=stage.id,
            state="UPLOADED",
        )
        session.add(submission)
        await session.flush()
        session.add(
            Artefact(
                submission_id=submission.id,
                deliverable_code="main",
                filename="main.pdf",
                content_type="application/pdf",
                size=100,
                storage_key=f"test/{submission.id}/main.pdf",
                sha256="abc123",
                complete=True,
                scan_status="CLEAN",
                quarantined=False,
            )
        )
        await session.commit()
        submission_id = submission.id
        email = competitor_user.email

    login = await client.post("/auth/login", json={"email": email, "password": "comp-pass-1234"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    finalise = await client.post(f"/submissions/{submission_id}:finalise", headers=headers)
    assert finalise.status_code == 200, finalise.text
    assert finalise.json()["state"] in {"ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"}
    assert finalise.json()["receipt"]

    async with session_manager.session() as session:
        rows = (
            await session.execute(
                select(SmsDelivery).where(
                    SmsDelivery.submission_id == submission_id,
                    SmsDelivery.message_type == "SUBMISSION_RECEIVED",
                )
            )
        ).scalars().all()
        by_role = {r.recipient_role: r for r in rows}
        assert by_role["competitor"].status == "sent"
        assert by_role["coach"].status == "failed"


@pytest.mark.asyncio
async def test_admin_competitors_excel_export(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    competition_id = uuid.UUID(create.json()["competitionId"])

    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        await seed_complete_config(session, cycle, with_exercises=False)
        stage = (
            await session.execute(
                select(Stage).where(Stage.competition_id == competition_id).order_by(Stage.order)
            )
        ).scalars().first()
        assert stage is not None
        skill_id = stage.skill_id
        session.add(
            Competitor(
                competition_id=competition_id,
                skill_id=skill_id,
                zone_id=None,
                ref_no=f"REF-{uuid.uuid4().hex[:8]}",
                status="REGISTERED",
                eligibility_status="ELIGIBLE",
                given_names="Ama",
                family_name="Mensah",
                email="ama@example.com",
                mobile="0551112233",
                coach={
                    "surname": "Coach",
                    "firstName": "Kwame",
                    "contactNumber": "0559998877",
                    "whatsapp": "0559998877",
                    "email": "coach@example.com",
                },
                user_id=None,
            )
        )
        await session.commit()

    export = await client.get(
        f"/competitions/{competition_id}/competitors:export",
        params={"skillId": str(skill_id)},
        headers=auth_headers,
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert export.content[:2] == b"PK"
    assert "attachment" in export.headers.get("content-disposition", "")
    assert ".xlsx" in export.headers.get("content-disposition", "")
