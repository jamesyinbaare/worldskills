"""Skill stage pathway configuration (US-STG-01)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Cycle, CycleStatus, MarkingScheme, Skill, Stage, User, Zone
from app.schemas.stages import PathwayPut, StagePathwayItem
from app.services.audit import write_audit_event
from app.services.pathway_engine import StageNode, compute_finalists_per_skill


def stage_to_dict(stage: Stage) -> dict[str, Any]:
    return {
        "id": str(stage.id),
        "cycleId": str(stage.cycle_id),
        "skillId": str(stage.skill_id) if stage.skill_id else None,
        "name": stage.name,
        "order": stage.order,
        "type": stage.stage_type,
        "opensAt": stage.opens_at.isoformat() if stage.opens_at else None,
        "closesAt": stage.closes_at.isoformat() if stage.closes_at else None,
        "quota": stage.quota,
        "quotaByZone": stage.quota_by_zone,
        "minScore": stage.min_score,
        "schemeId": str(stage.scheme_id) if stage.scheme_id else None,
        "branch": stage.branch,
    }


def _rollup_quota(quota_by_zone: dict[str, int]) -> int:
    return sum(int(v) for v in quota_by_zone.values())


def _nodes_from_payload(stages: list[StagePathwayItem]) -> list[StageNode]:
    return [
        StageNode(
            order=s.order,
            stage_type=s.type,
            branch=s.branch,
            quota_by_zone=s.quotaByZone,
            min_score=s.minScore,
        )
        for s in stages
    ]


def _validate_orders(stages: list[StagePathwayItem]) -> None:
    orders = sorted(s.order for s in stages)
    if len(orders) != len(set(orders)) or orders != list(range(1, len(orders) + 1)):
        raise AppError(
            "ORDER_INVALID",
            "Stage orders must be unique and contiguous starting at 1",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("stages.order", "ORDER_INVALID")],
        )


def _validate_branch_targets(stages: list[StagePathwayItem]) -> None:
    orders = {s.order for s in stages}
    for stage in stages:
        if not stage.branch:
            continue
        targets: list[int] = []
        if stage.branch.get("default") is not None:
            targets.append(int(stage.branch["default"]))
        for value in (stage.branch.get("byFamily") or {}).values():
            targets.append(int(value))
        for target in targets:
            if target not in orders:
                raise AppError(
                    "BRANCH_TARGET_MISSING",
                    f"Branch target order {target} is not in the pathway",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    fields=[FieldError("stages.branch", "BRANCH_TARGET_MISSING")],
                )


async def _require_cycle_for_pathway(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    controlled_change_reason: str | None,
) -> Cycle:
    result = await session.execute(select(Cycle).where(Cycle.id == cycle_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=status.HTTP_404_NOT_FOUND)

    if cycle.status in {CycleStatus.LOCKED, CycleStatus.CLOSED}:
        raise AppError(
            "CYCLE_LOCKED",
            "Cycle is locked and cannot accept pathway changes",
            status_code=status.HTTP_409_CONFLICT,
        )

    if cycle.status == CycleStatus.ACTIVE:
        if not controlled_change_reason or not controlled_change_reason.strip():
            raise AppError(
                "CYCLE_LOCKED",
                "Active cycle pathway changes require controlledChangeReason",
                status_code=status.HTTP_409_CONFLICT,
            )
    return cycle


async def _resolve_scheme(
    session: AsyncSession, *, cycle_id: uuid.UUID, scheme_id: uuid.UUID
) -> uuid.UUID:
    result = await session.execute(
        select(MarkingScheme).where(MarkingScheme.id == scheme_id, MarkingScheme.cycle_id == cycle_id)
    )
    if result.scalar_one_or_none() is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "schemeId is not resolvable in this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("schemeId", "CONFIG_INCOMPLETE")],
        )
    return scheme_id


async def _resolve_zones(
    session: AsyncSession, *, cycle_id: uuid.UUID, quota_by_zone: dict[str, int]
) -> None:
    zone_ids = [uuid.UUID(z) for z in quota_by_zone]
    result = await session.execute(
        select(Zone.id).where(Zone.cycle_id == cycle_id, Zone.id.in_(zone_ids))
    )
    found = {row[0] for row in result.all()}
    missing = [zid for zid in zone_ids if zid not in found]
    if missing:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "quotaByZone references a zone not in this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("quotaByZone", "CONFIG_INCOMPLETE")],
        )


async def put_skill_pathway(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    skill_id: uuid.UUID,
    payload: PathwayPut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[list[Stage], int]:
    await _require_cycle_for_pathway(
        session, cycle_id, controlled_change_reason=payload.controlledChangeReason
    )

    skill_result = await session.execute(
        select(Skill).where(Skill.id == skill_id, Skill.cycle_id == cycle_id)
    )
    skill = skill_result.scalar_one_or_none()
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "Skill not found in cycle", status_code=status.HTTP_404_NOT_FOUND)

    _validate_orders(payload.stages)
    _validate_branch_targets(payload.stages)

    for item in payload.stages:
        if item.minScore is not None and (item.minScore < 0 or item.minScore > 100):
            raise AppError(
                "SCORE_RANGE",
                "minScore must be between 0 and 100",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("minScore", "SCORE_RANGE")],
            )
        for amount in item.quotaByZone.values():
            if amount < 0:
                raise AppError(
                    "QUOTA_INVALID",
                    "quota must be an integer >= 0 per zone",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    fields=[FieldError("quotaByZone", "QUOTA_INVALID")],
                )
        await _resolve_scheme(session, cycle_id=cycle_id, scheme_id=item.schemeId)
        await _resolve_zones(session, cycle_id=cycle_id, quota_by_zone=item.quotaByZone)

    existing = (
        await session.execute(
            select(Stage).where(Stage.cycle_id == cycle_id, Stage.skill_id == skill_id).order_by(Stage.order)
        )
    ).scalars().all()
    before = [stage_to_dict(s) for s in existing]

    await session.execute(
        delete(Stage).where(Stage.cycle_id == cycle_id, Stage.skill_id == skill_id)
    )
    await session.flush()

    created: list[Stage] = []
    for item in sorted(payload.stages, key=lambda s: s.order):
        rollup = _rollup_quota(item.quotaByZone)
        stage = Stage(
            cycle_id=cycle_id,
            skill_id=skill_id,
            name=f"{skill.name} — {item.type} #{item.order}",
            order=item.order,
            stage_type=item.type,
            opens_at=item.opensAt.replace(tzinfo=None) if item.opensAt else None,
            closes_at=item.closesAt.replace(tzinfo=None) if item.closesAt else None,
            quota=rollup,
            quota_by_zone=dict(item.quotaByZone),
            min_score=item.minScore,
            scheme_id=item.schemeId,
            branch=dict(item.branch) if item.branch else None,
        )
        session.add(stage)
        created.append(stage)

    await session.flush()
    finalists = compute_finalists_per_skill(_nodes_from_payload(payload.stages))
    after = [stage_to_dict(s) for s in created]

    reason = None
    if payload.controlledChangeReason and payload.controlledChangeReason.strip():
        reason = payload.controlledChangeReason.strip()

    await write_audit_event(
        session,
        action="PATHWAY_UPDATE",
        entity_type="Skill",
        entity_id=str(skill_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        before={"stages": before},
        after={"stages": after, "finalistsPerSkill": finalists},
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    for stage in created:
        await session.refresh(stage)
    return created, finalists
