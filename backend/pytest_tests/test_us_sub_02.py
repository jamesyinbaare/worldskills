"""US-SUB-02 — Competitor submits work with evidence, scanning, timing and deadline control."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    Artefact,
    AuditEvent,
    Competitor,
    CycleStatus,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    Submission,
    User,
    Zone,
)
from app.services.storage import EICAR_SIGNATURE
from pytest_tests.conftest import cycle_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/cycles", json=cycle_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["cycleId"])


async def _seed_submission_world(
    session_manager: DBManager,
    cycle_id: uuid.UUID,
    competitor_user: User,
    *,
    closes_in_hours: float = 24,
    late_policy: str = "block",
    timed_seconds: int | None = None,
    opens_offset_hours: float = -1,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (stage_id, competitor_id)."""
    now = datetime.utcnow()
    async with session_manager.session() as session:
        age = AgeRule(cycle_id=cycle_id, name="U25", max_age=25)
        path = Pathway(cycle_id=cycle_id, name="National")
        scheme = MarkingScheme(cycle_id=cycle_id, name="CIS")
        zone = Zone(cycle_id=cycle_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()
        skill = Skill(
            cycle_id=cycle_id,
            name="Web Development",
            age_rule_id=age.id,
            pathway_id=path.id,
            scheme_id=scheme.id,
            capacity=20,
            active=True,
        )
        session.add(skill)
        await session.flush()
        rules: dict = {
            "requiredDeliverables": [
                {"code": "main", "formats": ["pdf", "zip"], "maxMb": 20},
                {"code": "photo", "formats": ["jpg", "png"], "maxMb": 5},
            ],
            "latePolicy": late_policy,
        }
        if timed_seconds is not None:
            rules["timedDurationSeconds"] = timed_seconds
        stage = Stage(
            cycle_id=cycle_id,
            skill_id=skill.id,
            name="Regional Project",
            order=1,
            quota=20,
            scheme_id=scheme.id,
            opens_at=now + timedelta(hours=opens_offset_hours),
            closes_at=now + timedelta(hours=closes_in_hours),
            submission_rules=rules,
        )
        session.add(stage)
        await session.flush()
        competitor = Competitor(
            cycle_id=cycle_id,
            skill_id=skill.id,
            zone_id=zone.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="REGISTERED",
            eligibility_status="ELIGIBLE",
            user_id=competitor_user.id,
            given_names="Ada",
            family_name="Lovelace",
            email=competitor_user.email,
        )
        session.add(competitor)
        cycle = await session.get(
            __import__("app.models", fromlist=["Cycle"]).Cycle, cycle_id
        )
        if cycle is not None:
            cycle.status = CycleStatus.ACTIVE
        await session.commit()
        return stage.id, competitor.id


async def _competitor_headers(client: AsyncClient, competitor_user: User) -> dict[str, str]:
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _open_submission(
    client: AsyncClient,
    headers: dict[str, str],
    cycle_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> uuid.UUID:
    resp = await client.post(
        f"/cycles/{cycle_id}/stages/{stage_id}/submissions",
        headers=headers,
    )
    assert resp.status_code in {200, 201}, resp.text
    return uuid.UUID(resp.json()["submissionId"])


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    submission_id: uuid.UUID,
    *,
    code: str,
    filename: str,
    data: bytes,
) -> object:
    return await client.post(
        f"/submissions/{submission_id}/artefacts",
        headers={
            **headers,
            "X-Deliverable-Code": code,
            "X-Filename": filename,
            "X-Content-Type": "application/octet-stream",
        },
        content=data,
    )


@pytest.mark.asyncio
async def test_US_SUB_02_AC1_on_time_complete(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(
        session_manager, cycle_id, competitor_user, closes_in_hours=24
    )
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    up1 = await _upload(client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF-project")
    assert up1.status_code == 202, up1.text
    assert up1.json()["scan"] == "CLEAN"

    up2 = await _upload(client, headers, sub_id, code="photo", filename="shot.jpg", data=b"\xff\xd8jpeg")
    assert up2.status_code == 202, up2.text

    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 200, fin.text
    body = fin.json()
    assert body["state"] == "ACCEPTED"
    assert body["hash"]
    assert body["receipt"]
    assert body["late"] is False

    async with session_manager.session() as session:
        sub = await session.get(Submission, sub_id)
        assert sub is not None
        assert sub.state == "ACCEPTED"
        assert sub.upload_locked is True
        assert sub.content_hash == body["hash"]
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "SUBMISSION_FINALISE",
                    AuditEvent.entity_id == str(sub_id),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_US_SUB_02_AC2_missing_deliverable(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(session_manager, cycle_id, competitor_user)
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    await _upload(client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF")

    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 409
    err = fin.json()["error"]
    assert err["code"] == "DELIVERABLE_MISSING"
    assert any(f["name"] == "photo" and f["reason"] == "DELIVERABLE_MISSING" for f in err["fields"])


@pytest.mark.asyncio
async def test_US_SUB_02_AC3_malware_eicar(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(session_manager, cycle_id, competitor_user)
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    infected = await _upload(
        client, headers, sub_id, code="main", filename="virus.pdf", data=EICAR_SIGNATURE
    )
    assert infected.status_code == 400
    assert infected.json()["error"]["code"] == "FILE_INFECTED"

    async with session_manager.session() as session:
        arts = (
            await session.execute(select(Artefact).where(Artefact.submission_id == sub_id))
        ).scalars().all()
        assert len(arts) == 1
        assert arts[0].quarantined is True
        assert arts[0].scan_status == "INFECTED"
        sub = await session.get(Submission, sub_id)
        assert sub is not None
        assert sub.state == "QUARANTINED"

    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 409


@pytest.mark.asyncio
async def test_US_SUB_02_AC4_late_submission_block_and_flag(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(
        session_manager, cycle_id, competitor_user, closes_in_hours=-1, late_policy="block"
    )
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    # Uploads may still be attempted; finalise must refuse under block policy
    await _upload(client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF")
    await _upload(client, headers, sub_id, code="photo", filename="shot.jpg", data=b"jpg")

    blocked = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "DEADLINE_PASSED"

    # Flag-late policy: accepted and marked LATE
    cycle_id2 = await _create_draft_cycle(client, auth_headers)
    stage_id2, _ = await _seed_submission_world(
        session_manager, cycle_id2, competitor_user, closes_in_hours=-1, late_policy="flag-late"
    )
    # Bind same user — open on new cycle needs competitor row (seed creates another)
    sub_id2 = await _open_submission(client, headers, cycle_id2, stage_id2)
    await _upload(client, headers, sub_id2, code="main", filename="work.pdf", data=b"%PDF")
    await _upload(client, headers, sub_id2, code="photo", filename="shot.jpg", data=b"jpg")
    flagged = await client.post(f"/submissions/{sub_id2}:finalise", headers=headers)
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["state"] == "LATE"
    assert flagged.json()["late"] is True


@pytest.mark.asyncio
async def test_US_SUB_02_AC5_timed_auto_submit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(
        session_manager,
        cycle_id,
        competitor_user,
        closes_in_hours=24,
        timed_seconds=3600,
    )
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    await _upload(client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF")
    # photo missing — timer expiry still captures what's present

    async with session_manager.session() as session:
        sub = await session.get(Submission, sub_id)
        assert sub is not None
        sub.timed_expires_at = datetime.utcnow() - timedelta(seconds=1)
        await session.commit()

    # Further upload blocked after expire endpoint
    expired = await client.post(f"/submissions/{sub_id}:expire-timer", headers=headers)
    assert expired.status_code == 200, expired.text
    assert expired.json()["state"] in {"ACCEPTED", "LATE"}
    assert expired.json()["hash"]

    blocked_upload = await _upload(
        client, headers, sub_id, code="photo", filename="late.jpg", data=b"jpg"
    )
    assert blocked_upload.status_code == 409
    assert blocked_upload.json()["error"]["code"] == "SUBMISSION_LOCKED"


@pytest.mark.asyncio
async def test_US_SUB_02_AC6_resumable_chunked_upload(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(session_manager, cycle_id, competitor_user)
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    # Simpler deliverable rules: only main for video-sized zip
    video = b"VIDEO-CHUNK-AAAA" + b"B" * 100 + b"VIDEO-CHUNK-CCCC"
    total = len(video)
    mid = total // 2

    session_resp = await client.post(
        f"/submissions/{sub_id}/artefacts/sessions",
        headers=headers,
        json={
            "deliverableCode": "main",
            "filename": "entry.zip",
            "contentType": "application/zip",
            "totalSize": total,
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    upload_id = session_resp.json()["uploadId"]

    part1 = video[:mid]
    r1 = await client.put(
        f"/submissions/{sub_id}/artefacts/sessions/{upload_id}",
        headers={
            **headers,
            "Content-Range": f"bytes 0-{mid - 1}/{total}",
        },
        content=part1,
    )
    assert r1.status_code == 202, r1.text
    assert r1.json()["complete"] is False
    assert r1.json()["receivedBytes"] == mid

    # Simulate dropped connection — resume from last offset (wrong offset rejected)
    bad = await client.put(
        f"/submissions/{sub_id}/artefacts/sessions/{upload_id}",
        headers={
            **headers,
            "Content-Range": f"bytes 0-{mid - 1}/{total}",
        },
        content=part1,
    )
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "UPLOAD_OFFSET_MISMATCH"

    part2 = video[mid:]
    r2 = await client.put(
        f"/submissions/{sub_id}/artefacts/sessions/{upload_id}",
        headers={
            **headers,
            "Content-Range": f"bytes {mid}-{total - 1}/{total}",
        },
        content=part2,
    )
    assert r2.status_code == 202, r2.text
    assert r2.json()["complete"] is True
    assert r2.json()["scan"] == "CLEAN"
    assert r2.json()["receivedBytes"] == total

    # Still need photo for finalise
    await _upload(client, headers, sub_id, code="photo", filename="shot.jpg", data=b"jpg")
    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["state"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_US_SUB_02_file_type_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    cycle_id = await _create_draft_cycle(client, auth_headers)
    stage_id, _ = await _seed_submission_world(session_manager, cycle_id, competitor_user)
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, cycle_id, stage_id)

    bad = await _upload(client, headers, sub_id, code="main", filename="hack.exe", data=b"MZ")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "FILE_TYPE"
