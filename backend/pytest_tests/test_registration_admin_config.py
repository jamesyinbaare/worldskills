"""Admin registration window + form configuration."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


@pytest.mark.asyncio
async def test_admin_upsert_registration_window_and_form(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    now = datetime.utcnow()
    opens = (now - timedelta(days=1)).isoformat()
    closes = (now + timedelta(days=30)).isoformat()

    empty = await client.get(
        f"/competitions/{competition_id}/registration-window", headers=auth_headers
    )
    assert empty.status_code == 200
    assert empty.json() is None

    put_win = await client.put(
        f"/competitions/{competition_id}/registration-window",
        json={"opensAt": opens, "closesAt": closes},
        headers=auth_headers,
    )
    assert put_win.status_code == 200, put_win.text
    assert put_win.json()["opensAt"]
    assert put_win.json()["closesAt"]

    get_win = await client.get(
        f"/competitions/{competition_id}/registration-window", headers=auth_headers
    )
    assert get_win.status_code == 200
    assert get_win.json()["closesAt"] == put_win.json()["closesAt"]

    put_form = await client.put(
        f"/competitions/{competition_id}/registration-form-admin",
        json={"useDefaults": True},
        headers=auth_headers,
    )
    assert put_form.status_code == 200, put_form.text
    assert put_form.json()["maxSkills"] == 1
    assert len(put_form.json()["fields"]) >= 5

    open_list = await client.get("/competitions:open-for-registration")
    # Draft cycle should not appear even with open window
    assert open_list.status_code == 200
    assert str(competition_id) not in {c["competitionId"] for c in open_list.json()}


@pytest.mark.asyncio
async def test_validate_requires_registration_window(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    validated = await client.post(
        f"/competitions/{competition_id}:validate", headers=auth_headers
    )
    assert validated.status_code == 200, validated.text
    body = validated.json()
    messages = [i["message"] for i in body["issues"]]
    assert any("Registration window" in m for m in messages)
    assert any("Registration form" in m for m in messages)
