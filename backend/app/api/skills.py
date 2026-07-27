from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import CatalogSkill, Skill, UserRole
from app.schemas.skills import (
    AvailableSkillOut,
    CycleSkillPatch,
    SkillCreate,
    SkillOut,
)
from app.services import skills as skill_service
from app.services.skills import age_rule_embed as _age_rule_embed

router = APIRouter(prefix="/competitions", tags=["skills"])

_REG_DISCOVERY_ROLES = {
    UserRole.COMPETITOR,
    UserRole.INSTITUTION,
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
}


def _skill_out(skill: Skill, *, has_pathway: bool = False) -> SkillOut:
    family_name = None
    catalog = skill.__dict__.get("catalog_skill")
    if catalog is not None:
        family = catalog.__dict__.get("family")
        if family is not None:
            family_name = family.name
    return SkillOut(
        skillId=skill.id,
        cycleSkillId=skill.id,
        competitionId=skill.competition_id,
        catalogSkillId=skill.catalog_skill_id,
        name=skill.name,
        number=skill.number,
        familyId=skill.family_id,
        familyName=family_name,
        ageRuleId=skill.age_rule_id,
        ageRule=_age_rule_embed(skill),
        pathwayId=skill.pathway_id,
        schemeId=skill.scheme_id,
        capacity=skill.capacity,
        schoolQuota=skill.school_quota,
        active=skill.active,
        hasPathway=has_pathway,
        hasCriteriaDocument=bool(skill.criteria_object_key and skill.criteria_file_name),
        criteriaFileName=skill.criteria_file_name,
        criteriaScanStatus=skill.criteria_scan_status,
    )


async def _load_skill(session: DBSessionDep, skill_id: uuid.UUID) -> Skill | None:
    result = await session.execute(
        select(Skill)
        .options(selectinload(Skill.catalog_skill).selectinload(CatalogSkill.family))
        .where(Skill.id == skill_id)
    )
    return result.scalar_one_or_none()


@router.get("/{competition_id}/skills:available", response_model=list[AvailableSkillOut])
async def list_available_skills(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> list[AvailableSkillOut]:
    from app.core.errors import AppError

    if user.role not in _REG_DISCOVERY_ROLES:
        raise AppError(
            "FORBIDDEN",
            "Insufficient role for skill discovery",
            status_code=403,
        )
    items = await skill_service.list_available_skills(session, competition_id)
    return [AvailableSkillOut(**item) for item in items]


@router.get("/{competition_id}/skills", response_model=list[SkillOut])
async def list_skills(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[SkillOut]:
    _ = admin
    skills = await skill_service.list_skills(session, competition_id)
    out: list[SkillOut] = []
    for s in skills:
        has_pw = await skill_service.skill_has_pathway(session, s.id)
        out.append(_skill_out(s, has_pathway=has_pw))
    return out


@router.post("/{competition_id}/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_or_associate_skill(
    competition_id: uuid.UUID,
    payload: SkillCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SkillOut:
    """Accept catalog association (`skillId` + `ageRule`) or legacy create (`name` + links)."""
    ip, ua = client_meta(request)
    skill = await skill_service.create_skill(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    loaded = await _load_skill(session, skill.id)
    return _skill_out(loaded or skill)


@router.patch("/{competition_id}/skills/{cycle_skill_id}", response_model=SkillOut)
async def patch_cycle_skill(
    competition_id: uuid.UUID,
    cycle_skill_id: uuid.UUID,
    payload: CycleSkillPatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SkillOut:
    ip, ua = client_meta(request)
    skill = await skill_service.patch_cycle_skill(
        session, competition_id, cycle_skill_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    loaded = await _load_skill(session, skill.id)
    has_pw = await skill_service.skill_has_pathway(session, skill.id)
    return _skill_out(loaded or skill, has_pathway=has_pw)


@router.post(
    "/{competition_id}/skills/{skill_id}/criteria-document",
    response_model=SkillOut,
)
async def upload_skill_criteria_document(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
    file: UploadFile = File(...),
) -> SkillOut:
    ip, ua = client_meta(request)
    data = await file.read()
    skill = await skill_service.upload_skill_criteria_document(
        session,
        competition_id,
        skill_id,
        actor=admin,
        data=data,
        filename=file.filename or "criteria.pdf",
        content_type=file.content_type,
        ip=ip,
        user_agent=ua,
    )
    loaded = await _load_skill(session, skill.id)
    has_pw = await skill_service.skill_has_pathway(session, skill.id)
    return _skill_out(loaded or skill, has_pathway=has_pw)


@router.delete(
    "/{competition_id}/skills/{skill_id}/criteria-document",
    response_model=SkillOut,
)
async def delete_skill_criteria_document(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SkillOut:
    ip, ua = client_meta(request)
    skill = await skill_service.delete_skill_criteria_document(
        session, competition_id, skill_id, actor=admin, ip=ip, user_agent=ua
    )
    loaded = await _load_skill(session, skill.id)
    has_pw = await skill_service.skill_has_pathway(session, skill.id)
    return _skill_out(loaded or skill, has_pathway=has_pw)


@router.get("/{competition_id}/skills/{skill_id}/criteria-document")
async def download_skill_criteria_document(
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> Response:
    data, filename, content_type = await skill_service.download_skill_criteria_document(
        session, competition_id, skill_id, actor=user
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
