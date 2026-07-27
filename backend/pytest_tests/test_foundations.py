"""Foundation tests: error envelope, RBAC, audit, storage, config resolution."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, error_envelope
from app.core.rbac import (
    Capability,
    check_conflict_of_interest,
    check_segregation_of_duties,
    has_capability,
)
from app.models import Competition, CompetitionStatus, User, UserRole
from app.services.audit import verify_audit_signature, write_audit_event
from app.services.config_resolution import ConfigIncompleteError, load_competition_config
from app.services.storage import InfectedScanner, LocalObjectStorage, ScanResult
from pytest_tests.conftest import competition_payload


@pytest.mark.asyncio
async def test_error_envelope_shape() -> None:
    body = error_envelope(code="CONFIG_INCOMPLETE", message="missing", fields=[{"name": "x", "reason": "REQUIRED"}])
    assert "error" in body
    assert body["error"]["code"] == "CONFIG_INCOMPLETE"
    assert body["error"]["fields"][0]["name"] == "x"
    assert "traceId" in body["error"]


@pytest.mark.asyncio
async def test_unauthenticated_uses_envelope(client: AsyncClient) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "traceId" in data["error"]


@pytest.mark.asyncio
async def test_rbac_capabilities() -> None:
    assert has_capability(UserRole.ADMIN, Capability.CONFIGURE_CYCLE)
    assert not has_capability(UserRole.COMPETITOR, Capability.CONFIGURE_CYCLE)
    assert has_capability(UserRole.EXPERT, Capability.SCORE_SUBMISSION)
    assert not has_capability(UserRole.EXPERT, Capability.MODERATE_SCORE)


def test_sod_and_coi() -> None:
    assert check_segregation_of_duties(scorer_id="a", moderator_id="b")
    assert not check_segregation_of_duties(scorer_id="a", moderator_id="a")
    assert check_conflict_of_interest(expert_institution_id="i1", competitor_institution_id="i1")
    assert not check_conflict_of_interest(expert_institution_id="i1", competitor_institution_id="i2")


@pytest.mark.asyncio
async def test_audit_write_and_verify(db_session: AsyncSession, admin_user: User) -> None:
    event = await write_audit_event(
        db_session,
        action="TEST",
        entity_type="Competition",
        entity_id=str(uuid.uuid4()),
        actor_id=admin_user.id,
        actor_role=admin_user.role.value,
        after={"ok": True},
    )
    await db_session.commit()
    assert verify_audit_signature(event)
    event.signature = "tampered"
    assert not verify_audit_signature(event)


@pytest.mark.asyncio
async def test_config_resolution_fail_closed(db_session: AsyncSession) -> None:
    cycle = Competition(
        name="Cfg Cycle",
        period_start=__import__("datetime").date.today(),
        period_end=__import__("datetime").date.today() + __import__("datetime").timedelta(days=10),
        time_zone="Africa/Accra",
        status=CompetitionStatus.DRAFT,
        languages=["en"],
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    cfg = await load_competition_config(db_session, cycle.id)
    with pytest.raises(ConfigIncompleteError) as exc:
        cfg.require("ageRuleId", None, entity="skill-1")
    assert exc.value.code == "CONFIG_INCOMPLETE"


@pytest.mark.asyncio
async def test_storage_scan_stub(tmp_path) -> None:
    store = LocalObjectStorage(root=tmp_path, scanner=InfectedScanner())
    with pytest.raises(AppError) as exc:
        store.put(b"virus")
    assert exc.value.code == "FILE_INFECTED"

    clean = LocalObjectStorage(root=tmp_path)
    obj = clean.put(b"hello", prefix="docs")
    assert clean.get(obj.key) == b"hello"
    assert clean.scanner.scan(b"x") == ScanResult.CLEAN


@pytest.mark.asyncio
async def test_login_and_me(client: AsyncClient, admin_user: User) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "admin-pass-123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"
    assert me.json()["email"] == admin_user.email


@pytest.mark.asyncio
async def test_competitor_forbidden_from_cycles(
    client: AsyncClient, competitor_user: User
) -> None:
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    token = login.json()["access_token"]
    resp = await client.post(
        "/competitions",
        json=competition_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
