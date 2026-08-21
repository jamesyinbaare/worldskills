"""Sponsor catalog CRUD + logo upload."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager

# Minimal 1x1 PNG
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.mark.asyncio
async def test_create_sponsor_name_required(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post("/sponsors", json={}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_sponsor_optional_fields_ok(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/sponsors",
        json={"name": "Acme Motors"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Acme Motors"
    assert body["website"] is None
    assert body["description"] is None
    assert body["hasLogo"] is False
    assert body["active"] is True


@pytest.mark.asyncio
async def test_create_sponsor_website_validation_and_normalize(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    bad = await client.post(
        "/sponsors",
        json={"name": "Bad URL Co", "website": "not a url"},
        headers=auth_headers,
    )
    assert bad.status_code == 422

    ok = await client.post(
        "/sponsors",
        json={
            "name": "Good URL Co",
            "website": "example.com",
            "description": "  Partner  ",
        },
        headers=auth_headers,
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["website"] == "https://example.com"
    assert body["description"] == "Partner"


@pytest.mark.asyncio
async def test_sponsor_duplicate_name(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    first = await client.post(
        "/sponsors",
        json={"name": "Dup Sponsor"},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/sponsors",
        json={"name": "dup sponsor"},
        headers=auth_headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "SPONSOR_DUPLICATE"


@pytest.mark.asyncio
async def test_list_patch_active_and_logo_flow(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/sponsors",
        json={"name": "Logo Corp", "website": "https://logo.example"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    sponsor_id = created.json()["sponsorId"]

    listed = await client.get("/sponsors", headers=auth_headers)
    assert listed.status_code == 200
    assert any(s["sponsorId"] == sponsor_id for s in listed.json())

    patched = await client.patch(
        f"/sponsors/{sponsor_id}",
        json={"active": False, "description": "Inactive partner"},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["active"] is False
    assert patched.json()["description"] == "Inactive partner"

    bad_logo = await client.post(
        f"/sponsors/{sponsor_id}/logo",
        headers=auth_headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_logo.status_code == 400, bad_logo.text
    assert bad_logo.json()["error"]["code"] == "FILE_TYPE"

    good_logo = await client.post(
        f"/sponsors/{sponsor_id}/logo",
        headers=auth_headers,
        files={"file": ("mark.png", _PNG_1X1, "image/png")},
    )
    assert good_logo.status_code == 200, good_logo.text
    assert good_logo.json()["hasLogo"] is True
    assert good_logo.json()["logoFileName"] == "mark.png"

    download = await client.get(
        f"/sponsors/{sponsor_id}/logo",
        headers=auth_headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/png")
    assert download.content[:8] == b"\x89PNG\r\n\x1a\n"

    cleared = await client.delete(
        f"/sponsors/{sponsor_id}/logo",
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["hasLogo"] is False

    missing = await client.get(
        f"/sponsors/{sponsor_id}/logo",
        headers=auth_headers,
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_public_sponsors_active_only_and_logo(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    active = await client.post(
        "/sponsors",
        json={"name": "Public Active Co"},
        headers=auth_headers,
    )
    assert active.status_code == 201, active.text
    active_id = active.json()["sponsorId"]

    inactive = await client.post(
        "/sponsors",
        json={"name": "Public Inactive Co"},
        headers=auth_headers,
    )
    assert inactive.status_code == 201, inactive.text
    inactive_id = inactive.json()["sponsorId"]
    await client.patch(
        f"/sponsors/{inactive_id}",
        json={"active": False},
        headers=auth_headers,
    )

    await client.post(
        f"/sponsors/{active_id}/logo",
        headers=auth_headers,
        files={"file": ("mark.png", _PNG_1X1, "image/png")},
    )
    await client.post(
        f"/sponsors/{inactive_id}/logo",
        headers=auth_headers,
        files={"file": ("mark.png", _PNG_1X1, "image/png")},
    )

    public_list = await client.get("/public/sponsors")
    assert public_list.status_code == 200, public_list.text
    ids = {s["sponsorId"] for s in public_list.json()}
    assert active_id in ids
    assert inactive_id not in ids

    public_logo = await client.get(f"/public/sponsors/{active_id}/logo")
    assert public_logo.status_code == 200
    assert public_logo.content[:8] == b"\x89PNG\r\n\x1a\n"

    inactive_logo = await client.get(f"/public/sponsors/{inactive_id}/logo")
    assert inactive_logo.status_code == 404

    missing_logo = await client.get(
        f"/public/sponsors/00000000-0000-0000-0000-000000000001/logo"
    )
    assert missing_logo.status_code == 404


async def _create_catalog_skill(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    name: str,
    number: str = "1",
) -> str:
    fam = await client.post(
        "/families",
        json={"name": f"Fam {name}"},
        headers=auth_headers,
    )
    assert fam.status_code == 201, fam.text
    skill = await client.post(
        "/skills",
        json={
            "name": name,
            "number": number,
            "familyId": fam.json()["familyId"],
        },
        headers=auth_headers,
    )
    assert skill.status_code == 201, skill.text
    return skill.json()["skillId"]


@pytest.mark.asyncio
async def test_sponsor_catalog_skill_links_create_patch_and_public(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    skill_a = await _create_catalog_skill(
        client, auth_headers, name="Welding Link", number="10"
    )
    skill_b = await _create_catalog_skill(
        client, auth_headers, name="Plumbing Link", number="11"
    )

    created = await client.post(
        "/sponsors",
        json={
            "name": "Skill Linked Co",
            "catalogSkillIds": [skill_a, skill_b],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["skillAreas"]
    names = {a["name"] for a in body["skillAreas"]}
    assert names == {"Welding Link", "Plumbing Link"}
    ids = {a["catalogSkillId"] for a in body["skillAreas"]}
    assert ids == {skill_a, skill_b}

    public = await client.get("/public/sponsors")
    assert public.status_code == 200
    match = next(s for s in public.json() if s["sponsorId"] == body["sponsorId"])
    assert {a["catalogSkillId"] for a in match["skillAreas"]} == {skill_a, skill_b}

    cleared = await client.patch(
        f"/sponsors/{body['sponsorId']}",
        json={"catalogSkillIds": []},
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["skillAreas"] == []

    restored = await client.patch(
        f"/sponsors/{body['sponsorId']}",
        json={"catalogSkillIds": [skill_a]},
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    assert len(restored.json()["skillAreas"]) == 1
    assert restored.json()["skillAreas"][0]["catalogSkillId"] == skill_a


@pytest.mark.asyncio
async def test_sponsor_catalog_skill_invalid_or_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    skill_id = await _create_catalog_skill(
        client, auth_headers, name="Inactive Link Skill"
    )
    deactivated = await client.patch(
        f"/skills/{skill_id}",
        json={"active": False},
        headers=auth_headers,
    )
    assert deactivated.status_code == 200, deactivated.text

    bad_unknown = await client.post(
        "/sponsors",
        json={
            "name": "Bad Skill Sponsor",
            "catalogSkillIds": ["00000000-0000-0000-0000-000000000099"],
        },
        headers=auth_headers,
    )
    assert bad_unknown.status_code == 422, bad_unknown.text

    bad_inactive = await client.post(
        "/sponsors",
        json={
            "name": "Inactive Skill Sponsor",
            "catalogSkillIds": [skill_id],
        },
        headers=auth_headers,
    )
    assert bad_inactive.status_code == 422, bad_inactive.text


@pytest.mark.asyncio
async def test_public_competition_skill_includes_linked_sponsors(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
) -> None:
    from datetime import datetime, timedelta

    from app.models import (
        AgeRule,
        Competition,
        CompetitionStatus,
        MarkingScheme,
        Pathway,
        RegistrationFormDefinition,
        RegistrationWindow,
        Skill,
    )
    from pytest_tests.conftest import competition_payload

    catalog_id = await _create_catalog_skill(
        client, auth_headers, name="Public Sponsor Skill", number="42"
    )
    sponsor = await client.post(
        "/sponsors",
        json={
            "name": "Skill Page Sponsor",
            "catalogSkillIds": [catalog_id],
        },
        headers=auth_headers,
    )
    assert sponsor.status_code == 201, sponsor.text
    sponsor_id = sponsor.json()["sponsorId"]

    general = await client.post(
        "/sponsors",
        json={"name": "General Only Sponsor"},
        headers=auth_headers,
    )
    assert general.status_code == 201, general.text
    general_id = general.json()["sponsorId"]

    cycle = await client.post(
        "/competitions",
        json=competition_payload(),
        headers=auth_headers,
    )
    assert cycle.status_code == 201, cycle.text
    competition_id = uuid.UUID(cycle.json()["competitionId"])

    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        session.add_all([age, path, scheme])
        await session.flush()
        session.add(
            Skill(
                competition_id=competition_id,
                catalog_skill_id=uuid.UUID(catalog_id),
                name="Public Sponsor Skill",
                number="42",
                age_rule_id=age.id,
                pathway_id=path.id,
                scheme_id=scheme.id,
                active=True,
            )
        )
        session.add(
            RegistrationFormDefinition(
                competition_id=competition_id,
                fields=[
                    {"name": "givenNames", "type": "string", "required": True},
                    {"name": "skillIds", "type": "array", "required": True},
                    {"name": "declarationAccepted", "type": "boolean", "required": True},
                ],
                max_skills=1,
            )
        )
        now = datetime.utcnow()
        session.add(
            RegistrationWindow(
                competition_id=competition_id,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
            )
        )
        competition = await session.get(Competition, competition_id)
        assert competition is not None
        competition.status = CompetitionStatus.ACTIVE
        await session.commit()

    public = await client.get(f"/competitions/{competition_id}/public")
    assert public.status_code == 200, public.text
    skills = public.json()["skills"]
    assert len(skills) == 1
    skill_sponsors = skills[0].get("sponsors") or []
    skill_sponsor_ids = {s["sponsorId"] for s in skill_sponsors}
    assert sponsor_id in skill_sponsor_ids
    assert general_id not in skill_sponsor_ids
