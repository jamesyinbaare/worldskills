"""US-LCY-01 — withdraw, substitute, and promote from waitlist."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import (
    Competitor,
    Competition,
    LifecycleConfig,
    NotificationOutbox,
    Shortlist,
    ShortlistEntry,
    User,
    UserRole,
)
from app.schemas.lifecycle import ReplacementIn, SubstituteOut, WithdrawOut
from app.services.audit import write_audit_event
from app.services.eligibility import screen_competitor

_ACTIVE_STATUSES = {
    "DRAFT",
    "PENDING_REVIEW",
    "REGISTERED",
    "ACTIVE_IN_STAGE",
    "FINALIST",
    "ELIGIBLE",
}


def _cycle_local_now(cycle: Competition, *, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(cycle.time_zone)
    base = now or datetime.utcnow()
    if base.tzinfo is not None:
        return base.astimezone(tz).replace(tzinfo=None)
    # Treat naive now as UTC wall, convert via attaching UTC then to cycle TZ
    from datetime import timezone

    return base.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)


async def _load_lifecycle_config(session: AsyncSession, competition_id: uuid.UUID) -> LifecycleConfig:
    cfg = (
        await session.execute(select(LifecycleConfig).where(LifecycleConfig.competition_id == competition_id))
    ).scalar_one_or_none()
    if cfg is None or cfg.substitution_cutoff_at is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Substitution cut-off is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("substitutionCutoffAt", "CONFIG_INCOMPLETE")],
        )
    if not cfg.waitlist_order:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Waitlist order is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("waitlistOrder", "CONFIG_INCOMPLETE")],
        )
    return cfg


def _can_withdraw(actor: User, competitor: Competitor) -> None:
    if is_admin_role(actor.role):
        return
    if has_capability(actor.role, Capability.NOMINATE_COMPETITOR):
        if actor.institution_id and actor.institution_id == competitor.institution_id:
            return
        raise AppError(
            "FORBIDDEN",
            "Institution may only withdraw its own competitors",
            status_code=403,
            fields=[FieldError("institutionId", "FORBIDDEN")],
        )
    raise AppError("FORBIDDEN", "Not authorised to withdraw competitors", status_code=403)


def _can_substitute(actor: User, competitor: Competitor) -> None:
    if is_admin_role(actor.role):
        return
    if actor.role == UserRole.INSTITUTION and has_capability(actor.role, Capability.NOMINATE_COMPETITOR):
        if actor.institution_id and actor.institution_id == competitor.institution_id:
            return
        raise AppError(
            "FORBIDDEN",
            "Institution may only substitute its own competitors",
            status_code=403,
            fields=[FieldError("institutionId", "FORBIDDEN")],
        )
    raise AppError("FORBIDDEN", "Not authorised to substitute competitors", status_code=403)


async def _find_advanced_entry(
    session: AsyncSession, competitor_id: uuid.UUID
) -> tuple[ShortlistEntry, Shortlist] | None:
    row = (
        await session.execute(
            select(ShortlistEntry, Shortlist)
            .join(Shortlist, ShortlistEntry.shortlist_id == Shortlist.id)
            .where(
                ShortlistEntry.competitor_id == competitor_id,
                ShortlistEntry.outcome == "ADVANCE",
                ShortlistEntry.advanced.is_(True),
                Shortlist.state == "CONFIRMED",
            )
            .order_by(Shortlist.confirmed_at.desc())
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


async def _promote_waitlist(
    session: AsyncSession,
    *,
    vacated: ShortlistEntry,
    shortlist: Shortlist,
    cycle: Competition,
    cfg: LifecycleConfig | None,
    actor: User,
) -> Competitor | None:
    """Promote next eligible WAITLIST entry in the same zone. Returns promoted competitor or None."""
    if cfg is None:
        # Promotion needs waitlist order config — fail closed only when config entirely missing
        # If withdraw without config but also no waitlist, just skip. If waitlist exists without config,
        # load will have been called when shortlist slot vacated — require config.
        try:
            cfg = await _load_lifecycle_config(session, cycle.id)
        except AppError:
            # No waitlist config: do not promote (fail closed = no silent ordering assumption)
            return None

    order = (cfg.waitlist_order or "").upper()
    if order != "RANK":
        raise AppError(
            "CONFIG_INCOMPLETE",
            f"Unsupported waitlist order '{cfg.waitlist_order}'",
            status_code=409,
            fields=[FieldError("waitlistOrder", "CONFIG_INCOMPLETE")],
        )

    candidates = (
        await session.execute(
            select(ShortlistEntry)
            .where(
                ShortlistEntry.shortlist_id == shortlist.id,
                ShortlistEntry.zone_id == vacated.zone_id,
                ShortlistEntry.outcome == "WAITLIST",
            )
            .order_by(ShortlistEntry.rank.asc())
        )
    ).scalars().all()

    for entry in candidates:
        competitor = await session.get(Competitor, entry.competitor_id)
        if competitor is None:
            continue
        if competitor.status == "WITHDRAWN":
            continue
        if competitor.eligibility_status not in (None, "ELIGIBLE", "OPEN_CATEGORY"):
            continue

        # Promote
        entry.outcome = "ADVANCE"
        entry.advanced = True
        entry.reason = "WAITLIST_PROMOTED"

        flags = [f for f in (competitor.flags or []) if f != "WAITLIST"]
        competitor.flags = flags
        if shortlist.is_final_stage:
            competitor.status = "FINALIST"
        else:
            competitor.status = "ACTIVE_IN_STAGE"

        session.add(
            NotificationOutbox(
                competition_id=cycle.id,
                recipient_role="COMPETITOR",
                recipient_id=competitor.id,
                template="WAITLIST_PROMOTED",
                event_key="WAITLIST_PROMOTED",
                payload={
                    "competitorId": str(competitor.id),
                    "shortlistId": str(shortlist.id),
                    "stageId": str(shortlist.stage_id),
                    "vacatedCompetitorId": str(vacated.competitor_id),
                },
                status="QUEUED",
            )
        )
        await write_audit_event(
            session,
            action="WAITLIST_PROMOTE",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=cycle.id,
            after={
                "shortlistId": str(shortlist.id),
                "from": "WAITLIST",
                "to": "ADVANCE",
                "vacatedCompetitorId": str(vacated.competitor_id),
            },
        )
        return competitor

    return None


async def withdraw_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    reason: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
    promote: bool = True,
) -> WithdrawOut:
    if reason is None or not str(reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Withdrawal reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )
    reason = str(reason).strip()

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    _can_withdraw(actor, competitor)

    if competitor.status == "WITHDRAWN":
        raise AppError(
            "ALREADY_WITHDRAWN",
            "Competitor is already withdrawn",
            status_code=409,
            fields=[FieldError("status", "ALREADY_WITHDRAWN")],
        )
    if competitor.status not in _ACTIVE_STATUSES and competitor.status != "INELIGIBLE":
        # Allow INELIGIBLE withdraw too; reject DISQUALIFIED only if already terminal oddly
        if competitor.status == "DISQUALIFIED":
            raise AppError(
                "INVALID_STATE",
                "Cannot withdraw a disqualified competitor",
                status_code=409,
                fields=[FieldError("status", "INVALID_STATE")],
            )

    cycle = await session.get(Competition, competitor.competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    before = {"status": competitor.status}
    competitor.status = "WITHDRAWN"
    competitor.withdrawn_at = datetime.utcnow()
    competitor.withdrawn_reason = reason
    competitor.withdrawn_by = actor.id

    promoted_id: uuid.UUID | None = None
    vacated = await _find_advanced_entry(session, competitor_id)
    if vacated and promote:
        entry, shortlist = vacated
        entry.advanced = False
        # Keep outcome ADVANCE historically? Spec: slot frees — mark vacated on entry
        entry.reason = "WITHDRAWN"
        cfg = (
            await session.execute(
                select(LifecycleConfig).where(LifecycleConfig.competition_id == cycle.id)
            )
        ).scalar_one_or_none()
        if cfg is None or not cfg.waitlist_order:
            # Slot freed but cannot order waitlist — fail closed: raise so promotion is explicit
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Waitlist order is not configured; cannot promote",
                status_code=409,
                fields=[FieldError("waitlistOrder", "CONFIG_INCOMPLETE")],
            )
        promoted = await _promote_waitlist(
            session,
            vacated=entry,
            shortlist=shortlist,
            cycle=cycle,
            cfg=cfg,
            actor=actor,
        )
        if promoted:
            promoted_id = promoted.id

    await write_audit_event(
        session,
        action="COMPETITOR_WITHDRAW",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competitor.competition_id,
        before=before,
        after={
            "status": "WITHDRAWN",
            "promotedCompetitorId": str(promoted_id) if promoted_id else None,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return WithdrawOut(
        competitorId=competitor.id,
        status="WITHDRAWN",
        promotedCompetitorId=promoted_id,
    )


async def substitute_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    replacement: ReplacementIn,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> SubstituteOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    _can_substitute(actor, competitor)

    if competitor.status == "WITHDRAWN":
        raise AppError(
            "ALREADY_WITHDRAWN",
            "Cannot substitute a withdrawn competitor",
            status_code=409,
            fields=[FieldError("status", "ALREADY_WITHDRAWN")],
        )

    cycle = await session.get(Competition, competitor.competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    cfg = await _load_lifecycle_config(session, cycle.id)
    local_now = _cycle_local_now(cycle, now=now)
    if local_now > cfg.substitution_cutoff_at:
        raise AppError(
            "SUBSTITUTION_CLOSED",
            "Substitution cut-off has passed",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("substitutionCutoffAt", "SUBSTITUTION_CLOSED")],
        )

    # Create replacement in same skill / zone / institution
    new_comp = Competitor(
        competition_id=competitor.competition_id,
        skill_id=competitor.skill_id,
        zone_id=competitor.zone_id,
        institution_id=competitor.institution_id,
        ref_no=replacement.refNo,
        status="PENDING_REVIEW",
        given_names=replacement.givenNames,
        family_name=replacement.familyName,
        date_of_birth=replacement.dateOfBirth,
        nationality=replacement.nationality,
        enrolment_attested=replacement.enrolmentAttested,
        email=replacement.email,
        mobile=replacement.mobile,
        flags=[],
        substitutes_id=competitor.id,
    )
    session.add(new_comp)
    await session.flush()

    screen = await screen_competitor(
        session,
        new_comp.id,
        actor=actor,
        ip=ip,
        user_agent=user_agent,
        commit=False,
    )

    if not screen.eligible:
        failed_rules = list(screen.failedRules)
        await session.delete(new_comp)
        await write_audit_event(
            session,
            action="COMPETITOR_SUBSTITUTE_REFUSED",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=competitor.competition_id,
            after={"failedRules": failed_rules, "reason": "ELIGIBILITY_FAILED"},
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "ELIGIBILITY_FAILED",
            "Replacement failed eligibility screening",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("replacement", "ELIGIBILITY_FAILED")],
        )

    # Transfer shortlist advance slot if any (no waitlist promote)
    vacated = await _find_advanced_entry(session, competitor.id)
    prior_status = competitor.status

    competitor.status = "WITHDRAWN"
    competitor.withdrawn_at = datetime.utcnow()
    competitor.withdrawn_reason = f"Substituted by {new_comp.ref_no}"
    competitor.withdrawn_by = actor.id
    competitor.substituted_by_id = new_comp.id

    new_comp.status = prior_status if prior_status in _ACTIVE_STATUSES else "ACTIVE_IN_STAGE"
    if new_comp.status in {"DRAFT", "PENDING_REVIEW", "REGISTERED"}:
        new_comp.status = "ACTIVE_IN_STAGE"

    if vacated:
        old_entry, shortlist = vacated
        old_entry.advanced = False
        old_entry.reason = "SUBSTITUTED"
        session.add(
            ShortlistEntry(
                shortlist_id=shortlist.id,
                competitor_id=new_comp.id,
                zone_id=old_entry.zone_id,
                score=old_entry.score,
                rank=old_entry.rank,
                outcome="ADVANCE",
                advanced=True,
                reason="SUBSTITUTION",
            )
        )

    await write_audit_event(
        session,
        action="COMPETITOR_SUBSTITUTE",
        entity_type="Competitor",
        entity_id=str(new_comp.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competitor.competition_id,
        before={"withdrawnCompetitorId": str(competitor.id), "status": prior_status},
        after={
            "replacementCompetitorId": str(new_comp.id),
            "eligible": True,
            "status": new_comp.status,
        },
        reason="Substitution",
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return SubstituteOut(
        withdrawnCompetitorId=competitor.id,
        replacementCompetitorId=new_comp.id,
        eligible=True,
        status=new_comp.status,
        failedRules=[],
    )
