"""Optional exercise deliverables must be uploadable but not required at finalise."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    AgeRule,
    CompetitionStatus,
    Exercise,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    User,
    Zone,
)
from app.services.exercises import deliverables_to_submission_rules
from pytest_tests.conftest import competition_payload
from pytest_tests.test_us_sub_02 import (
    _competitor_headers,
    _open_submission,
    _upload,
)


def test_deliverables_to_submission_rules_includes_optional() -> None:
    ex = Exercise(
        stage_id=uuid.uuid4(),
        competition_id=uuid.uuid4(),
        title="T",
        deliverables=[
            {
                "code": "main",
                "label": "Main",
                "required": True,
                "allowedTypes": ["pdf"],
                "maxSizeBytes": 1_048_576,
            },
            {
                "code": "section 2",
                "label": "Section 2",
                "required": False,
                "allowedTypes": ["pdf", "zip"],
                "maxSizeBytes": 2_097_152,
            },
        ],
        status="PUBLISHED",
        late_policy="block",
    )
    rules = deliverables_to_submission_rules(ex)
    assert [d["code"] for d in rules["allowedDeliverables"]] == ["main", "section 2"]
    assert [d["code"] for d in rules["requiredDeliverables"]] == ["main"]
    optional = next(d for d in rules["allowedDeliverables"] if d["code"] == "section 2")
    assert optional["formats"] == ["pdf", "zip"]
    assert optional["maxMb"] == 2


async def _seed_with_optional_exercise(
    session_manager: DBManager,
    competition_id: uuid.UUID,
    competitor_user: User,
) -> uuid.UUID:
    now = datetime.utcnow()
    async with session_manager.session() as session:
        age = AgeRule(competition_id=competition_id, name="U25", max_age=25)
        path = Pathway(competition_id=competition_id, name="National")
        scheme = MarkingScheme(competition_id=competition_id, name="CIS")
        zone = Zone(competition_id=competition_id, name="Greater Accra", active=True)
        session.add_all([age, path, scheme, zone])
        await session.flush()
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
        stage = Stage(
            competition_id=competition_id,
            skill_id=skill.id,
            name="Regional Project",
            order=1,
            quota=20,
            opens_at=now - timedelta(hours=1),
            closes_at=now + timedelta(hours=24),
        )
        session.add(stage)
        await session.flush()
        ex = Exercise(
            stage_id=stage.id,
            competition_id=competition_id,
            title="Challenge",
            brief="Upload main; section 2 optional",
            deliverables=[
                {
                    "code": "main",
                    "label": "Main package",
                    "required": True,
                    "allowedTypes": ["pdf", "zip"],
                    "maxSizeBytes": 20_000_000,
                },
                {
                    "code": "section 2",
                    "label": "Section 2",
                    "required": False,
                    "allowedTypes": ["pdf", "zip"],
                    "maxSizeBytes": 20_000_000,
                },
            ],
            status="PUBLISHED",
            scheme_id=scheme.id,
            late_policy="block",
        )
        session.add(ex)
        # Keep stage.submission_rules in sync as upsert/publish would
        stage.submission_rules = deliverables_to_submission_rules(ex)

        from app.models import Competitor, Competition

        competitor = Competitor(
            competition_id=competition_id,
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
        cycle = await session.get(Competition, competition_id)
        if cycle is not None:
            cycle.status = CompetitionStatus.ACTIVE
        await session.commit()
        return stage.id


@pytest.mark.asyncio
async def test_optional_deliverable_upload_and_finalise(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    assert create.status_code == 201, create.text
    competition_id = uuid.UUID(create.json()["competitionId"])
    stage_id = await _seed_with_optional_exercise(
        session_manager, competition_id, competitor_user
    )
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, competition_id, stage_id)

    # Optional code must be accepted for upload
    optional_up = await _upload(
        client,
        headers,
        sub_id,
        code="section 2",
        filename="extra.pdf",
        data=b"%PDF-optional",
    )
    assert optional_up.status_code == 202, optional_up.text
    assert optional_up.json()["scan"] == "CLEAN"

    # Finalise without required deliverable still fails
    missing = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert missing.status_code == 409, missing.text
    assert missing.json()["error"]["code"] == "DELIVERABLE_MISSING"

    # Required only is enough to finalise (optional already present is fine)
    required_up = await _upload(
        client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF-main"
    )
    assert required_up.status_code == 202, required_up.text

    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["state"] in {"ACCEPTED", "LATE"}


@pytest.mark.asyncio
async def test_finalise_without_optional_succeeds(
    client: AsyncClient,
    auth_headers: dict[str, str],
    session_manager: DBManager,
    competitor_user: User,
) -> None:
    create = await client.post("/competitions", json=competition_payload(), headers=auth_headers)
    assert create.status_code == 201, create.text
    competition_id = uuid.UUID(create.json()["competitionId"])
    stage_id = await _seed_with_optional_exercise(
        session_manager, competition_id, competitor_user
    )
    headers = await _competitor_headers(client, competitor_user)
    sub_id = await _open_submission(client, headers, competition_id, stage_id)

    await _upload(client, headers, sub_id, code="main", filename="work.pdf", data=b"%PDF-main")
    fin = await client.post(f"/submissions/{sub_id}:finalise", headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["state"] in {"ACCEPTED", "LATE"}
