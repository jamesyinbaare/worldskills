"""Institution nomination with per-skill limits and approve/reject workflow."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import (
    Competitor,
    InstitutionCompetitionMembership,
    Nomination,
    NominationStatus,
    NotificationOutbox,
    Skill,
    User,
    UserRole,
    Zone,
)
from app.schemas.nominations import NominationCreate
from app.services.audit import write_audit_event
from app.services.geography import resolve_zone_for_registration

_COUNTING_STATUSES = (NominationStatus.PENDING_REVIEW, NominationStatus.APPROVED)


def _nomination_to_dict(n: Nomination) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "competitionId": str(n.competition_id),
        "institutionId": str(n.institution_id),
        "skillId": str(n.skill_id),
        "competitorRef": n.competitor_ref,
        "competitorId": str(n.competitor_id) if n.competitor_id else None,
        "status": n.status.value if hasattr(n.status, "value") else n.status,
        "reason": n.reason,
    }


async def enqueue_notification(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID | None,
    recipient_role: str,
    template: str,
    payload: dict[str, Any],
    recipient_id: uuid.UUID | None = None,
) -> None:
    """Legacy enqueue used by nominations/registration — still writes outbox rows.

    Prefer `app.services.notifications.emit` for full multi-channel delivery (US-NOT-01).
    """
    session.add(
        NotificationOutbox(
            competition_id=competition_id,
            recipient_role=recipient_role,
            recipient_id=recipient_id,
            template=template,
            event_key=template,
            payload=payload,
            status="QUEUED",
        )
    )


def assert_can_nominate(user: User, institution_id: uuid.UUID) -> None:
    if is_admin_role(user.role):
        return
    if not has_capability(user.role, Capability.NOMINATE_COMPETITOR):
        raise AppError("FORBIDDEN", "Missing nominate capability", status_code=403)
    if user.institution_id != institution_id:
        raise AppError(
            "FORBIDDEN",
            "Institution may only nominate for its own account",
            status_code=403,
            fields=[FieldError("institutionId", "FORBIDDEN")],
        )


async def create_nomination(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: NominationCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Nomination:
    assert_can_nominate(actor, payload.institutionId)

    skill = await session.get(Skill, payload.skillId)
    if skill is None or skill.competition_id != competition_id:
        raise AppError(
            "SKILL_INACTIVE",
            "Skill not found in this competition",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillId", "SKILL_INACTIVE")],
        )
    if not skill.active:
        raise AppError(
            "SKILL_INACTIVE",
            "Skill is inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillId", "SKILL_INACTIVE")],
        )

    membership = (
        await session.execute(
            select(InstitutionCompetitionMembership).where(
                InstitutionCompetitionMembership.competition_id == competition_id,
                InstitutionCompetitionMembership.institution_id == payload.institutionId,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Institution is not linked to a zone for this competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("institutionId", "CONFIG_INCOMPLETE")],
        )

    # Lock skill row for atomic slot check (US-INS-01 race edge case)
    skill_locked = (
        await session.execute(
            select(Skill)
            .where(Skill.id == payload.skillId, Skill.competition_id == competition_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if skill_locked is None or not skill_locked.active:
        raise AppError(
            "SKILL_INACTIVE",
            "Skill not found in this competition",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillId", "SKILL_INACTIVE")],
        )
    if skill_locked.school_quota is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "School quota not configured for this skill",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "CONFIG_INCOMPLETE")],
        )

    used = (
        await session.execute(
            select(func.count())
            .select_from(Nomination)
            .where(
                Nomination.competition_id == competition_id,
                Nomination.institution_id == payload.institutionId,
                Nomination.skill_id == payload.skillId,
                Nomination.status.in_(_COUNTING_STATUSES),
            )
        )
    ).scalar_one()
    if int(used) >= int(skill_locked.school_quota):
        raise AppError(
            "NOMINATION_LIMIT_REACHED",
            "Institution nomination limit reached for this skill",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "NOMINATION_LIMIT_REACHED")],
        )

    region_id, zone_id = await resolve_zone_for_registration(
        session,
        competition_id,
        region_id=payload.regionId,
        institution_id=payload.institutionId,
    )

    competitor = Competitor(
        competition_id=competition_id,
        skill_id=payload.skillId,
        zone_id=zone_id,
        region_id=region_id,
        institution_id=payload.institutionId,
        ref_no=payload.competitorRef.strip(),
        status="PENDING_REVIEW",
    )
    session.add(competitor)
    await session.flush()

    nomination = Nomination(
        competition_id=competition_id,
        institution_id=payload.institutionId,
        skill_id=payload.skillId,
        competitor_ref=payload.competitorRef.strip(),
        competitor_id=competitor.id,
        status=NominationStatus.PENDING_REVIEW,
    )
    session.add(nomination)
    await session.flush()

    await enqueue_notification(
        session,
        competition_id=competition_id,
        recipient_role="ADMIN",
        template="NOMINATION_PENDING_REVIEW",
        payload={"nominationId": str(nomination.id), "institutionId": str(payload.institutionId)},
    )
    await write_audit_event(
        session,
        action="NOMINATION_CREATE",
        entity_type="Nomination",
        entity_id=str(nomination.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=_nomination_to_dict(nomination),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(nomination)
    return nomination


async def approve_nomination(
    session: AsyncSession,
    nomination_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Nomination:
    if not is_admin_role(actor.role):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)

    nomination = await session.get(Nomination, nomination_id)
    if nomination is None:
        raise AppError("NOMINATION_NOT_FOUND", "Nomination not found", status_code=404)
    if nomination.status != NominationStatus.PENDING_REVIEW:
        raise AppError(
            "INVALID_STATE",
            "Nomination is not pending review",
            status_code=status.HTTP_409_CONFLICT,
        )

    before = _nomination_to_dict(nomination)
    nomination.status = NominationStatus.APPROVED

    if nomination.competitor_id:
        competitor = await session.get(Competitor, nomination.competitor_id)
        if competitor is not None:
            competitor.status = "REGISTERED"

    await enqueue_notification(
        session,
        competition_id=nomination.competition_id,
        recipient_role=UserRole.INSTITUTION.value,
        recipient_id=nomination.institution_id,
        template="NOMINATION_APPROVED",
        payload={"nominationId": str(nomination.id)},
    )
    await enqueue_notification(
        session,
        competition_id=nomination.competition_id,
        recipient_role="ADMIN",
        recipient_id=actor.id,
        template="NOMINATION_APPROVED",
        payload={"nominationId": str(nomination.id)},
    )
    await write_audit_event(
        session,
        action="NOMINATION_APPROVE",
        entity_type="Nomination",
        entity_id=str(nomination.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=nomination.competition_id,
        before=before,
        after=_nomination_to_dict(nomination),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(nomination)
    return nomination


async def reject_nomination(
    session: AsyncSession,
    nomination_id: uuid.UUID,
    *,
    reason: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Nomination:
    if not is_admin_role(actor.role):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)

    if reason is None or not str(reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Rejection reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )

    nomination = await session.get(Nomination, nomination_id)
    if nomination is None:
        raise AppError("NOMINATION_NOT_FOUND", "Nomination not found", status_code=404)
    if nomination.status != NominationStatus.PENDING_REVIEW:
        raise AppError(
            "INVALID_STATE",
            "Nomination is not pending review",
            status_code=status.HTTP_409_CONFLICT,
        )

    before = _nomination_to_dict(nomination)
    nomination.status = NominationStatus.REJECTED
    nomination.reason = reason.strip()

    if nomination.competitor_id:
        competitor = await session.get(Competitor, nomination.competitor_id)
        if competitor is not None:
            competitor.status = "REJECTED"

    await enqueue_notification(
        session,
        competition_id=nomination.competition_id,
        recipient_role=UserRole.INSTITUTION.value,
        recipient_id=nomination.institution_id,
        template="NOMINATION_REJECTED",
        payload={"nominationId": str(nomination.id), "reason": nomination.reason},
    )
    await write_audit_event(
        session,
        action="NOMINATION_REJECT",
        entity_type="Nomination",
        entity_id=str(nomination.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=nomination.competition_id,
        before=before,
        after=_nomination_to_dict(nomination),
        reason=nomination.reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(nomination)
    return nomination
