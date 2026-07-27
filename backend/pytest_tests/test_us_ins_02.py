"""US-INS-02 — Institution records & Excel import."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import Institution
from app.services.storage import EICAR_SIGNATURE
from pytest_tests.conftest import region_id_by_name


async def _create(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    code: str,
    name: str,
    region_id: uuid.UUID,
) -> dict:
    resp = await client.post(
        "/institutions",
        json={"code": code, "name": name, "regionId": str(region_id), "active": True},
        headers=headers,
    )
    return resp


@pytest.mark.asyncio
async def test_US_INS_02_AC1_create_institution(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    region_id = await region_id_by_name(session_manager)
    code = f"SCH-{uuid.uuid4().hex[:6]}"
    resp = await _create(
        client, auth_headers, code=code, name=f"School {code}", region_id=region_id
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == code
    assert body["regionId"] == str(region_id)
    assert body["active"] is True


@pytest.mark.asyncio
async def test_US_INS_02_AC2_reject_duplicate_code(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    region_id = await region_id_by_name(session_manager)
    code = f"DUP-{uuid.uuid4().hex[:6]}"
    first = await _create(client, auth_headers, code=code, name=f"A {code}", region_id=region_id)
    assert first.status_code == 201, first.text
    second = await _create(client, auth_headers, code=code, name=f"B {code}", region_id=region_id)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "DUPLICATE"


@pytest.mark.asyncio
async def test_US_INS_02_duplicate_names_allowed(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    """School names are not unique — only codes are."""
    region_id = await region_id_by_name(session_manager)
    shared_name = f"Shared High School {uuid.uuid4().hex[:6]}"
    first = await _create(
        client, auth_headers, code=f"N1-{uuid.uuid4().hex[:6]}", name=shared_name, region_id=region_id
    )
    second = await _create(
        client, auth_headers, code=f"N2-{uuid.uuid4().hex[:6]}", name=shared_name, region_id=region_id
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["name"] == second.json()["name"] == shared_name


@pytest.mark.asyncio
async def test_US_INS_02_AC3_patch_institution(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    region_id = await region_id_by_name(session_manager)
    other = await region_id_by_name(session_manager, "Ashanti")
    code = f"PAT-{uuid.uuid4().hex[:6]}"
    created = await _create(client, auth_headers, code=code, name=f"Old {code}", region_id=region_id)
    assert created.status_code == 201, created.text
    iid = created.json()["institutionId"]
    resp = await client.patch(
        f"/institutions/{iid}",
        json={"name": f"New {code}", "regionId": str(other), "active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == f"New {code}"
    assert resp.json()["regionId"] == str(other)
    assert resp.json()["active"] is False


@pytest.mark.asyncio
async def test_US_INS_02_AC4_excel_import_upsert(
    client: AsyncClient, auth_headers: dict[str, str], session_manager: DBManager
) -> None:
    region_id = await region_id_by_name(session_manager)
    code = f"IMP-{uuid.uuid4().hex[:6]}"
    await _create(client, auth_headers, code=code, name=f"Before {code}", region_id=region_id)

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["school code", "name", "region"])
    ws.append([code, f"After {code}", "Greater Accra"])
    ws.append([f"NEW-{code}", f"Brand New {code}", "Ashanti"])
    buf = io.BytesIO()
    wb.save(buf)

    resp = await client.post(
        "/institutions:import",
        files={
            "file": (
                "schools.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_US_INS_02_AC5_import_row_errors(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["school code", "name", "region"])
    ws.append(["", "No Code", "Greater Accra"])
    ws.append([f"OK-{uuid.uuid4().hex[:6]}", "Valid School", "Not A Real Region"])
    buf = io.BytesIO()
    wb.save(buf)

    resp = await client.post(
        "/institutions:import",
        files={"file": ("bad.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) >= 2


@pytest.mark.asyncio
async def test_US_INS_02_AC6_import_malware_or_bad_type(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bad = await client.post(
        "/institutions:import",
        files={"file": ("schools.csv", b"code,name,region\n", "text/csv")},
        headers=auth_headers,
    )
    assert bad.status_code == 400, bad.text
    assert bad.json()["error"]["code"] == "FILE_TYPE"

    infected = await client.post(
        "/institutions:import",
        files={
            "file": (
                "evil.xlsx",
                EICAR_SIGNATURE + b"not-really-xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers,
    )
    assert infected.status_code == 400, infected.text
    assert infected.json()["error"]["code"] == "FILE_INFECTED"


@pytest.mark.asyncio
async def test_US_INS_02_AC7_template_download(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/institutions/import-template", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers.get("content-type", "")
    assert resp.content[:2] == b"PK"  # zip/xlsx
