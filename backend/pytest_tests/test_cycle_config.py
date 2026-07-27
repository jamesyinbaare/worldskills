"""Competition config APIs — age rules, pathways, marking schemes for skill linking."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import AgeRule, AuditEvent, MarkingScheme, Pathway, User
from pytest_tests.conftest import competition_payload


async def _create_draft_cycle(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


@pytest.mark.asyncio
async def test_age_rule_list_and_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)

    empty = await client.get(f"/competitions/{competition_id}/age-rules", headers=auth_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    create = await client.post(
        f"/competitions/{competition_id}/age-rules",
        json={
            "name": "U25",
            "maxAge": 25,
            "referenceDate": "2026-01-01",
            "openCategoryEnabled": True,
        },
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "U25"
    assert body["maxAge"] == 25
    assert body["referenceDate"] == "2026-01-01"
    assert body["openCategoryEnabled"] is True
    assert "ageRuleId" in body

    listed = await client.get(f"/competitions/{competition_id}/age-rules", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["ageRuleId"] == body["ageRuleId"]

    async with session_manager.session() as session:
        rule = await session.get(AgeRule, uuid.UUID(body["ageRuleId"]))
        assert rule is not None
        audit = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "AGE_RULE_CREATE",
                    AuditEvent.entity_id == body["ageRuleId"],
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_pathway_list_and_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)

    create = await client.post(
        f"/competitions/{competition_id}/pathways",
        json={"name": "National"},
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "National"
    assert "pathwayId" in body

    listed = await client.get(f"/competitions/{competition_id}/pathways", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    async with session_manager.session() as session:
        path = await session.get(Pathway, uuid.UUID(body["pathwayId"]))
        assert path is not None


@pytest.mark.asyncio
async def test_marking_scheme_list_and_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)

    create = await client.post(
        f"/competitions/{competition_id}/marking-schemes",
        json={"name": "CIS"},
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "CIS"
    assert "schemeId" in body

    listed = await client.get(f"/competitions/{competition_id}/marking-schemes", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    async with session_manager.session() as session:
        scheme = await session.get(MarkingScheme, uuid.UUID(body["schemeId"]))
        assert scheme is not None


@pytest.mark.asyncio
async def test_cycle_config_not_found_and_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    competitor_user: User,
) -> None:
    missing = uuid.uuid4()
    resp = await client.get(f"/competitions/{missing}/age-rules", headers=auth_headers)
    assert resp.status_code == 404

    competition_id = await _create_draft_cycle(client, auth_headers)
    login = await client.post(
        "/auth/login",
        json={"email": competitor_user.email, "password": "comp-pass-123"},
    )
    assert login.status_code == 200
    comp_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    denied = await client.post(
        f"/competitions/{competition_id}/pathways",
        json={"name": "X"},
        headers=comp_headers,
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_age_rule_validation(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    competition_id = await _create_draft_cycle(client, auth_headers)
    bad = await client.post(
        f"/competitions/{competition_id}/age-rules",
        json={"name": "   ", "maxAge": 25},
        headers=auth_headers,
    )
    assert bad.status_code == 422
