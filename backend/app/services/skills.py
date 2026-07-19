"""Skill create and capacity enforcement service."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import AgeRule, Cycle, CycleStatus, MarkingScheme, Pathway, Skill, User
from app.schemas.skills import SkillCreate
from app.services.audit import write_audit_event


def skill_to_dict(skill: Skill) -> dict[str, Any]:
    return {
        "id": str(skill.id),
        "cycleId": str(skill.cycle_id),
        "name": skill.name,
        "number": skill.number,
        "familyId": skill.family_id,
        "ageRuleId": str(skill.age_rule_id) if skill.age_rule_id else None,
        "pathwayId": str(skill.pathway_id) if skill.pathway_id else None,
        "schemeId": str(skill.scheme_id) if skill.scheme_id else None,
        "capacity": skill.capacity,
        "active": skill.active,
    }


def enforce_skill_capacity(skill: Skill, *, occupied_count: int) -> None:
    """Block a new registration when the skill is at configured capacity.

    Called by registration flow (US-REG-01). Waitlist is out of scope here.
    """
    if skill.capacity is None:
        return
    if occupied_count >= skill.capacity:
        raise AppError(
            "SKILL_CAPACITY_REACHED",
            f"Skill '{skill.name}' is at capacity ({skill.capacity})",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "SKILL_CAPACITY_REACHED")],
        )


async def _require_cycle_mutable(session: AsyncSession, cycle_id: uuid.UUID) -> Cycle:
    result = await session.execute(select(Cycle).where(Cycle.id == cycle_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=status.HTTP_404_NOT_FOUND)
    if cycle.status not in {CycleStatus.DRAFT}:
        # Controlled change for ACTIVE is a later story; reject structural skill adds when locked/closed.
        if cycle.status in {CycleStatus.LOCKED, CycleStatus.CLOSED}:
            raise AppError(
                "CYCLE_LOCKED",
                "Cycle is locked and cannot accept new skills",
                status_code=status.HTTP_409_CONFLICT,
            )
        # ACTIVE: allow adds only if we treat as controlled change — keep DRAFT-only for MVP safety.
        if cycle.status == CycleStatus.ACTIVE:
            raise AppError(
                "CYCLE_LOCKED",
                "Active cycle does not allow skill creation without controlled change",
                status_code=status.HTTP_409_CONFLICT,
            )
    return cycle


async def _resolve_in_cycle(
    session: AsyncSession,
    *,
    cycle_id: uuid.UUID,
    model: type,
    entity_id: uuid.UUID | None,
    field_name: str,
) -> uuid.UUID | None:
    if entity_id is None:
        return None
    result = await session.execute(
        select(model).where(model.id == entity_id, model.cycle_id == cycle_id)  # type: ignore[attr-defined]
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            f"{field_name} is not resolvable in this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError(field_name, "CONFIG_INCOMPLETE")],
        )
    return entity_id


async def create_skill(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    payload: SkillCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    await _require_cycle_mutable(session, cycle_id)

    if not payload.name or not payload.name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("name", "REQUIRED")],
        )

    if payload.capacity is not None and payload.capacity <= 0:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid capacity",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("capacity", "INVALID_CAPACITY")],
        )

    dup = await session.execute(
        select(Skill).where(Skill.cycle_id == cycle_id, Skill.name == payload.name)
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "SKILL_DUPLICATE",
            "A skill with this name already exists in the cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    age_rule_id = await _resolve_in_cycle(
        session, cycle_id=cycle_id, model=AgeRule, entity_id=payload.ageRuleId, field_name="ageRuleId"
    )
    pathway_id = await _resolve_in_cycle(
        session, cycle_id=cycle_id, model=Pathway, entity_id=payload.pathwayId, field_name="pathwayId"
    )
    scheme_id = await _resolve_in_cycle(
        session,
        cycle_id=cycle_id,
        model=MarkingScheme,
        entity_id=payload.schemeId,
        field_name="schemeId",
    )

    skill = Skill(
        cycle_id=cycle_id,
        name=payload.name,
        number=payload.number,
        family_id=payload.familyId,
        age_rule_id=age_rule_id,
        pathway_id=pathway_id,
        scheme_id=scheme_id,
        capacity=payload.capacity,
        active=True,
    )
    session.add(skill)
    await session.flush()

    await write_audit_event(
        session,
        action="SKILL_CREATE",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill
