"""US-AUD-01 — Immutable audit log and data-subject rights."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select  # noqa: F401 — kept for future assertions

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    AuditEvent,
    Competitor,
    Institution,
    MarkingScheme,
    Pathway,
    Skill,
    User,
    UserRole,
    Zone,
)
from app.services.audit import verify_audit_signature, write_audit_event
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


async def _seed_competitor_with_user(
    session_manager: DBManager,
    competition_id: uuid.UUID,
) -> dict:
    async with session_manager.session() as session:
        age = (
            await session.execute(select(AgeRule).where(AgeRule.competition_id == competition_id))
        ).scalars().first()
        path = (
            await session.execute(select(Pathway).where(Pathway.competition_id == competition_id))
        ).scalars().first()
        scheme = (
            await session.execute(select(MarkingScheme).where(MarkingScheme.competition_id == competition_id))
        ).scalars().first()
        zone = (
            await session.execute(select(Zone).where(Zone.competition_id == competition_id))
        ).scalars().first()

        if age is None or path is None or scheme is None or zone is None:
            age = AgeRule(competition_id=competition_id, name="U25", max_age=25, reference_date=date(2026, 1, 1))
            path = Pathway(competition_id=competition_id, name="National")
            scheme = MarkingScheme(competition_id=competition_id, name="CIS")
            zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
            session.add_all([age, path, scheme, zone])
            await session.flush()

        inst = Institution(name=f"Aud Inst {uuid.uuid4().hex[:6]}", active=True)
        session.add(inst)
        await session.flush()

        skill = (
            await session.execute(select(Skill).where(Skill.competition_id == competition_id))
        ).scalars().first()
        if skill is None:
            skill = Skill(
                competition_id=competition_id,
                name="Web Development",
                age_rule_id=age.id,
                pathway_id=path.id,
            scheme_id=scheme.id,
                capacity=20,
                active=True,
            )
            session.add(skill)
            await session.flush()

        user = User(
            email=f"subject-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("subject-pass-123"),
            full_name="Data Subject",
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        competitor = Competitor(
            competition_id=competition_id,
            skill_id=skill.id,
            zone_id=zone.id,
            institution_id=inst.id,
            user_id=user.id,
            ref_no=f"REF-{uuid.uuid4().hex[:8]}",
            status="REGISTERED",
            given_names="Ada",
            family_name="Lovelace",
            date_of_birth=date(2004, 5, 1),
            email="ada@example.com",
            mobile="+233200000001",
            national_id="GHA-12345",
            guardian_name="Guardian",
            guardian_email="g@example.com",
            consent_public_at=datetime.utcnow(),
            public_profile_visible=True,
            eligibility_status="ELIGIBLE",
        )
        session.add(competitor)
        await session.flush()
        await session.commit()
        return {
            "competitor_id": competitor.id,
            "user_id": user.id,
            "email": user.email,
            "password": "subject-pass-123",
        }


async def _subject_headers(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_US_AUD_01_AC1_audit_on_action(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    competition_id = await _create_competition(client, auth_headers)

    resp = await client.get(
        f"/admin/audit?entity={competition_id}&from={(datetime.utcnow() - timedelta(hours=1)).isoformat()}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    actions = {e["action"] for e in body["events"]}
    assert "COMPETITION_CREATE" in actions
    created = next(e for e in body["events"] if e["action"] == "COMPETITION_CREATE")
    assert created["actorId"]
    assert created["timestamp"]
    assert created.get("after") is not None or created.get("before") is not None


@pytest.mark.asyncio
async def test_US_AUD_01_AC2_tamper_resistance(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    admin_user: User,
) -> None:
    async with session_manager.session() as session:
        event = await write_audit_event(
            session,
            action="TEST_IMMUTABLE",
            entity_type="Competitor",
            entity_id=str(uuid.uuid4()),
            actor_id=admin_user.id,
            actor_role=admin_user.role.value,
            after={"v": 1},
        )
        await session.commit()
        event_id = event.id
        assert verify_audit_signature(event)

    # API refuses delete
    denied = await client.delete(f"/admin/audit/{event_id}", headers=auth_headers)
    assert denied.status_code in {403, 405, 409}, denied.text
    assert denied.json()["error"]["code"] in {
        "AUDIT_IMMUTABLE",
        "METHOD_NOT_ALLOWED",
        "FORBIDDEN",
    }

    # ORM / SQL update must not stick — signature still verifies original
    async with session_manager.session() as session:
        row = await session.get(AuditEvent, event_id)
        assert row is not None
        original_sig = row.signature
        row.after = {"v": 999, "tampered": True}
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    async with session_manager.session() as session:
        row = await session.get(AuditEvent, event_id)
        assert row is not None
        # Either update was blocked, or signature check fails if somehow mutated
        if row.after == {"v": 999, "tampered": True}:
            assert not verify_audit_signature(row)
        else:
            assert row.signature == original_sig
            assert verify_audit_signature(row)

    # Tamper attempt itself is audited
    audit_list = await client.get("/admin/audit", headers=auth_headers)
    assert audit_list.status_code == 200, audit_list.text
    tamper_actions = {e["action"] for e in audit_list.json()["events"]}
    assert "AUDIT_TAMPER_ATTEMPT" in tamper_actions


@pytest.mark.asyncio
async def test_US_AUD_01_AC3_access_request(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_competitor_with_user(session_manager, competition_id)
    subject_headers = await _subject_headers(client, ctx["email"], ctx["password"])

    resp = await client.post(
        "/governance/dsar",
        headers=subject_headers,
        json={"subjectId": str(ctx["competitor_id"]), "type": "ACCESS"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["jobId"]
    assert body.get("status") in {None, "COMPLETED", "QUEUED", "PROCESSING"}

    # Fetch job / export — include export on response when completed synchronously
    assert "export" in body or body.get("status") == "COMPLETED"
    export = body.get("export") or {}
    if not export:
        job = await client.get(f"/governance/dsar/{body['jobId']}", headers=subject_headers)
        assert job.status_code == 200, job.text
        export = job.json().get("export") or {}
    assert export.get("competitorId") == str(ctx["competitor_id"])
    assert "givenNames" in export or "email" in export
    assert export.get("email") == "ada@example.com"


@pytest.mark.asyncio
async def test_US_AUD_01_AC3_unverified_subject(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_competitor_with_user(session_manager, competition_id)
    # Another competitor cannot request this subject's data
    other = await _seed_competitor_with_user(session_manager, competition_id)
    other_headers = await _subject_headers(client, other["email"], other["password"])

    resp = await client.post(
        "/governance/dsar",
        headers=other_headers,
        json={"subjectId": str(ctx["competitor_id"]), "type": "ACCESS"},
    )
    assert resp.status_code in {403, 409}, resp.text
    assert resp.json()["error"]["code"] == "SUBJECT_UNVERIFIED"


@pytest.mark.asyncio
async def test_US_AUD_01_AC4_erasure_and_withdrawal(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_competitor_with_user(session_manager, competition_id)

    # Admin processes lawful erasure
    erase = await client.post(
        "/governance/dsar",
        headers=auth_headers,
        json={"subjectId": str(ctx["competitor_id"]), "type": "ERASURE"},
    )
    assert erase.status_code == 202, erase.text
    assert erase.json()["jobId"]

    async with session_manager.session() as session:
        comp = await session.get(Competitor, ctx["competitor_id"])
        assert comp is not None
        assert comp.email is None
        assert comp.national_id is None
        assert comp.given_names is None
        assert comp.ref_no  # integrity stub retained
        assert comp.id == ctx["competitor_id"]

    # Withdrawal clears public consent flags
    ctx2 = await _seed_competitor_with_user(session_manager, competition_id)
    withdraw = await client.post(
        "/governance/dsar",
        headers=auth_headers,
        json={"subjectId": str(ctx2["competitor_id"]), "type": "WITHDRAW"},
    )
    assert withdraw.status_code == 202, withdraw.text

    async with session_manager.session() as session:
        comp = await session.get(Competitor, ctx2["competitor_id"])
        assert comp is not None
        assert comp.public_profile_visible is False
        assert comp.consent_public_at is None

    # Audit retained for DSAR processing
    audit = await client.get("/admin/audit", headers=auth_headers)
    assert audit.status_code == 200, audit.text
    actions = {e["action"] for e in audit.json()["events"]}
    assert "DSAR_ERASURE" in actions or "DSAR_PROCESS" in actions
    assert "DSAR_WITHDRAW" in actions or "DSAR_PROCESS" in actions
