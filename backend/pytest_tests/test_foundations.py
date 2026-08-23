"""Foundation tests: error envelope, RBAC, audit, storage, config resolution."""

from __future__ import annotations

import json
import logging
import uuid
import warnings

import pytest
from fastapi import HTTPException, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import StarletteDeprecationWarning
from starlette.requests import Request

from app.core.errors import (
    AppError,
    app_error_handler,
    error_envelope,
    http_exception_handler,
    public_message,
    unhandled_error_handler,
)
from app.core.rbac import (
    Capability,
    check_conflict_of_interest,
    check_segregation_of_duties,
    has_capability,
)
from app.main import app
from app.models import Competition, CompetitionStatus, User, UserRole
from app.services.audit import verify_audit_signature, write_audit_event
from app.services.config_resolution import ConfigIncompleteError, load_competition_config
from app.services.storage import InfectedScanner, LocalObjectStorage, ScanResult
from pytest_tests.conftest import competition_payload


def _dummy_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


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
    assert data["error"]["message"] == "Please sign in again."
    assert "traceId" in data["error"]


@pytest.mark.asyncio
async def test_http_exception_uses_envelope() -> None:
    response = await http_exception_handler(
        _dummy_request(),
        HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"),
    )
    assert response.status_code == 503
    body = json.loads(response.body)
    assert "detail" not in body
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "database" not in body["error"]["message"].lower()
    assert "temporarily unavailable" in body["error"]["message"].lower()
    assert "traceId" in body["error"]


@pytest.mark.asyncio
async def test_storage_misconfigured_message_is_humanized(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app"):
        response = await app_error_handler(
            _dummy_request(),
            AppError(
                "STORAGE_MISCONFIGURED",
                "GCS bucket not configured (set GCS_BUCKET_NAME)",
                status_code=500,
            ),
        )
    body = json.loads(response.body)
    assert body["error"]["code"] == "STORAGE_MISCONFIGURED"
    assert "GCS" not in body["error"]["message"]
    assert "bucket" not in body["error"]["message"].lower()
    assert "Something went wrong" in body["error"]["message"]
    assert "GCS bucket not configured" in caplog.text


@pytest.mark.asyncio
async def test_forbidden_capability_message_is_humanized() -> None:
    response = await app_error_handler(
        _dummy_request(),
        AppError("FORBIDDEN", "Missing capability: CONFIGURE_CYCLE", status_code=403),
    )
    body = json.loads(response.body)
    assert body["error"]["code"] == "FORBIDDEN"
    assert "capability" not in body["error"]["message"].lower()
    assert body["error"]["message"] == public_message("FORBIDDEN", 403, "x")


@pytest.mark.asyncio
async def test_http_exception_route_uses_envelope(client: AsyncClient) -> None:
    path = f"/__test_http_exc_{uuid.uuid4().hex[:8]}"

    @app.get(path)
    async def _raise_http_exc() -> None:
        raise HTTPException(status_code=404, detail="missing thing")

    try:
        resp = await client.get(path)
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" not in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["message"] == "We could not find what you were looking for."
        assert "traceId" in data["error"]
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != path
        ]


@pytest.mark.asyncio
async def test_unhandled_error_logs_and_envelopes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="app"):
        response = await unhandled_error_handler(_dummy_request(), RuntimeError("boom"))
    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" not in body["error"]["message"]
    assert "Something went wrong" in body["error"]["message"]
    assert "unhandled error" in caplog.text
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_unhandled_route_uses_envelope(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    path = f"/__test_boom_{uuid.uuid4().hex[:8]}"

    @app.get(path)
    async def _boom() -> None:
        raise RuntimeError("intentional boom")

    try:
        with caplog.at_level(logging.ERROR):
            resp = await client.get(path)
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "traceId" in data["error"]
        # Exception handlers return INTERNAL_ERROR; unhandled_error_handler logs the boom.
        assert "intentional boom" in caplog.text
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != path
        ]


def test_app_error_422_uses_content_constant_without_deprecation() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", StarletteDeprecationWarning)
        err = AppError(
            "FILE_TYPE",
            "bad type",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    assert err.status_code == 422
    assert not any(issubclass(w.category, StarletteDeprecationWarning) for w in caught)


@pytest.mark.asyncio
async def test_validation_error_uses_envelope(client: AsyncClient) -> None:
    resp = await client.post("/auth/login", json={})
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" not in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "traceId" in data["error"]
    assert isinstance(data["error"]["fields"], list)


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
