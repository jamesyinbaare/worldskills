"""Cycle create / clone / validate / activate service."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import (
    AgeRule,
    Cycle,
    CycleStatus,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    User,
)
from app.schemas.cycles import CycleCreate, ValidationIssue
from app.services.audit import write_audit_event
from app.services.config_resolution import load_cycle_config


async def _find_duplicate(
    session: AsyncSession,
    *,
    name: str,
    period_start: date,
    period_end: date,
    exclude_id: uuid.UUID | None = None,
) -> Cycle | None:
    """Name collision with an existing cycle in an overlapping period."""
    stmt = select(Cycle).where(
        Cycle.name == name,
        Cycle.period_start <= period_end,
        Cycle.period_end >= period_start,
    )
    if exclude_id is not None:
        stmt = stmt.where(Cycle.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def cycle_to_dict(cycle: Cycle) -> dict[str, Any]:
    return {
        "id": str(cycle.id),
        "name": cycle.name,
        "period": {"start": str(cycle.period_start), "end": str(cycle.period_end)},
        "timeZone": cycle.time_zone,
        "status": cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
        "languages": cycle.languages,
        "organisingBody": cycle.organising_body,
        "branding": cycle.branding,
    }


async def create_cycle(
    session: AsyncSession,
    payload: CycleCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Cycle:
    if payload.period.end <= payload.period.start:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid period",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("period.end", "BEFORE_START")],
        )

    dup = await _find_duplicate(
        session,
        name=payload.name,
        period_start=payload.period.start,
        period_end=payload.period.end,
    )
    if dup is not None:
        raise AppError(
            "CYCLE_DUPLICATE",
            "A cycle with this name already exists in an overlapping period",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    cycle = Cycle(
        name=payload.name,
        period_start=payload.period.start,
        period_end=payload.period.end,
        time_zone=payload.timeZone,
        status=CycleStatus.DRAFT,
        languages=["en"],
        organising_body=payload.organisingBody,
        branding=payload.branding,
    )
    session.add(cycle)
    await session.flush()

    await write_audit_event(
        session,
        action="CYCLE_CREATE",
        entity_type="Cycle",
        entity_id=str(cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle.id,
        after=cycle_to_dict(cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def list_cycles(session: AsyncSession) -> list[Cycle]:
    result = await session.execute(select(Cycle).order_by(Cycle.created_at.desc()))
    return list(result.scalars().all())


async def get_cycle(session: AsyncSession, cycle_id: uuid.UUID) -> Cycle:
    result = await session.execute(
        select(Cycle)
        .where(Cycle.id == cycle_id)
        .options(
            selectinload(Cycle.skills),
            selectinload(Cycle.stages),
            selectinload(Cycle.age_rules),
            selectinload(Cycle.pathways),
            selectinload(Cycle.marking_schemes),
        )
    )
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)
    return cycle


async def clone_cycle(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Cycle:
    source = await get_cycle(session, source_id)

    new_cycle = Cycle(
        name=f"{source.name} (copy)",
        period_start=source.period_start,
        period_end=source.period_end,
        time_zone=source.time_zone,
        status=CycleStatus.DRAFT,
        languages=list(source.languages or []),
        organising_body=source.organising_body,
        branding=source.branding,
    )
    session.add(new_cycle)
    await session.flush()

    age_map: dict[uuid.UUID, AgeRule] = {}
    for rule in source.age_rules:
        cloned = AgeRule(
            cycle_id=new_cycle.id,
            name=rule.name,
            max_age=rule.max_age,
            reference_date=rule.reference_date,
        )
        session.add(cloned)
        await session.flush()
        age_map[rule.id] = cloned

    path_map: dict[uuid.UUID, Pathway] = {}
    for path in source.pathways:
        cloned = Pathway(cycle_id=new_cycle.id, name=path.name)
        session.add(cloned)
        await session.flush()
        path_map[path.id] = cloned

    scheme_map: dict[uuid.UUID, MarkingScheme] = {}
    for scheme in source.marking_schemes:
        cloned = MarkingScheme(cycle_id=new_cycle.id, name=scheme.name)
        session.add(cloned)
        await session.flush()
        scheme_map[scheme.id] = cloned

    skill_map: dict[uuid.UUID, Skill] = {}
    for skill in source.skills:
        cloned = Skill(
            cycle_id=new_cycle.id,
            name=skill.name,
            number=skill.number,
            family_id=skill.family_id,
            age_rule_id=age_map[skill.age_rule_id].id if skill.age_rule_id and skill.age_rule_id in age_map else None,
            pathway_id=path_map[skill.pathway_id].id if skill.pathway_id and skill.pathway_id in path_map else None,
            scheme_id=scheme_map[skill.scheme_id].id if skill.scheme_id and skill.scheme_id in scheme_map else None,
            capacity=skill.capacity,
            active=skill.active,
        )
        session.add(cloned)
        await session.flush()
        skill_map[skill.id] = cloned

    for stage in source.stages:
        cloned = Stage(
            cycle_id=new_cycle.id,
            skill_id=skill_map[stage.skill_id].id if stage.skill_id and stage.skill_id in skill_map else None,
            name=stage.name,
            order=stage.order,
            stage_type=stage.stage_type,
            opens_at=stage.opens_at,
            closes_at=stage.closes_at,
            quota=stage.quota,
            quota_by_zone=dict(stage.quota_by_zone) if stage.quota_by_zone else None,
            min_score=stage.min_score,
            scheme_id=scheme_map[stage.scheme_id].id if stage.scheme_id and stage.scheme_id in scheme_map else None,
            branch=dict(stage.branch) if stage.branch else None,
        )
        session.add(cloned)

    await session.flush()
    await write_audit_event(
        session,
        action="CYCLE_CLONE",
        entity_type="Cycle",
        entity_id=str(new_cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=new_cycle.id,
        before={"sourceCycleId": str(source.id)},
        after=cycle_to_dict(new_cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(new_cycle)
    return new_cycle


async def validate_cycle(session: AsyncSession, cycle_id: uuid.UUID) -> tuple[bool, list[ValidationIssue]]:
    cfg = await load_cycle_config(session, cycle_id)
    issues: list[ValidationIssue] = []

    for skill in cfg.skills:
        if skill.age_rule_id is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no age rule",
                    link=f"/admin/cycles/{cycle_id}/skills/{skill.id}",
                )
            )
        if skill.pathway_id is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no pathway",
                    link=f"/admin/cycles/{cycle_id}/skills/{skill.id}",
                )
            )
        if skill.scheme_id is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no marking scheme",
                    link=f"/admin/cycles/{cycle_id}/skills/{skill.id}",
                )
            )

    for stage in cfg.stages:
        if stage.scheme_id is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(stage.id),
                    message=f"Stage '{stage.name}' has no marking scheme",
                    link=f"/admin/cycles/{cycle_id}/stages/{stage.id}",
                )
            )
        effective_quota = stage.quota
        if effective_quota is None and stage.quota_by_zone:
            effective_quota = sum(int(v) for v in stage.quota_by_zone.values())
        if effective_quota is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(stage.id),
                    message=f"Stage '{stage.name}' has no quota",
                    link=f"/admin/cycles/{cycle_id}/stages/{stage.id}",
                )
            )

    # Quota consistency: later stage advancing more than prior stage admits
    by_skill: dict[uuid.UUID | None, list[Stage]] = {}
    for stage in cfg.stages:
        by_skill.setdefault(stage.skill_id, []).append(stage)
    for _skill_id, stages in by_skill.items():
        ordered = sorted(stages, key=lambda s: s.order)
        for i in range(1, len(ordered)):
            prior, curr = ordered[i - 1], ordered[i]
            prior_q = prior.quota
            if prior_q is None and prior.quota_by_zone:
                prior_q = sum(int(v) for v in prior.quota_by_zone.values())
            curr_q = curr.quota
            if curr_q is None and curr.quota_by_zone:
                curr_q = sum(int(v) for v in curr.quota_by_zone.values())
            if prior_q is not None and curr_q is not None and curr_q > prior_q:
                issues.append(
                    ValidationIssue(
                        code="QUOTA_INCONSISTENT",
                        entity=str(curr.id),
                        message=(
                            f"Stage '{curr.name}' quota ({curr_q}) exceeds "
                            f"upstream '{prior.name}' quota ({prior_q})"
                        ),
                        link=f"/admin/cycles/{cycle_id}/stages/{curr.id}",
                    )
                )

    ok = len(issues) == 0
    return ok, issues


async def activate_cycle(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Cycle:
    cycle = await get_cycle(session, cycle_id)

    if cycle.status == CycleStatus.ACTIVE:
        return cycle  # idempotent

    ok, issues = await validate_cycle(session, cycle_id)
    if not ok:
        incomplete = [i for i in issues if i.code == "CONFIG_INCOMPLETE"]
        if incomplete:
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Cycle configuration is incomplete",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError(i.entity, i.code) for i in incomplete],
            )
        raise AppError(
            issues[0].code,
            issues[0].message,
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError(i.entity, i.code) for i in issues],
        )

    before = cycle_to_dict(cycle)
    cycle.status = CycleStatus.ACTIVE
    await session.flush()
    await write_audit_event(
        session,
        action="CYCLE_ACTIVATE",
        entity_type="Cycle",
        entity_id=str(cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle.id,
        before=before,
        after=cycle_to_dict(cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def update_cycle_structural(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    name: str | None,
    actor: User,
) -> Cycle:
    _ = actor
    cycle = await get_cycle(session, cycle_id)
    if cycle.status in {CycleStatus.ACTIVE, CycleStatus.LOCKED, CycleStatus.CLOSED}:
        raise AppError(
            "CYCLE_LOCKED",
            "Structural edits require the controlled-change flow",
            status_code=status.HTTP_409_CONFLICT,
        )
    if name is not None:
        cycle.name = name
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def cycle_has_isolated_data(session: AsyncSession, cycle_a: uuid.UUID, cycle_b: uuid.UUID) -> bool:
    """True when skills from A are not visible under B (isolation check helper)."""
    a_skills = await session.execute(select(Skill.id).where(Skill.cycle_id == cycle_a))
    b_skills = await session.execute(select(Skill.id).where(Skill.cycle_id == cycle_b))
    a_ids = {row[0] for row in a_skills.all()}
    b_ids = {row[0] for row in b_skills.all()}
    return a_ids.isdisjoint(b_ids)
