from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import AgeRule, MarkingScheme, Pathway
from app.schemas.competition_config import (
    AgeRuleCreate,
    AgeRuleOut,
    MarkingSchemeCreate,
    MarkingSchemeOut,
    PathwayConfigCreate,
    PathwayConfigOut,
)
from app.services import competition_config as config_service

router = APIRouter(prefix="/competitions", tags=["competition-config"])


def _age_rule_out(rule: AgeRule) -> AgeRuleOut:
    return AgeRuleOut(
        ageRuleId=rule.id,
        competitionId=rule.competition_id,
        name=rule.name,
        maxAge=rule.max_age,
        referenceDate=rule.reference_date,
        openCategoryEnabled=rule.open_category_enabled,
    )


def _pathway_out(path: Pathway) -> PathwayConfigOut:
    return PathwayConfigOut(
        pathwayId=path.id,
        competitionId=path.competition_id,
        name=path.name,
    )


def _scheme_out(scheme: MarkingScheme) -> MarkingSchemeOut:
    from app.services.exercises import rubric_meta

    has, blind, _ = rubric_meta(scheme)
    rubric = scheme.rubric if isinstance(scheme.rubric, dict) else {}
    return MarkingSchemeOut(
        schemeId=scheme.id,
        competitionId=scheme.competition_id,
        name=scheme.name,
        documentFileName=scheme.document_file_name,
        documentContentType=scheme.document_content_type,
        documentScanStatus=scheme.document_scan_status,
        blindMode=blind,
        criteria=list(rubric.get("criteria") or []) if has or rubric else None,
        penalties=list(rubric.get("penalties") or []) if has or rubric else None,
        hasRubricCriteria=has,
    )


@router.get("/{competition_id}/age-rules", response_model=list[AgeRuleOut])
async def list_age_rules(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[AgeRuleOut]:
    _ = admin
    rules = await config_service.list_age_rules(session, competition_id)
    return [_age_rule_out(r) for r in rules]


@router.post(
    "/{competition_id}/age-rules",
    response_model=AgeRuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_age_rule(
    competition_id: uuid.UUID,
    payload: AgeRuleCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> AgeRuleOut:
    ip, ua = client_meta(request)
    rule = await config_service.create_age_rule(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _age_rule_out(rule)


@router.get("/{competition_id}/pathways", response_model=list[PathwayConfigOut])
async def list_pathways(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[PathwayConfigOut]:
    _ = admin
    paths = await config_service.list_pathways(session, competition_id)
    return [_pathway_out(p) for p in paths]


@router.post(
    "/{competition_id}/pathways",
    response_model=PathwayConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pathway(
    competition_id: uuid.UUID,
    payload: PathwayConfigCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> PathwayConfigOut:
    ip, ua = client_meta(request)
    path = await config_service.create_pathway(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _pathway_out(path)


@router.get("/{competition_id}/marking-schemes", response_model=list[MarkingSchemeOut])
async def list_marking_schemes(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[MarkingSchemeOut]:
    _ = admin
    schemes = await config_service.list_marking_schemes(session, competition_id)
    return [_scheme_out(s) for s in schemes]


@router.post(
    "/{competition_id}/marking-schemes",
    response_model=MarkingSchemeOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_marking_scheme(
    competition_id: uuid.UUID,
    payload: MarkingSchemeCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> MarkingSchemeOut:
    ip, ua = client_meta(request)
    scheme = await config_service.create_marking_scheme(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _scheme_out(scheme)


@router.post(
    "/{competition_id}/marking-schemes/{scheme_id}/document",
    response_model=MarkingSchemeOut,
)
async def upload_scheme_document(
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
    file: UploadFile = File(...),
) -> MarkingSchemeOut:
    ip, ua = client_meta(request)
    data = await file.read()
    scheme = await config_service.upload_scheme_document(
        session,
        competition_id,
        scheme_id,
        actor=admin,
        data=data,
        filename=file.filename or "scheme.pdf",
        content_type=file.content_type,
        ip=ip,
        user_agent=ua,
    )
    return _scheme_out(scheme)


@router.delete(
    "/{competition_id}/marking-schemes/{scheme_id}/document",
    response_model=MarkingSchemeOut,
)
async def delete_scheme_document(
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> MarkingSchemeOut:
    ip, ua = client_meta(request)
    scheme = await config_service.delete_scheme_document(
        session, competition_id, scheme_id, actor=admin, ip=ip, user_agent=ua
    )
    return _scheme_out(scheme)


@router.get("/{competition_id}/marking-schemes/{scheme_id}/document")
async def download_scheme_document(
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> Response:
    data, filename, content_type = await config_service.download_scheme_document(
        session, competition_id, scheme_id, actor=user
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
