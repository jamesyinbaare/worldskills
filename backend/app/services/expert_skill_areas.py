"""Global expert ↔ catalog skill area bindings."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import CatalogSkill, ExpertSkillArea, Family, User, UserRole
from app.services.audit import write_audit_event

_ASSIGNABLE_ROLES = {UserRole.EXPERT, UserRole.CHIEF_EXPERT}


def skill_area_out(row: ExpertSkillArea, catalog: CatalogSkill, family: Family | None) -> dict[str, Any]:
    return {
        "catalogSkillId": str(catalog.id),
        "name": catalog.name,
        "number": catalog.number,
        "familyId": str(catalog.family_id),
        "familyName": family.name if family else None,
        "active": catalog.active,
    }


async def _load_expert(session: AsyncSession, user_id: uuid.UUID) -> User:
    expert = await session.get(User, user_id)
    if expert is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)
    if expert.role not in _ASSIGNABLE_ROLES:
        raise AppError(
            "INVALID_ROLE",
            "Only expert accounts can have skill areas",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("userId", "INVALID_ROLE")],
        )
    return expert


async def _resolve_active_catalog_skills(
    session: AsyncSession, catalog_skill_ids: list[uuid.UUID]
) -> list[CatalogSkill]:
    if not catalog_skill_ids:
        return []
    unique_ids = list(dict.fromkeys(catalog_skill_ids))
    result = await session.execute(
        select(CatalogSkill).where(
            CatalogSkill.id.in_(unique_ids),
            CatalogSkill.active.is_(True),
        )
    )
    found = {row.id: row for row in result.scalars().all()}
    missing = [skill_id for skill_id in unique_ids if skill_id not in found]
    if missing:
        raise AppError(
            "INVALID_SKILL_AREA",
            "One or more catalog skill areas are invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("catalogSkillIds", "INVALID")],
        )
    return [found[skill_id] for skill_id in unique_ids]


async def list_expert_skill_areas(session: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    await _load_expert(session, user_id)
    rows = (
        await session.execute(
            select(ExpertSkillArea, CatalogSkill, Family)
            .join(CatalogSkill, CatalogSkill.id == ExpertSkillArea.catalog_skill_id)
            .join(Family, Family.id == CatalogSkill.family_id)
            .where(ExpertSkillArea.expert_id == user_id)
            .order_by(Family.name, CatalogSkill.name)
        )
    ).all()
    return [skill_area_out(row, catalog, family) for row, catalog, family in rows]


async def set_expert_skill_areas(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    catalog_skill_ids: list[uuid.UUID],
    ip: str | None = None,
    user_agent: str | None = None,
) -> list[dict[str, Any]]:
    expert = await _load_expert(session, user_id)
    catalogs = await _resolve_active_catalog_skills(session, catalog_skill_ids)

    existing = (
        await session.execute(select(ExpertSkillArea).where(ExpertSkillArea.expert_id == user_id))
    ).scalars().all()
    before_ids = sorted(str(row.catalog_skill_id) for row in existing)
    wanted = {c.id for c in catalogs}

    for row in existing:
        if row.catalog_skill_id not in wanted:
            await session.delete(row)

    existing_ids = {row.catalog_skill_id for row in existing}
    for catalog in catalogs:
        if catalog.id not in existing_ids:
            session.add(
                ExpertSkillArea(
                    expert_id=expert.id,
                    catalog_skill_id=catalog.id,
                )
            )

    await session.flush()
    after = await list_expert_skill_areas(session, user_id)
    await write_audit_event(
        session,
        action="EXPERT_SKILL_AREAS_SET",
        entity_type="User",
        entity_id=str(user_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        before={"catalogSkillIds": before_ids},
        after={"catalogSkillIds": [item["catalogSkillId"] for item in after]},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return after


async def expert_has_catalog_skill(
    session: AsyncSession, *, expert_id: uuid.UUID, catalog_skill_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(ExpertSkillArea.id).where(
                ExpertSkillArea.expert_id == expert_id,
                ExpertSkillArea.catalog_skill_id == catalog_skill_id,
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def list_catalog_skill_ids_for_expert(
    session: AsyncSession, expert_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(ExpertSkillArea.catalog_skill_id).where(ExpertSkillArea.expert_id == expert_id)
        )
    ).scalars().all()
    return list(rows)


async def list_experts_for_catalog_skill(
    session: AsyncSession, catalog_skill_id: uuid.UUID
) -> list[User]:
    result = await session.execute(
        select(User)
        .join(ExpertSkillArea, ExpertSkillArea.expert_id == User.id)
        .where(
            ExpertSkillArea.catalog_skill_id == catalog_skill_id,
            User.is_active.is_(True),
            User.role.in_(list(_ASSIGNABLE_ROLES)),
        )
        .order_by(User.full_name)
    )
    return list(result.scalars().all())
