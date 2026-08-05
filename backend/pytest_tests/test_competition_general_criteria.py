"""Competition general criteria document."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    Competition,
    CompetitionStatus,
    Institution,
    Region,
    RegistrationWindow,
    User,
    UserRole,
)
from pytest_tests.conftest import competition_payload


async def _create_competition(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    resp = await client.post("/competitions", json=competition_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["competitionId"])


@pytest.mark.asyncio
async def test_general_criteria_document_upload_and_download_acl(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)

    pdf = b"%PDF-1.4 general-criteria"
    upload = await client.post(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=auth_headers,
        files={"file": ("general.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["hasGeneralCriteriaDocument"] is True
    assert upload.json()["generalCriteriaFileName"] == "general.pdf"

    get_cycle = await client.get(f"/competitions/{competition_id}", headers=auth_headers)
    assert get_cycle.status_code == 200, get_cycle.text
    assert get_cycle.json()["hasGeneralCriteriaDocument"] is True

    admin_dl = await client.get(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=auth_headers,
    )
    assert admin_dl.status_code == 200, admin_dl.text
    assert admin_dl.content.startswith(b"%PDF")

    async with session_manager.session() as session:
        region = (await session.execute(select(Region).limit(1))).scalar_one_or_none()
        if region is None:
            region = Region(name=f"Region-{uuid.uuid4().hex[:6]}")
            session.add(region)
            await session.flush()
        inst = Institution(
            name=f"School-{uuid.uuid4().hex[:6]}",
            region_id=region.id,
        )
        session.add(inst)
        await session.flush()
        inst_user = User(
            email=f"inst-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Institution User",
            hashed_password=get_password_hash("inst-pass-123"),
            role=UserRole.INSTITUTION,
            is_active=True,
            institution_id=inst.id,
        )
        session.add(inst_user)
        await session.commit()
        email = inst_user.email

    login = await client.post(
        "/auth/login", json={"email": email, "password": "inst-pass-123"}
    )
    assert login.status_code == 200, login.text
    inst_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    dl = await client.get(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=inst_headers,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content.startswith(b"%PDF")

    async with session_manager.session() as session:
        competitor = User(
            email=f"comp-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Competitor User",
            hashed_password=get_password_hash("comp-pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(competitor)
        await session.commit()
        comp_email = competitor.email

    clogin = await client.post(
        "/auth/login", json={"email": comp_email, "password": "comp-pass-123"}
    )
    assert clogin.status_code == 200, clogin.text
    comp_headers = {"Authorization": f"Bearer {clogin.json()['access_token']}"}
    denied = await client.get(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=comp_headers,
    )
    assert denied.status_code == 403, denied.text

    deleted = await client.delete(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=auth_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["hasGeneralCriteriaDocument"] is False


@pytest.mark.asyncio
async def test_public_general_criteria_download_while_registration_open(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)

    pdf = b"%PDF-1.4 public-general"
    upload = await client.post(
        f"/competitions/{competition_id}/general-criteria-document",
        headers=auth_headers,
        files={"file": ("public-general.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    now = datetime.utcnow()
    async with session_manager.session() as session:
        cycle = await session.get(Competition, competition_id)
        assert cycle is not None
        cycle.status = CompetitionStatus.ACTIVE
        existing = (
            await session.execute(
                select(RegistrationWindow).where(
                    RegistrationWindow.competition_id == competition_id
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                RegistrationWindow(
                    competition_id=cycle.id,
                    opens_at=now - timedelta(days=1),
                    closes_at=now + timedelta(days=30),
                )
            )
        else:
            existing.opens_at = now - timedelta(days=1)
            existing.closes_at = now + timedelta(days=30)
        await session.commit()

    public = await client.get(f"/competitions/{competition_id}/public")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["hasGeneralCriteriaDocument"] is True
    assert body["generalCriteriaFileName"] == "public-general.pdf"

    dl = await client.get(
        f"/competitions/{competition_id}/public/general-criteria-document",
    )
    assert dl.status_code == 200, dl.text
    assert dl.content.startswith(b"%PDF")
