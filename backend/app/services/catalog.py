"""Global skill family + catalog skill services (US-SKL-02)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import CatalogSkill, Family, Skill, User
from app.schemas.catalog import (
    CatalogSkillCreate,
    CatalogSkillPatch,
    FamilyCreate,
    FamilyPatch,
)
from app.services.audit import write_audit_event


def family_to_dict(family: Family) -> dict[str, Any]:
    return {
        "familyId": str(family.id),
        "name": family.name,
        "description": family.description,
        "active": family.active,
    }


def catalog_skill_to_dict(skill: CatalogSkill, *, family_name: str | None = None) -> dict[str, Any]:
    return {
        "skillId": str(skill.id),
        "name": skill.name,
        "number": skill.number,
        "familyId": str(skill.family_id),
        "familyName": family_name,
        "description": skill.description,
        "active": skill.active,
    }


async def list_families(session: AsyncSession) -> list[Family]:
    result = await session.execute(select(Family).order_by(Family.name))
    return list(result.scalars().all())


async def create_family(
    session: AsyncSession,
    payload: FamilyCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Family:
    dup = await session.execute(select(Family).where(func.lower(Family.name) == payload.name.lower()))
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "FAMILY_DUPLICATE",
            "A family with this name already exists",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    family = Family(name=payload.name, description=payload.description, active=True)
    session.add(family)
    await session.flush()

    await write_audit_event(
        session,
        action="FAMILY_CREATE",
        entity_type="Family",
        entity_id=str(family.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        after=family_to_dict(family),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(family)
    return family


async def patch_family(
    session: AsyncSession,
    family_id: uuid.UUID,
    payload: FamilyPatch,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Family:
    family = await session.get(Family, family_id)
    if family is None:
        raise AppError("FAMILY_NOT_FOUND", "Family not found", status_code=status.HTTP_404_NOT_FOUND)

    before = family_to_dict(family)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        dup = await session.execute(
            select(Family).where(func.lower(Family.name) == data["name"].lower(), Family.id != family_id)
        )
        if dup.scalar_one_or_none() is not None:
            raise AppError(
                "FAMILY_DUPLICATE",
                "A family with this name already exists",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("name", "DUPLICATE")],
            )
        family.name = data["name"]

    if "description" in data:
        family.description = data["description"]
    if "active" in data and data["active"] is not None:
        if data["active"] is False:
            active_skills = await session.execute(
                select(func.count())
                .select_from(CatalogSkill)
                .where(CatalogSkill.family_id == family_id, CatalogSkill.active.is_(True))
            )
            if int(active_skills.scalar_one()) > 0:
                raise AppError(
                    "FAMILY_IN_USE",
                    "Cannot deactivate a family that still has active catalog skills",
                    status_code=status.HTTP_409_CONFLICT,
                    fields=[FieldError("active", "FAMILY_IN_USE")],
                )
        family.active = data["active"]

    await write_audit_event(
        session,
        action="FAMILY_UPDATE",
        entity_type="Family",
        entity_id=str(family.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        before=before,
        after=family_to_dict(family),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(family)
    return family


async def list_catalog_skills(
    session: AsyncSession, *, active_only: bool = False
) -> list[CatalogSkill]:
    stmt = select(CatalogSkill).options(selectinload(CatalogSkill.family)).order_by(CatalogSkill.name)
    if active_only:
        stmt = stmt.where(CatalogSkill.active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _require_active_family(session: AsyncSession, family_id: uuid.UUID) -> Family:
    family = await session.get(Family, family_id)
    if family is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Family is not resolvable",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("familyId", "CONFIG_INCOMPLETE")],
        )
    if not family.active:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Family is not active",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("familyId", "CONFIG_INCOMPLETE")],
        )
    return family


async def create_catalog_skill(
    session: AsyncSession,
    payload: CatalogSkillCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> CatalogSkill:
    family = await _require_active_family(session, payload.familyId)
    family_name = family.name

    dup = await session.execute(
        select(CatalogSkill).where(func.lower(CatalogSkill.name) == payload.name.lower())
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "SKILL_DUPLICATE",
            "A catalog skill with this name already exists",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    skill = CatalogSkill(
        name=payload.name,
        number=payload.number,
        family_id=family.id,
        description=payload.description,
        active=True,
    )
    session.add(skill)
    await session.flush()

    await write_audit_event(
        session,
        action="CATALOG_SKILL_CREATE",
        entity_type="CatalogSkill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        after=catalog_skill_to_dict(skill, family_name=family_name),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    result = await session.execute(
        select(CatalogSkill)
        .options(selectinload(CatalogSkill.family))
        .where(CatalogSkill.id == skill.id)
    )
    return result.scalar_one()


async def patch_catalog_skill(
    session: AsyncSession,
    skill_id: uuid.UUID,
    payload: CatalogSkillPatch,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> CatalogSkill:
    result = await session.execute(
        select(CatalogSkill).options(selectinload(CatalogSkill.family)).where(CatalogSkill.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "Catalog skill not found", status_code=status.HTTP_404_NOT_FOUND)

    before = catalog_skill_to_dict(skill, family_name=skill.family.name if skill.family else None)
    data = payload.model_dump(exclude_unset=True)

    if "familyId" in data:
        if data["familyId"] is None:
            raise AppError(
                "VALIDATION_ERROR",
                "Family is required",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("familyId", "REQUIRED")],
            )
        family = await _require_active_family(session, data["familyId"])
        skill.family_id = family.id

    if "name" in data and data["name"] is not None:
        dup = await session.execute(
            select(CatalogSkill).where(
                func.lower(CatalogSkill.name) == data["name"].lower(),
                CatalogSkill.id != skill_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise AppError(
                "SKILL_DUPLICATE",
                "A catalog skill with this name already exists",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("name", "DUPLICATE")],
            )
        skill.name = data["name"]

    if "number" in data:
        skill.number = data["number"]
    if "description" in data:
        skill.description = data["description"]
    if "active" in data and data["active"] is not None:
        skill.active = data["active"]

    await session.flush()
    await session.refresh(skill, attribute_names=["family"])

    await write_audit_event(
        session,
        action="CATALOG_SKILL_UPDATE",
        entity_type="CatalogSkill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        before=before,
        after=catalog_skill_to_dict(skill, family_name=skill.family.name if skill.family else None),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill, attribute_names=["family"])
    return skill


async def catalog_skill_has_cycle_associations(session: AsyncSession, skill_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(func.count()).select_from(Skill).where(Skill.catalog_skill_id == skill_id)
    )
    return int(result.scalar_one()) > 0
