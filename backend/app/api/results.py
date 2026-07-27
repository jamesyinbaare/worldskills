"""US-RES-01 results publication API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.rbac import Capability
from app.dependencies.auth import CurrentUserDep, client_meta, require_capability
from app.dependencies.database import DBSessionDep
from app.models import User
from app.schemas.results import (
    AdminResultItem,
    CertificateTemplateOut,
    CompetitorResultsOut,
    CorrectResultIn,
    CorrectResultOut,
    PrepareResultsIn,
    PrepareResultsOut,
    PublicResultsOut,
    ReleaseResultsIn,
    ReleaseResultsOut,
    ResultsConfigOut,
    ResultsConfigPut,
)
from app.services import results as results_service

router = APIRouter(tags=["results"])

PublishUserDep = Annotated[User, Depends(require_capability(Capability.PUBLISH_RESULTS))]


@router.get(
    "/competitions/{competition_id}/results-config",
    response_model=ResultsConfigOut,
)
async def get_results_config(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
) -> ResultsConfigOut:
    return await results_service.get_results_config(
        session, competition_id, actor=actor
    )


@router.put(
    "/competitions/{competition_id}/results-config",
    response_model=ResultsConfigOut,
)
async def put_results_config(
    competition_id: uuid.UUID,
    body: ResultsConfigPut,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
) -> ResultsConfigOut:
    ip, ua = client_meta(request)
    return await results_service.put_results_config(
        session,
        competition_id,
        body,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.get(
    "/competitions/{competition_id}/certificate-templates",
    response_model=list[CertificateTemplateOut],
)
async def list_certificate_templates(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
) -> list[CertificateTemplateOut]:
    return await results_service.list_certificate_templates(
        session, competition_id, actor=actor
    )


@router.get(
    "/competitions/{competition_id}/results",
    response_model=list[AdminResultItem],
)
async def list_admin_results(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
    skillId: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> list[AdminResultItem]:
    return await results_service.list_admin_results(
        session,
        competition_id,
        actor=actor,
        skill_id=skillId,
        q=q,
        state=state,
    )


@router.post("/competitions/{competition_id}/results:prepare", response_model=PrepareResultsOut)
async def prepare_results(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
    body: PrepareResultsIn = PrepareResultsIn(),
) -> PrepareResultsOut:
    ip, ua = client_meta(request)
    return await results_service.prepare_results(
        session,
        competition_id,
        actor=actor,
        skill_id=body.skillId,
        stage_id=body.stageId,
        ip=ip,
        user_agent=ua,
    )


@router.post("/competitions/{competition_id}/results:release", response_model=ReleaseResultsOut)
async def release_results(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
    body: ReleaseResultsIn = ReleaseResultsIn(),
) -> ReleaseResultsOut:
    ip, ua = client_meta(request)
    return await results_service.release_results(
        session,
        competition_id,
        actor=actor,
        manual=body.manual,
        skill_id=body.skillId,
        stage_id=body.stageId,
        ip=ip,
        user_agent=ua,
    )


@router.post("/results/{result_id}:correct", response_model=CorrectResultOut)
async def correct_result(
    result_id: uuid.UUID,
    body: CorrectResultIn,
    session: DBSessionDep,
    actor: PublishUserDep,
    request: Request,
) -> CorrectResultOut:
    ip, ua = client_meta(request)
    return await results_service.correct_result(
        session,
        result_id,
        changes=body.changes,
        reason=body.reason,
        actor=actor,
        ip=ip,
        user_agent=ua,
    )


@router.get("/public/competitions/{competition_id}/results", response_model=PublicResultsOut)
async def public_results(
    competition_id: uuid.UUID,
    session: DBSessionDep,
) -> PublicResultsOut:
    return await results_service.get_public_results(session, competition_id)


@router.get("/competitions/{competition_id}/results/me", response_model=CompetitorResultsOut)
async def my_results(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    actor: CurrentUserDep,
) -> CompetitorResultsOut:
    return await results_service.get_competitor_results(session, competition_id, actor=actor)
