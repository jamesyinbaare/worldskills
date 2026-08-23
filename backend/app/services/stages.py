"""Skill stage pathway configuration (US-STG-01)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Competition, Exercise, Skill, Stage, StageSelectionMode, Submission, User, Zone
from app.schemas.stages import PathwayPut, StagePathwayItem
from app.services.audit import write_audit_event
from app.services.pathway_engine import StageNode, compute_finalists_per_skill

# Match submissions.IMMUTABLE_STATES — avoid importing submissions (circular).
_IMMUTABLE_SUBMISSION_STATES = ("ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN")


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def assert_stage_available(stage: Stage, *, now: datetime | None = None) -> None:
    """Block competitor actions before stage.opens_at (exercise availability)."""
    if stage.opens_at is None:
        return
    current = _as_naive(now or datetime.utcnow())
    opens = _as_naive(stage.opens_at)
    if current < opens:
        raise AppError(
            "WINDOW_CLOSED",
            "Exercise is not available yet",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("opensAt", "WINDOW_CLOSED")],
        )


def stage_to_dict(stage: Stage) -> dict[str, Any]:
    return {
        "id": str(stage.id),
        "competitionId": str(stage.competition_id),
        "skillId": str(stage.skill_id) if stage.skill_id else None,
        "name": stage.name,
        "order": stage.order,
        "type": stage.stage_type,
        "selectionMode": stage.selection_mode,
        "opensAt": stage.opens_at.isoformat() if stage.opens_at else None,
        "closesAt": stage.closes_at.isoformat() if stage.closes_at else None,
        "quota": stage.quota,
        "quotaByZone": stage.quota_by_zone,
        "minScore": stage.min_score,
        "branch": stage.branch,
    }


def _rollup_quota(quota_by_zone: dict[str, int]) -> int:
    return sum(int(v) for v in quota_by_zone.values())


def _nodes_from_payload(stages: list[StagePathwayItem]) -> list[StageNode]:
    nodes: list[StageNode] = []
    for s in stages:
        mode = s.selectionMode
        if mode == "NATIONAL_POOL":
            nodes.append(
                StageNode(
                    order=s.order,
                    stage_type=s.type,
                    branch=s.branch,
                    quota_by_zone={},
                    min_score=s.minScore,
                    selection_mode=mode,
                    overall_quota=s.quota,
                )
            )
        else:
            nodes.append(
                StageNode(
                    order=s.order,
                    stage_type=s.type,
                    branch=s.branch,
                    quota_by_zone=s.quotaByZone or {},
                    min_score=s.minScore,
                    selection_mode=mode,
                    overall_quota=None,
                )
            )
    return nodes


def _validate_orders(stages: list[StagePathwayItem]) -> None:
    orders = sorted(s.order for s in stages)
    if len(orders) != len(set(orders)) or orders != list(range(1, len(orders) + 1)):
        raise AppError(
            "ORDER_INVALID",
            "Stage orders must be unique and contiguous starting at 1",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    fields=[FieldError("stages.branch", "BRANCH_TARGET_MISSING")],
                )


async def _require_cycle_for_pathway(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    controlled_change_reason: str | None,
) -> Competition:
    _ = controlled_change_reason
    result = await session.execute(select(Competition).where(Competition.id == competition_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    return cycle


async def _resolve_zones(
    session: AsyncSession, *, competition_id: uuid.UUID, quota_by_zone: dict[str, int]
) -> None:
    zone_ids = [uuid.UUID(z) for z in quota_by_zone]
    result = await session.execute(
        select(Zone.id).where(Zone.competition_id == competition_id, Zone.id.in_(zone_ids))
    )
    found = {row[0] for row in result.all()}
    missing = [zid for zid in zone_ids if zid not in found]
    if missing:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "quotaByZone references a zone not in this competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("quotaByZone", "CONFIG_INCOMPLETE")],
        )


async def put_skill_pathway(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    payload: PathwayPut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[list[Stage], int]:
    await _require_cycle_for_pathway(
        session, competition_id, controlled_change_reason=payload.controlledChangeReason
    )

    skill_result = await session.execute(
        select(Skill).where(Skill.id == skill_id, Skill.competition_id == competition_id)
    )
    skill = skill_result.scalar_one_or_none()
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "Skill not found in cycle", status_code=status.HTTP_404_NOT_FOUND)

    _validate_orders(payload.stages)
    _validate_branch_targets(payload.stages)

    for item in payload.stages:
        stage_type = (item.type or "").strip().upper()
        if stage_type not in {"VIRTUAL", "PHYSICAL"}:
            raise AppError(
                "INVALID_TYPE",
                "Stage type must be VIRTUAL or PHYSICAL",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("type", "INVALID_TYPE")],
            )
        if item.minScore is not None and (item.minScore < 0 or item.minScore > 100):
            raise AppError(
                "SCORE_RANGE",
                "minScore must be between 0 and 100",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("minScore", "SCORE_RANGE")],
            )
        if item.opensAt is not None and item.closesAt is not None:
            opens = item.opensAt.replace(tzinfo=None)
            closes = item.closesAt.replace(tzinfo=None)
            if closes <= opens:
                raise AppError(
                    "BEFORE_OPENS",
                    "closesAt must be after opensAt",
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    fields=[FieldError("closesAt", "BEFORE_OPENS")],
                )
        mode = item.selectionMode
        if mode == "PER_ZONE":
            if not item.quotaByZone:
                raise AppError(
                    "QUOTA_INVALID",
                    "quotaByZone is required for PER_ZONE stages",
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    fields=[FieldError("quotaByZone", "QUOTA_INVALID")],
                )
            for amount in item.quotaByZone.values():
                if amount < 0:
                    raise AppError(
                        "QUOTA_INVALID",
                        "quota must be an integer >= 0 per zone",
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        fields=[FieldError("quotaByZone", "QUOTA_INVALID")],
                    )
            await _resolve_zones(session, competition_id=competition_id, quota_by_zone=item.quotaByZone)
        else:
            if item.quota is None or item.quota < 0:
                raise AppError(
                    "QUOTA_INVALID",
                    "quota is required for NATIONAL_POOL stages",
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    fields=[FieldError("quota", "QUOTA_INVALID")],
                )

    existing = (
        await session.execute(
            select(Stage).where(Stage.competition_id == competition_id, Stage.skill_id == skill_id).order_by(Stage.order)
        )
    ).scalars().all()
    before = [stage_to_dict(s) for s in existing]
    by_order = {s.order: s for s in existing}
    keep_orders = {item.order for item in payload.stages}

    # Refuse to drop stages that already have submissions or published exercise work
    for stage in existing:
        if stage.order in keep_orders:
            continue
        has_submission = (
            await session.execute(
                select(Submission.id).where(Submission.stage_id == stage.id).limit(1)
            )
        ).first() is not None
        exercise = (
            await session.execute(select(Exercise).where(Exercise.stage_id == stage.id))
        ).scalar_one_or_none()
        has_exercise_work = bool(
            exercise
            and (
                exercise.status == "PUBLISHED"
                or exercise.scheme_id
                or exercise.pack_object_key
            )
        )
        if has_submission or has_exercise_work:
            raise AppError(
                "PATHWAY_LOCKED",
                "Cannot remove a stage that already has submissions or a published exercise. "
                "Adjust quotas/windows on existing stages instead.",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("stages", "PATHWAY_LOCKED")],
            )
        await session.delete(stage)

    await session.flush()

    created: list[Stage] = []
    for item in sorted(payload.stages, key=lambda s: s.order):
        if item.selectionMode == "NATIONAL_POOL":
            rollup = int(item.quota or 0)
            quota_by_zone = None
            selection_mode = StageSelectionMode.NATIONAL_POOL.value
            scalar_quota = rollup
        else:
            quota_by_zone = dict(item.quotaByZone or {})
            rollup = _rollup_quota(quota_by_zone)
            selection_mode = StageSelectionMode.PER_ZONE.value
            scalar_quota = rollup

        stage = by_order.get(item.order)
        if stage is None:
            stage = Stage(
                competition_id=competition_id,
                skill_id=skill_id,
                name=f"{skill.name} — {item.type} #{item.order}",
                order=item.order,
            )
            session.add(stage)

        stage.name = f"{skill.name} — {item.type} #{item.order}"
        stage.stage_type = item.type
        stage.selection_mode = selection_mode
        stage.opens_at = item.opensAt.replace(tzinfo=None) if item.opensAt else None
        stage.closes_at = item.closesAt.replace(tzinfo=None) if item.closesAt else None
        stage.quota = scalar_quota
        stage.quota_by_zone = quota_by_zone
        stage.min_score = item.minScore
        stage.branch = dict(item.branch) if item.branch else None
        created.append(stage)

    await session.flush()

    # Keep open submissions on the live stage window when admins extend/shorten closes_at
    for stage in created:
        await session.execute(
            update(Submission)
            .where(
                Submission.stage_id == stage.id,
                Submission.state.notin_(_IMMUTABLE_SUBMISSION_STATES),
            )
            .values(deadline_at=stage.closes_at)
        )

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
        competition_id=competition_id,
        before={"stages": before},
        after={"stages": after, "finalistsPerSkill": finalists},
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    for stage in created:
        await session.refresh(stage)

    # If pathway windows opened a published exercise, fan-out availability SMS
    try:
        from app.services import competition_sms

        for stage in created:
            await competition_sms.notify_exercise_available(
                session,
                competition_id=competition_id,
                stage_id=stage.id,
                trigger="pathway_window_update",
                actor=actor,
                commit=True,
            )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "EXERCISE_AVAILABLE SMS failed after pathway update competition=%s",
            competition_id,
        )

    return created, finalists


async def get_skill_pathway(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> tuple[list[Stage], int | None]:
    skill_result = await session.execute(
        select(Skill).where(Skill.id == skill_id, Skill.competition_id == competition_id)
    )
    if skill_result.scalar_one_or_none() is None:
        raise AppError("SKILL_NOT_FOUND", "Skill not found in cycle", status_code=status.HTTP_404_NOT_FOUND)

    stages = list(
        (
            await session.execute(
                select(Stage)
                .where(Stage.competition_id == competition_id, Stage.skill_id == skill_id)
                .order_by(Stage.order)
            )
        )
        .scalars()
        .all()
    )
    if not stages:
        return [], None
    nodes = [
        StageNode(
            order=s.order,
            stage_type=s.stage_type,
            branch=s.branch,
            quota_by_zone={str(k): int(v) for k, v in (s.quota_by_zone or {}).items()},
            min_score=s.min_score,
            selection_mode=s.selection_mode or StageSelectionMode.PER_ZONE.value,
            overall_quota=s.quota if (s.selection_mode or "").upper() == "NATIONAL_POOL" else None,
        )
        for s in stages
    ]
    return stages, compute_finalists_per_skill(nodes)
