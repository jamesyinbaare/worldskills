"""US-APP-01 — lodge/rule appeals, disqualify, tie-break config resolution."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, check_conflict_of_interest, has_capability, is_admin_role
from app.models import (
    AppealCase,
    AppealsConfig,
    Competitor,
    Cycle,
    NotificationOutbox,
    Shortlist,
    ShortlistEntry,
    Stage,
    Submission,
    User,
    UserRole,
)
from app.schemas.appeals import AppealOut, DisqualifyOut
from app.services.audit import write_audit_event
from app.services.lifecycle import _find_advanced_entry, _promote_waitlist
from app.services.pathway_engine import Candidate, has_score_tie_at_quota_boundary, rank_for_shortlist

_VALID_OUTCOMES = {"UPHELD", "DISMISSED"}
_VALID_REMEDIES = {"RE_SCORE", "RE_RANK", "REINSTATE"}


def _cycle_local_now(cycle: Cycle, *, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(cycle.time_zone)
    base = now or datetime.utcnow()
    if base.tzinfo is not None:
        return base.astimezone(tz).replace(tzinfo=None)
    from datetime import timezone

    return base.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)


async def load_appeals_config(session: AsyncSession, cycle_id: uuid.UUID) -> AppealsConfig:
    cfg = (
        await session.execute(select(AppealsConfig).where(AppealsConfig.cycle_id == cycle_id))
    ).scalar_one_or_none()
    if cfg is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Appeals configuration is not set for this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("appealsConfig", "CONFIG_INCOMPLETE")],
        )
    if not cfg.tie_break_rules:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Tie-break rules are not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("tieBreakRules", "CONFIG_INCOMPLETE")],
        )
    if not cfg.dq_reasons:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Disqualification reasons are not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("dqReasons", "CONFIG_INCOMPLETE")],
        )
    return cfg


async def require_tie_break_rules_if_needed(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    candidates: list[Candidate],
    quota_by_zone: dict[str, int],
    min_score: int | None,
) -> list[str] | None:
    """Return configured tie-break rules; fail closed when a boundary tie exists without config."""
    tied = has_score_tie_at_quota_boundary(
        candidates, quota_by_zone=quota_by_zone, min_score=min_score
    )
    cfg = (
        await session.execute(select(AppealsConfig).where(AppealsConfig.cycle_id == cycle_id))
    ).scalar_one_or_none()
    if tied:
        if cfg is None or not cfg.tie_break_rules:
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Tie-break rules required when competitors are tied at the quota boundary",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("tieBreakRules", "CONFIG_INCOMPLETE")],
            )
        return list(cfg.tie_break_rules)
    if cfg and cfg.tie_break_rules:
        return list(cfg.tie_break_rules)
    return None


def _case_out(case: AppealCase) -> AppealOut:
    return AppealOut(
        appealId=case.id,
        cycleId=case.cycle_id,
        competitorId=case.competitor_id,
        stageId=case.stage_id,
        state=case.state,
        reason=case.reason,
        officerId=case.officer_id,
        rulingOutcome=case.ruling_outcome,
        rulingReason=case.ruling_reason,
        remedy=case.remedy,
    )


def _can_lodge(actor: User, competitor: Competitor) -> None:
    if is_admin_role(actor.role):
        return
    if actor.role == UserRole.INSTITUTION and has_capability(actor.role, Capability.NOMINATE_COMPETITOR):
        if actor.institution_id and actor.institution_id == competitor.institution_id:
            return
        raise AppError(
            "FORBIDDEN",
            "Institution may only appeal for its own competitors",
            status_code=403,
            fields=[FieldError("institutionId", "FORBIDDEN")],
        )
    if actor.role == UserRole.COMPETITOR:
        # Competitor users lodge against the competitor they represent — identity link not yet
        # modelled beyond role; allow any COMPETITOR role within cycle lodge for MVP when they
        # pass competitorId they "own". Prefer linking via email match when available.
        return
    raise AppError("FORBIDDEN", "Not authorised to lodge an appeal", status_code=403)


def _require_rule_capability(actor: User) -> None:
    if not has_capability(actor.role, Capability.RULE_ON_APPEAL):
        raise AppError(
            "FORBIDDEN",
            "Appeals Officer or Admin required",
            status_code=403,
            fields=[FieldError("role", "FORBIDDEN")],
        )


async def lodge_appeal(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    competitor_id: uuid.UUID,
    stage_id: uuid.UUID,
    reason: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> AppealOut:
    if reason is None or not str(reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Appeal reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )
    reason = str(reason).strip()

    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None or competitor.cycle_id != cycle_id:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found in cycle", status_code=404)

    stage = await session.get(Stage, stage_id)
    if stage is None or stage.cycle_id != cycle_id:
        raise AppError("STAGE_NOT_FOUND", "Stage not found in cycle", status_code=404)

    _can_lodge(actor, competitor)

    cfg = await load_appeals_config(session, cycle_id)
    local_now = _cycle_local_now(cycle, now=now)
    if local_now < cfg.appeal_window_opens_at or local_now > cfg.appeal_window_closes_at:
        raise AppError(
            "APPEAL_WINDOW_CLOSED",
            "Appeal window is closed",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("appealWindow", "APPEAL_WINDOW_CLOSED")],
        )

    case = AppealCase(
        cycle_id=cycle_id,
        competitor_id=competitor_id,
        stage_id=stage_id,
        reason=reason,
        state="SUBMITTED",
        lodged_by=actor.id,
        submitted_at=datetime.utcnow(),
    )
    session.add(case)
    await session.flush()

    await write_audit_event(
        session,
        action="APPEAL_LODGED",
        entity_type="AppealCase",
        entity_id=str(case.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        after={
            "state": "SUBMITTED",
            "competitorId": str(competitor_id),
            "stageId": str(stage_id),
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return _case_out(case)


async def assign_appeal(
    session: AsyncSession,
    appeal_id: uuid.UUID,
    *,
    officer_id: uuid.UUID,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AppealOut:
    _require_rule_capability(actor)

    case = await session.get(AppealCase, appeal_id)
    if case is None:
        raise AppError("APPEAL_NOT_FOUND", "Appeal case not found", status_code=404)
    if case.state not in {"SUBMITTED", "UNDER_REVIEW"}:
        raise AppError(
            "INVALID_STATE",
            f"Cannot assign appeal in state {case.state}",
            status_code=409,
            fields=[FieldError("state", "INVALID_STATE")],
        )

    officer = await session.get(User, officer_id)
    if officer is None or not officer.is_active:
        raise AppError("OFFICER_NOT_FOUND", "Officer not found", status_code=404)
    if not has_capability(officer.role, Capability.RULE_ON_APPEAL):
        raise AppError(
            "FORBIDDEN",
            "Assignee must have appeals ruling capability",
            status_code=403,
            fields=[FieldError("officerId", "FORBIDDEN")],
        )

    competitor = await session.get(Competitor, case.competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    if check_conflict_of_interest(
        expert_institution_id=str(officer.institution_id) if officer.institution_id else None,
        competitor_institution_id=str(competitor.institution_id) if competitor.institution_id else None,
    ):
        raise AppError(
            "OFFICER_CONFLICT",
            "Officer has a conflict of interest with this case",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("officerId", "OFFICER_CONFLICT")],
        )

    before = {"state": case.state, "officerId": str(case.officer_id) if case.officer_id else None}
    case.officer_id = officer_id
    case.state = "UNDER_REVIEW"
    case.assigned_at = datetime.utcnow()

    await write_audit_event(
        session,
        action="APPEAL_ASSIGNED",
        entity_type="AppealCase",
        entity_id=str(case.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=case.cycle_id,
        before=before,
        after={"state": "UNDER_REVIEW", "officerId": str(officer_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return _case_out(case)


async def _apply_remedy(
    session: AsyncSession,
    case: AppealCase,
    *,
    remedy: str,
    actor: User,
) -> None:
    competitor = await session.get(Competitor, case.competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    if remedy == "REINSTATE":
        competitor.status = "ACTIVE_IN_STAGE"
        flags = [f for f in (competitor.flags or []) if f != "WAITLIST"]
        competitor.flags = flags
        # Promote to ADVANCE on latest confirmed shortlist for this stage if present
        shortlist = (
            await session.execute(
                select(Shortlist)
                .where(
                    Shortlist.cycle_id == case.cycle_id,
                    Shortlist.stage_id == case.stage_id,
                    Shortlist.state == "CONFIRMED",
                )
                .order_by(Shortlist.confirmed_at.desc())
            )
        ).scalars().first()
        if shortlist:
            entry = (
                await session.execute(
                    select(ShortlistEntry).where(
                        ShortlistEntry.shortlist_id == shortlist.id,
                        ShortlistEntry.competitor_id == competitor.id,
                    )
                )
            ).scalar_one_or_none()
            if entry:
                entry.outcome = "ADVANCE"
                entry.advanced = True
                entry.reason = "APPEAL_REINSTATE"

    elif remedy == "RE_RANK":
        await _rerank_stage(session, case.cycle_id, case.stage_id)

    elif remedy == "RE_SCORE":
        subs = (
            await session.execute(
                select(Submission).where(
                    Submission.competitor_id == competitor.id,
                    Submission.stage_id == case.stage_id,
                )
            )
        ).scalars().all()
        for sub in subs:
            sub.score_total = None
            if sub.state in {"ACCEPTED", "LATE"}:
                sub.state = "ACCEPTED"  # stay accepted but unscored for re-mark
        session.add(
            NotificationOutbox(
                cycle_id=case.cycle_id,
                recipient_role="EXPERT",
                recipient_id=None,
                template="APPEAL_RE_SCORE",
                event_key="APPEAL_RE_SCORE",
                payload={
                    "appealId": str(case.id),
                    "competitorId": str(competitor.id),
                    "stageId": str(case.stage_id),
                },
                status="QUEUED",
            )
        )


async def _rerank_stage(session: AsyncSession, cycle_id: uuid.UUID, stage_id: uuid.UUID) -> None:
    stage = await session.get(Stage, stage_id)
    if stage is None:
        return
    cfg = await load_appeals_config(session, cycle_id)
    quota_by_zone = {str(k): int(v) for k, v in (stage.quota_by_zone or {}).items()}
    subs = (
        await session.execute(
            select(Submission).where(
                Submission.cycle_id == cycle_id,
                Submission.stage_id == stage_id,
                Submission.state.in_(["ACCEPTED", "LATE"]),
                Submission.score_total.is_not(None),
            )
        )
    ).scalars().all()
    candidates: list[Candidate] = []
    for sub in subs:
        comp = await session.get(Competitor, sub.competitor_id)
        if comp is None or comp.status == "DISQUALIFIED":
            continue
        candidates.append(
            Candidate(
                competitor_id=str(comp.id),
                zone_id=str(comp.zone_id),
                score=float(sub.score_total or 0),
                date_of_birth=comp.date_of_birth,
                ref_no=comp.ref_no,
            )
        )
    if not quota_by_zone and stage.quota is not None:
        zones = {c.zone_id for c in candidates}
        quota_by_zone = {z: int(stage.quota) for z in zones}

    ranked = rank_for_shortlist(
        candidates,
        quota_by_zone=quota_by_zone,
        min_score=stage.min_score,
        tie_break_rules=list(cfg.tie_break_rules),
    )

    # Update confirmed shortlist entries if present
    shortlist = (
        await session.execute(
            select(Shortlist)
            .where(
                Shortlist.cycle_id == cycle_id,
                Shortlist.stage_id == stage_id,
                Shortlist.state == "CONFIRMED",
            )
            .order_by(Shortlist.confirmed_at.desc())
        )
    ).scalars().first()
    if shortlist is None:
        return
    for entry_row in ranked:
        cid = uuid.UUID(entry_row.competitor_id)
        entry = (
            await session.execute(
                select(ShortlistEntry).where(
                    ShortlistEntry.shortlist_id == shortlist.id,
                    ShortlistEntry.competitor_id == cid,
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            session.add(
                ShortlistEntry(
                    shortlist_id=shortlist.id,
                    competitor_id=cid,
                    zone_id=uuid.UUID(entry_row.zone_id),
                    score=int(entry_row.score),
                    rank=entry_row.rank,
                    outcome=entry_row.outcome,
                    advanced=entry_row.outcome == "ADVANCE",
                    reason="APPEAL_RE_RANK",
                )
            )
        else:
            entry.score = int(entry_row.score)
            entry.rank = entry_row.rank
            entry.outcome = entry_row.outcome
            entry.advanced = entry_row.outcome == "ADVANCE"
            entry.reason = "APPEAL_RE_RANK"


async def rule_appeal(
    session: AsyncSession,
    appeal_id: uuid.UUID,
    *,
    outcome: str,
    reason: str | None,
    remedy: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AppealOut:
    _require_rule_capability(actor)

    case = await session.get(AppealCase, appeal_id)
    if case is None:
        raise AppError("APPEAL_NOT_FOUND", "Appeal case not found", status_code=404)
    if case.state != "UNDER_REVIEW":
        raise AppError(
            "INVALID_STATE",
            f"Cannot rule on appeal in state {case.state}",
            status_code=409,
            fields=[FieldError("state", "INVALID_STATE")],
        )

    # Assigned officer must rule (admin may also rule)
    if (
        case.officer_id
        and case.officer_id != actor.id
        and not is_admin_role(actor.role)
    ):
        raise AppError(
            "FORBIDDEN",
            "Only the assigned officer or Admin may rule",
            status_code=403,
            fields=[FieldError("officerId", "FORBIDDEN")],
        )

    outcome_u = (outcome or "").upper()
    if outcome_u not in _VALID_OUTCOMES:
        raise AppError(
            "INVALID_OUTCOME",
            "Outcome must be UPHELD or DISMISSED",
            status_code=422,
            fields=[FieldError("outcome", "INVALID_OUTCOME")],
        )
    if reason is None or not str(reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Ruling reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )
    reason = str(reason).strip()

    remedy_u: str | None = None
    if outcome_u == "UPHELD":
        if remedy is None or not str(remedy).strip():
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Remedy is required when upholding an appeal",
                status_code=422,
                fields=[FieldError("remedy", "REASON_REQUIRED")],
            )
        remedy_u = str(remedy).strip().upper()
        if remedy_u not in _VALID_REMEDIES:
            raise AppError(
                "INVALID_REMEDY",
                "Remedy must be RE_SCORE, RE_RANK, or REINSTATE",
                status_code=422,
                fields=[FieldError("remedy", "INVALID_REMEDY")],
            )

    before = {"state": case.state}
    case.ruling_outcome = outcome_u
    case.ruling_reason = reason
    case.remedy = remedy_u
    case.ruled_at = datetime.utcnow()
    case.state = outcome_u

    if outcome_u == "UPHELD" and remedy_u:
        await _apply_remedy(session, case, remedy=remedy_u, actor=actor)
        case.state = "REMEDIED"

    session.add(
        NotificationOutbox(
            cycle_id=case.cycle_id,
            recipient_role="COMPETITOR",
            recipient_id=case.competitor_id,
            template="APPEAL_OUTCOME",
            event_key="APPEAL_OUTCOME",
            payload={
                "appealId": str(case.id),
                "outcome": outcome_u,
                "remedy": remedy_u,
                "reason": reason,
            },
            status="QUEUED",
        )
    )

    await write_audit_event(
        session,
        action="APPEAL_RULED",
        entity_type="AppealCase",
        entity_id=str(case.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=case.cycle_id,
        before=before,
        after={
            "state": case.state,
            "outcome": outcome_u,
            "remedy": remedy_u,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return _case_out(case)


async def disqualify_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    reason: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> DisqualifyOut:
    _require_rule_capability(actor)

    if reason is None or not str(reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Disqualification reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )
    reason = str(reason).strip()

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    cfg = await load_appeals_config(session, competitor.cycle_id)
    allowed = {str(r).upper() for r in (cfg.dq_reasons or [])}
    if reason.upper() not in allowed:
        raise AppError(
            "INVALID_DQ_REASON",
            "Disqualification reason is not in the configured set",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "INVALID_DQ_REASON")],
        )
    reason = reason.upper()

    if competitor.status == "DISQUALIFIED":
        raise AppError(
            "ALREADY_DISQUALIFIED",
            "Competitor is already disqualified",
            status_code=409,
            fields=[FieldError("status", "ALREADY_DISQUALIFIED")],
        )

    cycle = await session.get(Cycle, competitor.cycle_id)
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)

    before = {"status": competitor.status}
    competitor.status = "DISQUALIFIED"
    competitor.dq_reason = reason
    competitor.dq_at = datetime.utcnow()
    competitor.dq_by = actor.id

    promoted_id: uuid.UUID | None = None
    vacated = await _find_advanced_entry(session, competitor_id)
    if vacated:
        entry, shortlist = vacated
        entry.advanced = False
        entry.outcome = "EXCLUDED"
        entry.reason = "DISQUALIFIED"
        from app.models import LifecycleConfig

        life_cfg = (
            await session.execute(
                select(LifecycleConfig).where(LifecycleConfig.cycle_id == cycle.id)
            )
        ).scalar_one_or_none()
        if life_cfg and life_cfg.waitlist_order:
            promoted = await _promote_waitlist(
                session,
                vacated=entry,
                shortlist=shortlist,
                cycle=cycle,
                cfg=life_cfg,
                actor=actor,
            )
            if promoted:
                promoted_id = promoted.id

    await write_audit_event(
        session,
        action="COMPETITOR_DISQUALIFY",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=competitor.cycle_id,
        before=before,
        after={
            "status": "DISQUALIFIED",
            "reason": reason,
            "promotedCompetitorId": str(promoted_id) if promoted_id else None,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return DisqualifyOut(
        competitorId=competitor.id,
        status="DISQUALIFIED",
        reason=reason,
        promotedCompetitorId=promoted_id,
    )
