"""Expert list/download of CLEAN submission artefacts for scoring."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import Artefact, ExpertSkillArea, User, UserRole
from app.services.storage import get_object_storage
from pytest_tests.test_us_asm_01 import _create_competition, _login, _seed_scoring_world


async def _add_clean_artefact(
    session_manager: DBManager,
    submission_id: uuid.UUID,
    *,
    deliverable_code: str = "main",
    filename: str = "deliverable.pdf",
    content: bytes = b"%PDF-1.4 expert-scoring-artefact",
) -> uuid.UUID:
    store = get_object_storage()
    stored, _scan = store.put_raw(
        content,
        prefix=f"submissions/{submission_id}/{deliverable_code}",
        filename=filename,
    )
    async with session_manager.session() as session:
        artefact = Artefact(
            submission_id=submission_id,
            deliverable_code=deliverable_code,
            filename=filename,
            content_type="application/pdf",
            size=stored.size,
            storage_key=stored.key,
            sha256=stored.sha256,
            scan_status="CLEAN",
            quarantined=False,
            complete=True,
            received_bytes=stored.size,
            total_size=stored.size,
        )
        session.add(artefact)
        await session.commit()
        await session.refresh(artefact)
        return artefact.id


async def _add_infected_artefact(
    session_manager: DBManager,
    submission_id: uuid.UUID,
) -> uuid.UUID:
    async with session_manager.session() as session:
        artefact = Artefact(
            submission_id=submission_id,
            deliverable_code="infected",
            filename="bad.zip",
            content_type="application/zip",
            size=10,
            storage_key=f"quarantine/submissions/{submission_id}/bad.zip",
            sha256="deadbeef",
            scan_status="INFECTED",
            quarantined=True,
            complete=True,
        )
        session.add(artefact)
        await session.commit()
        await session.refresh(artefact)
        return artefact.id


@pytest.mark.asyncio
async def test_assessment_lists_and_downloads_clean_artefact(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    sub_id = ctx["submission_id"]
    payload = b"%PDF-1.4 clean-bytes-for-download"
    artefact_id = await _add_clean_artefact(
        session_manager, sub_id, content=payload, filename="project.pdf"
    )
    headers = await _login(client, ctx["expert"])

    view = await client.get(f"/submissions/{sub_id}/assessment", headers=headers)
    assert view.status_code == 200, view.text
    body = view.json()
    assert len(body["artefacts"]) == 1
    art = body["artefacts"][0]
    assert art["artefactId"] == str(artefact_id)
    assert art["deliverableCode"] == "main"
    assert art["filename"] == "project.pdf"
    assert art["scanStatus"] == "CLEAN"
    assert art["size"] == len(payload)

    dl = await client.get(
        f"/submissions/{sub_id}/artefacts/{artefact_id}/download",
        headers=headers,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == payload
    cd = dl.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert "project.pdf" in cd
    assert "main" in cd
    assert body["anonCode"] in cd


@pytest.mark.asyncio
async def test_download_filenames_disambiguate_by_anon_and_deliverable(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=True)
    sub_id = ctx["submission_id"]
    same_name = "report.pdf"
    id_main = await _add_clean_artefact(
        session_manager,
        sub_id,
        deliverable_code="main",
        filename=same_name,
        content=b"%PDF-main",
    )
    id_extra = await _add_clean_artefact(
        session_manager,
        sub_id,
        deliverable_code="section 2",
        filename=same_name,
        content=b"%PDF-extra",
    )
    headers = await _login(client, ctx["expert"])

    view = await client.get(f"/submissions/{sub_id}/assessment", headers=headers)
    assert view.status_code == 200, view.text
    anon = view.json()["anonCode"]
    assert anon

    dl_main = await client.get(
        f"/submissions/{sub_id}/artefacts/{id_main}/download",
        headers=headers,
    )
    dl_extra = await client.get(
        f"/submissions/{sub_id}/artefacts/{id_extra}/download",
        headers=headers,
    )
    assert dl_main.status_code == 200, dl_main.text
    assert dl_extra.status_code == 200, dl_extra.text

    cd_main = dl_main.headers.get("content-disposition", "")
    cd_extra = dl_extra.headers.get("content-disposition", "")
    assert anon in cd_main and anon in cd_extra
    assert "main" in cd_main
    assert "section 2" in cd_extra or "section-2" in cd_extra
    assert "report.pdf" in cd_main and "report.pdf" in cd_extra
    assert cd_main != cd_extra


@pytest.mark.asyncio
async def test_assessment_excludes_infected_artefact_from_list_and_download(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    sub_id = ctx["submission_id"]
    clean_id = await _add_clean_artefact(session_manager, sub_id)
    infected_id = await _add_infected_artefact(session_manager, sub_id)
    headers = await _login(client, ctx["expert"])

    view = await client.get(f"/submissions/{sub_id}/assessment", headers=headers)
    assert view.status_code == 200, view.text
    listed_ids = {a["artefactId"] for a in view.json()["artefacts"]}
    assert str(clean_id) in listed_ids
    assert str(infected_id) not in listed_ids

    dl = await client.get(
        f"/submissions/{sub_id}/artefacts/{infected_id}/download",
        headers=headers,
    )
    assert dl.status_code == 404
    assert dl.json()["error"]["code"] == "ARTEFACT_NOT_FOUND"


@pytest.mark.asyncio
async def test_download_artefact_coi_blocked(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(
        session_manager, competition_id, blind=False, expert_same_institution=True
    )
    sub_id = ctx["submission_id"]
    artefact_id = await _add_clean_artefact(session_manager, sub_id)
    headers = await _login(client, ctx["expert"])

    dl = await client.get(
        f"/submissions/{sub_id}/artefacts/{artefact_id}/download",
        headers=headers,
    )
    assert dl.status_code == 409
    assert dl.json()["error"]["code"] == "CONFLICT_OF_INTEREST"


@pytest.mark.asyncio
async def test_download_artefact_unassigned_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    competition_id = await _create_competition(client, auth_headers)
    ctx = await _seed_scoring_world(session_manager, competition_id, blind=False)
    sub_id = ctx["submission_id"]
    artefact_id = await _add_clean_artefact(session_manager, sub_id)

    async with session_manager.session() as session:
        # Catalog skill from assigned expert's ExpertSkillArea — reuse via first area
        from sqlalchemy import select

        area = (
            await session.execute(
                select(ExpertSkillArea).where(ExpertSkillArea.expert_id == ctx["expert"].id)
            )
        ).scalar_one()
        outsider = User(
            email=f"outsider-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Unassigned Expert",
            hashed_password=get_password_hash("expert-pass-123"),
            role=UserRole.EXPERT,
            is_active=True,
            institution_id=ctx["inst_b"],
        )
        session.add(outsider)
        await session.flush()
        session.add(
            ExpertSkillArea(expert_id=outsider.id, catalog_skill_id=area.catalog_skill_id)
        )
        await session.commit()
        await session.refresh(outsider)

    headers = await _login(client, outsider)
    dl = await client.get(
        f"/submissions/{sub_id}/artefacts/{artefact_id}/download",
        headers=headers,
    )
    assert dl.status_code == 403
    assert dl.json()["error"]["code"] == "NOT_ASSIGNED"
