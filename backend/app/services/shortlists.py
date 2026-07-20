"""US-SHL-01 — generate, confirm and apply shortlists."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability
from app.models import (
    Competitor,
    NotificationOutbox,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    Submission,
    User,
)
from app.schemas.shortlists import (
    ShortlistConfirmOut,
    ShortlistGenerateOut,
    ShortlistRankedItem,
)
from app.services.appeals import require_tie_break_rules_if_needed
from app.services.audit import write_audit_event
from app.services.pathway_engine import (
    Candidate,
    StageNode,
    compute_finalists_per_skill,
    rank_for_shortlist,
    resolve_next_stage,
)


def _stage_nodes(stages: list[Stage]) -> list[StageNode]:
    return [
        StageNode(
            order=s.order,
            stage_type=s.stage_type,
            branch=s.branch,
            quota_by_zone={str(k): int(v) for k, v in (s.quota_by_zone or {}).items()},
            min_score=s.min_score,
        )
        for s in stages
    ]


def _is_final_stage(stage: Stage, skill_stages: list[Stage]) -> bool:
    nodes = _stage_nodes(skill_stages)
    by_order = {n.order: n for n in nodes}
    current = by_order.get(stage.order)
    if current is None:
        return True
    # Leaf if resolve_next_stage would fail
    try:
        resolve_next_stage(nodes, current_order=stage.order, family_id=None)
        return False
    except KeyError:
        return True


async def _require_shortlist_capability(actor: User) -> None:
    if not has_capability(actor.role, Capability.APPROVE_SHORTLIST):
        raise AppError(
            "NOT_AUTHORISED",
            "Chief Expert or Admin required to manage shortlists",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("role", "NOT_AUTHORISED")],
        )


async def generate_shortlist(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ShortlistGenerateOut:
    await _require_shortlist_capability(actor)

    stage = await session.get(Stage, stage_id)
    if stage is None or stage.cycle_id != cycle_id:
        raise AppError("STAGE_NOT_FOUND", "Stage not found in cycle", status_code=404)

    quota_by_zone = {str(k): int(v) for k, v in (stage.quota_by_zone or {}).items()}
    if not quota_by_zone and stage.quota is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Stage quota is not configured",
            status_code=409,
            fields=[FieldError("quotaByZone", "CONFIG_INCOMPLETE")],
        )
    if not quota_by_zone and stage.quota is not None:
        # Legacy scalar: apply same quota only when zone keys known from competitors later
        pass

    # Collect ACCEPTED/LATE submissions for this stage with scores
    subs = (
        await session.execute(
            select(Submission).where(
                Submission.cycle_id == cycle_id,
                Submission.stage_id == stage_id,
                Submission.state.in_(["ACCEPTED", "LATE"]),
            )
        )
    ).scalars().all()
    if not subs:
        # Also accept submissions linked by skill if stage_id unset on old rows — still require scores
        raise AppError(
            "SCORING_INCOMPLETE",
            "No scored submissions for this stage",
            status_code=409,
            fields=[FieldError("stageId", "SCORING_INCOMPLETE")],
        )

    incomplete = [s for s in subs if s.score_total is None]
    if incomplete:
        raise AppError(
            "SCORING_INCOMPLETE",
            "Not all submissions have completed scores",
            status_code=409,
            fields=[FieldError(str(s.id), "SCORING_INCOMPLETE") for s in incomplete[:5]],
        )

    candidates: list[Candidate] = []
    competitor_cache: dict[uuid.UUID, Competitor] = {}
    for sub in subs:
        comp = await session.get(Competitor, sub.competitor_id)
        if comp is None:
            continue
        if comp.status == "DISQUALIFIED":
            continue
        competitor_cache[comp.id] = comp
        candidates.append(
            Candidate(
                competitor_id=str(comp.id),
                zone_id=str(comp.zone_id),
                score=float(sub.score_total or 0),
                date_of_birth=comp.date_of_birth,
                ref_no=comp.ref_no,
            )
        )

    # If only scalar quota, invent per-zone quotas from unique zones present
    if not quota_by_zone and stage.quota is not None:
        zones = {c.zone_id for c in candidates}
        quota_by_zone = {z: int(stage.quota) for z in zones}

    tie_break_rules = await require_tie_break_rules_if_needed(
        session,
        cycle_id,
        candidates=candidates,
        quota_by_zone=quota_by_zone,
        min_score=stage.min_score,
    )
    ranked = rank_for_shortlist(
        candidates,
        quota_by_zone=quota_by_zone,
        min_score=stage.min_score,
        tie_break_rules=tie_break_rules,
    )

    skill_stages: list[Stage] = []
    if stage.skill_id:
        skill_stages = list(
            (
                await session.execute(
                    select(Stage)
                    .where(Stage.cycle_id == cycle_id, Stage.skill_id == stage.skill_id)
                    .order_by(Stage.order)
                )
            ).scalars().all()
        )
    is_final = _is_final_stage(stage, skill_stages) if skill_stages else True

    # Replace any existing provisional shortlist for this stage
    existing = (
        await session.execute(
            select(Shortlist).where(
                Shortlist.cycle_id == cycle_id,
                Shortlist.stage_id == stage_id,
                Shortlist.state == "PROVISIONAL",
            )
        )
    ).scalars().all()
    for old in existing:
        await session.delete(old)
    await session.flush()

    by_zone_payload: dict[str, list[dict[str, Any]]] = {}
    shortlist = Shortlist(
        cycle_id=cycle_id,
        stage_id=stage_id,
        skill_id=stage.skill_id,
        state="PROVISIONAL",
        is_final_stage=is_final,
        generated_at=datetime.utcnow(),
    )
    session.add(shortlist)
    await session.flush()

    items_out: dict[str, list[ShortlistRankedItem]] = {}
    for entry in ranked:
        cid = uuid.UUID(entry.competitor_id)
        zid = uuid.UUID(entry.zone_id)
        comp = competitor_cache.get(cid)
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=cid,
                zone_id=zid,
                score=int(entry.score),
                rank=entry.rank,
                outcome=entry.outcome,
                reason=entry.reason,
                advanced=False,
            )
        )
        item = ShortlistRankedItem(
            competitorId=cid,
            zoneId=zid,
            score=int(entry.score),
            rank=entry.rank,
            outcome=entry.outcome,
            reason=entry.reason,
            refNo=comp.ref_no if comp else None,
        )
        items_out.setdefault(str(zid), []).append(item)
        by_zone_payload.setdefault(str(zid), []).append(item.model_dump(mode="json"))

    shortlist.payload = by_zone_payload
    await session.flush()

    await write_audit_event(
        session,
        action="SHORTLIST_GENERATE",
        entity_type="Shortlist",
        entity_id=str(shortlist.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        after={"stageId": str(stage_id), "state": "PROVISIONAL", "byZone": by_zone_payload},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(shortlist)

    return ShortlistGenerateOut(
        shortlistId=shortlist.id,
        stageId=stage_id,
        state=shortlist.state,
        isFinalStage=is_final,
        byZone=items_out,
        generatedAt=shortlist.generated_at,
    )


async def confirm_shortlist(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ShortlistConfirmOut:
    await _require_shortlist_capability(actor)

    stage = await session.get(Stage, stage_id)
    if stage is None or stage.cycle_id != cycle_id:
        raise AppError("STAGE_NOT_FOUND", "Stage not found in cycle", status_code=404)

    shortlist = (
        await session.execute(
            select(Shortlist)
            .where(
                Shortlist.cycle_id == cycle_id,
                Shortlist.stage_id == stage_id,
                Shortlist.state == "PROVISIONAL",
            )
            .order_by(Shortlist.generated_at.desc())
        )
    ).scalars().first()
    if shortlist is None:
        raise AppError(
            "SHORTLIST_NOT_FOUND",
            "No provisional shortlist to confirm",
            status_code=409,
            fields=[FieldError("stageId", "SHORTLIST_NOT_FOUND")],
        )

    entries = (
        await session.execute(
            select(ShortlistEntry).where(ShortlistEntry.shortlist_id == shortlist.id)
        )
    ).scalars().all()

    # Resolve next stage for advancement
    next_stage: Stage | None = None
    skill_stages: list[Stage] = []
    if stage.skill_id:
        skill_stages = list(
            (
                await session.execute(
                    select(Stage)
                    .where(Stage.cycle_id == cycle_id, Stage.skill_id == stage.skill_id)
                    .order_by(Stage.order)
                )
            ).scalars().all()
        )
        nodes = _stage_nodes(skill_stages)
        skill = await session.get(Skill, stage.skill_id)
        family = skill.family_id if skill else None
        try:
            nxt_node = resolve_next_stage(nodes, current_order=stage.order, family_id=family)
            next_stage = next((s for s in skill_stages if s.order == nxt_node.order), None)
        except KeyError:
            next_stage = None

    advanced_ids: list[uuid.UUID] = []
    waitlist_ids: list[uuid.UUID] = []
    excluded_ids: list[uuid.UUID] = []
    notified = 0
    finalist_items: list[ShortlistRankedItem] = []

    for entry in entries:
        comp = await session.get(Competitor, entry.competitor_id)
        if comp is None:
            continue
        if entry.outcome == "EXCLUDED":
            excluded_ids.append(entry.competitor_id)
            continue
        if entry.outcome == "WAITLIST":
            waitlist_ids.append(entry.competitor_id)
            flags = list(comp.flags or [])
            if "WAITLIST" not in flags:
                flags.append("WAITLIST")
            comp.flags = flags
            if shortlist.is_final_stage:
                pass
            else:
                # Runners-up on waitlist for next stage
                pass
            continue

        # ADVANCE
        advanced_ids.append(entry.competitor_id)
        entry.advanced = True
        if shortlist.is_final_stage or next_stage is None:
            comp.status = "FINALIST"
            finalist_items.append(
                ShortlistRankedItem(
                    competitorId=comp.id,
                    zoneId=entry.zone_id,
                    score=entry.score,
                    rank=entry.rank,
                    outcome="ADVANCE",
                    reason=None,
                    refNo=comp.ref_no,
                )
            )
        else:
            comp.status = "ACTIVE_IN_STAGE"
            # Open path to next stage by ensuring a shell OPEN submission later is out of scope;
            # status ACTIVE_IN_STAGE signals progression.

        session.add(
            NotificationOutbox(
                cycle_id=cycle_id,
                recipient_role="COMPETITOR",
                recipient_id=comp.id,
                template="SHORTLIST_ADVANCED" if entry.outcome == "ADVANCE" else "SHORTLIST_WAITLIST",
                payload={
                    "competitorId": str(comp.id),
                    "stageId": str(stage_id),
                    "outcome": entry.outcome,
                    "nextStageId": str(next_stage.id) if next_stage else None,
                    "finalist": shortlist.is_final_stage,
                },
            )
        )
        notified += 1

    # Waitlist notifications
    for wid in waitlist_ids:
        session.add(
            NotificationOutbox(
                cycle_id=cycle_id,
                recipient_role="COMPETITOR",
                recipient_id=wid,
                template="SHORTLIST_WAITLIST",
                payload={"competitorId": str(wid), "stageId": str(stage_id)},
            )
        )
        notified += 1

    shortlist.state = "CONFIRMED"
    shortlist.confirmed_at = datetime.utcnow()
    shortlist.confirmed_by = actor.id

    await write_audit_event(
        session,
        action="SHORTLIST_CONFIRM",
        entity_type="Shortlist",
        entity_id=str(shortlist.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        after={
            "advanced": [str(a) for a in advanced_ids],
            "waitlist": [str(w) for w in waitlist_ids],
            "excluded": [str(e) for e in excluded_ids],
            "isFinalStage": shortlist.is_final_stage,
            "finalistsPerSkill": (
                compute_finalists_per_skill(_stage_nodes(skill_stages)) if skill_stages else None
            ),
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return ShortlistConfirmOut(
        shortlistId=shortlist.id,
        state="CONFIRMED",
        advanced=advanced_ids,
        waitlist=waitlist_ids,
        excluded=excluded_ids,
        finalists=finalist_items if shortlist.is_final_stage else None,
        notified=notified,
    )
