"""Global family + skill catalog HTTP API (US-SKL-02)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import CatalogSkill, Family
from app.schemas.catalog import (
    CatalogSkillCreate,
    CatalogSkillOut,
    CatalogSkillPatch,
    FamilyCreate,
    FamilyOut,
    FamilyPatch,
)
from app.schemas.users import UserOut
from app.services import catalog as catalog_service
from app.services import expert_skill_areas as expert_skill_areas_service

router = APIRouter(tags=["catalog"])


def _family_out(family: Family) -> FamilyOut:
    return FamilyOut(
        familyId=family.id,
        name=family.name,
        description=family.description,
        active=family.active,
    )


def _catalog_skill_out(skill: CatalogSkill) -> CatalogSkillOut:
    family_name = None
    family = skill.__dict__.get("family")
    if family is not None:
        family_name = family.name
    return CatalogSkillOut(
        skillId=skill.id,
        name=skill.name,
        number=skill.number,
        familyId=skill.family_id,
        familyName=family_name,
        description=skill.description,
        active=skill.active,
    )


@router.get("/families", response_model=list[FamilyOut])
async def list_families(session: DBSessionDep, admin: AdminUserDep) -> list[FamilyOut]:
    _ = admin
    families = await catalog_service.list_families(session)
    return [_family_out(f) for f in families]


@router.post("/families", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
async def create_family(
    payload: FamilyCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> FamilyOut:
    ip, ua = client_meta(request)
    family = await catalog_service.create_family(
        session, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _family_out(family)


@router.patch("/families/{family_id}", response_model=FamilyOut)
async def patch_family(
    family_id: uuid.UUID,
    payload: FamilyPatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> FamilyOut:
    ip, ua = client_meta(request)
    family = await catalog_service.patch_family(
        session, family_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _family_out(family)


@router.get("/skills", response_model=list[CatalogSkillOut])
async def list_catalog_skills(
    session: DBSessionDep,
    admin: AdminUserDep,
    active: bool | None = Query(default=None),
) -> list[CatalogSkillOut]:
    _ = admin
    skills = await catalog_service.list_catalog_skills(
        session, active_only=active is True
    )
    return [_catalog_skill_out(s) for s in skills]


@router.post("/skills", response_model=CatalogSkillOut, status_code=status.HTTP_201_CREATED)
async def create_catalog_skill(
    payload: CatalogSkillCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CatalogSkillOut:
    ip, ua = client_meta(request)
    skill = await catalog_service.create_catalog_skill(
        session, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _catalog_skill_out(skill)


@router.patch("/skills/{skill_id}", response_model=CatalogSkillOut)
async def patch_catalog_skill(
    skill_id: uuid.UUID,
    payload: CatalogSkillPatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CatalogSkillOut:
    ip, ua = client_meta(request)
    skill = await catalog_service.patch_catalog_skill(
        session, skill_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _catalog_skill_out(skill)


@router.get("/skills/{skill_id}/experts", response_model=list[UserOut])
async def list_catalog_skill_experts(
    skill_id: uuid.UUID,
    session: DBSessionDep,
    _admin: AdminUserDep,
) -> list[dict]:
    catalog = await session.get(CatalogSkill, skill_id)
    if catalog is None:
        from app.core.errors import AppError

        raise AppError("SKILL_NOT_FOUND", "Catalog skill not found", status_code=404)
    experts = await expert_skill_areas_service.list_experts_for_catalog_skill(
        session, skill_id
    )
    return [
        {
            "userId": str(u.id),
            "email": u.email or "",
            "fullName": u.full_name,
            "role": u.role.value,
            "institutionId": str(u.institution_id) if u.institution_id else None,
            "isActive": u.is_active,
            "mustChangePassword": u.must_change_password,
            "phoneNumber": u.phone_number,
        }
        for u in experts
    ]
