"""Competitor + coach SMS for exercise availability and submission receipts."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.errors import AppError, FieldError
from app.models import (
    Competition,
    Competitor,
    Exercise,
    NotificationOutbox,
    Skill,
    Stage,
    Submission,
    User,
    Zone,
)
from app.services.sms.delivery_log import (
    MESSAGE_TYPE_EXERCISE_AVAILABLE,
    MESSAGE_TYPE_REGISTRATION_CONFIRMATION,
    MESSAGE_TYPE_SKILL_BROADCAST,
    MESSAGE_TYPE_SUBMISSION_RECEIVED,
    RECIPIENT_COACH,
    RECIPIENT_COMPETITOR,
    send_and_log_sms,
)
from app.services.stages import assert_stage_available

logger = logging.getLogger(__name__)

_ELIGIBLE_STATUSES = {
    "REGISTERED",
    "ACTIVE_IN_STAGE",
    "FINALIST",
    "CONSENT_PENDING",
    "PENDING_REVIEW",
}

SKILL_SMS_TEMPLATES: dict[str, str] = {
    "exercise_reminder": (
        "Reminder for {{competitorName}} — {{skillName}} exercise details "
        "are in the competitor portal. {{portalUrl}}"
    ),
    "schedule_update": (
        "Schedule update for {{skillName}}"
        "{{zoneLabel}}. Check the portal for details. {{portalUrl}}"
    ),
    "general_notice": (
        "Notice for {{skillName}} competitors"
        "{{zoneLabel}}. {{customNote}} {{portalUrl}}"
    ),
}


@dataclass
class NotifySummary:
    competitors_considered: int = 0
    competitor_sent: int = 0
    coach_sent: int = 0
    failed: int = 0
    skipped_not_ready: bool = False
    skipped_already_notified: bool = False


def _render(template: str, context: dict[str, Any]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value if value is not None else ""))
    return result


def _competitor_phone(competitor: Competitor) -> str:
    return (competitor.mobile or competitor.whatsapp or "").strip()


def _coach_phone(competitor: Competitor) -> str:
    coach = competitor.coach if isinstance(competitor.coach, dict) else {}
    return str(coach.get("contactNumber") or coach.get("whatsapp") or "").strip()


def _coach_name(competitor: Competitor) -> str:
    coach = competitor.coach if isinstance(competitor.coach, dict) else {}
    first = str(coach.get("firstName") or "").strip()
    surname = str(coach.get("surname") or "").strip()
    return f"{first} {surname}".strip() or "Coach"


def _competitor_display_name(competitor: Competitor) -> str:
    given = (competitor.given_names or "").strip()
    family = (competitor.family_name or "").strip()
    return f"{given} {family}".strip() or "Competitor"


def _portal_url(competition_id: uuid.UUID, stage_id: uuid.UUID) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/competitor/competitions/{competition_id}/stages/{stage_id}/submit"


def _exercise_available_message(context: dict[str, Any], *, for_coach: bool) -> str:
    if for_coach:
        template = (
            "Exercise for {{competitorName}} ({{skillName}} / {{stageName}}) "
            "is now available. Portal: {{portalUrl}}"
        )
    else:
        template = (
            "{{skillName}} — {{stageName}} exercise is available. "
            "Submit via {{portalUrl}}"
        )
    return _render(template, context)


def _submission_received_message(context: dict[str, Any], *, for_coach: bool) -> str:
    if for_coach:
        template = (
            "{{competitorName}} submitted {{skillName}} / {{stageName}}. "
            "Receipt {{receipt}} ({{state}})."
        )
    else:
        template = (
            "Submission received for {{skillName}} / {{stageName}}. "
            "Receipt {{receipt}} ({{state}})."
        )
    return _render(template, context)


def _registration_confirmation_message(context: dict[str, Any]) -> str:
    template = (
        "Registration received for {{competitionName}}. "
        "Ref {{competitorRef}}."
    )
    return _render(template, context)


async def notify_registration_received(
    session: AsyncSession,
    *,
    competitor: Competitor,
    competition_id: uuid.UUID,
    competitor_ref: str,
    trigger: str = "registration_create",
    commit: bool = False,
) -> NotifySummary:
    """Send REGISTRATION_CONFIRMATION SMS to the competitor (best-effort)."""
    summary = NotifySummary()
    competition = await session.get(Competition, competition_id)
    if competition is None:
        return summary

    summary.competitors_considered = 1
    context = {
        "competitionName": competition.name,
        "competitorName": _competitor_display_name(competitor),
        "competitorRef": competitor_ref,
        "status": competitor.status or "",
    }

    dedupe = f"REGISTRATION_CONFIRMATION:{competitor.id}"
    message = _registration_confirmation_message(context)
    result, _ = await send_and_log_sms(
        session,
        phone=_competitor_phone(competitor),
        message=message,
        message_type=MESSAGE_TYPE_REGISTRATION_CONFIRMATION,
        trigger=trigger,
        recipient_role=RECIPIENT_COMPETITOR,
        competitor_id=competitor.id,
        user_id=competitor.user_id,
        competition_id=competition_id,
        dedupe_key=dedupe,
    )
    if result.sent and result.error != "deduped":
        summary.competitor_sent += 1
        await _enqueue_outbox(
            session,
            event_key=MESSAGE_TYPE_REGISTRATION_CONFIRMATION,
            competition_id=competition_id,
            recipient_role="COMPETITOR",
            recipient_id=competitor.id,
            body=message,
            dedupe_key=dedupe,
            payload=context,
        )
    elif not result.sent:
        summary.failed += 1

    if commit:
        await session.commit()
    return summary


def is_stage_window_open(stage: Stage, *, now: datetime | None = None) -> bool:
    try:
        assert_stage_available(stage, now=now)
        return True
    except AppError:
        return False


async def _enqueue_outbox(
    session: AsyncSession,
    *,
    event_key: str,
    competition_id: uuid.UUID,
    recipient_role: str,
    recipient_id: uuid.UUID | None,
    body: str,
    dedupe_key: str | None,
    payload: dict[str, Any],
) -> None:
    session.add(
        NotificationOutbox(
            competition_id=competition_id,
            recipient_role=recipient_role,
            recipient_id=recipient_id,
            template=event_key,
            event_key=event_key,
            channel="SMS",
            language="en",
            rendered_subject=event_key,
            rendered_body=body,
            status="SENT",
            dedupe_key=dedupe_key,
            payload=payload,
        )
    )


async def _load_stage_context(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> tuple[Competition, Stage, Exercise, Skill | None] | None:
    stage = await session.get(Stage, stage_id)
    if stage is None or stage.competition_id != competition_id:
        return None
    competition = await session.get(Competition, competition_id)
    if competition is None:
        return None
    exercise = (
        await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
    ).scalar_one_or_none()
    if exercise is None:
        return None
    skill = await session.get(Skill, stage.skill_id) if stage.skill_id else None
    return competition, stage, exercise, skill


async def notify_exercise_available(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    trigger: str,
    actor: User | None = None,
    force: bool = False,
    commit: bool = True,
) -> NotifySummary:
    """Fan-out EXERCISE_AVAILABLE SMS to eligible competitors and coaches.

    Only sends when exercise is PUBLISHED and the stage window is open.
    Automatic sends (force=False) skip when availability_notified_at is set and
    dedupe per competitor/coach. Admin notify (force=True) always re-sends.
    """
    summary = NotifySummary()
    loaded = await _load_stage_context(session, competition_id, stage_id)
    if loaded is None:
        summary.skipped_not_ready = True
        return summary
    competition, stage, exercise, skill = loaded

    if exercise.status != "PUBLISHED":
        summary.skipped_not_ready = True
        return summary
    if not is_stage_window_open(stage):
        summary.skipped_not_ready = True
        return summary

    if exercise.availability_notified_at is not None and not force:
        summary.skipped_already_notified = True
        return summary

    if stage.skill_id is None:
        summary.skipped_not_ready = True
        return summary

    competitors = list(
        (
            await session.execute(
                select(Competitor).where(
                    Competitor.competition_id == competition_id,
                    Competitor.skill_id == stage.skill_id,
                    Competitor.status.in_(sorted(_ELIGIBLE_STATUSES)),
                )
            )
        )
        .scalars()
        .all()
    )
    summary.competitors_considered = len(competitors)

    context_base = {
        "competitionName": competition.name,
        "skillName": skill.name if skill else "Skill",
        "stageName": stage.name,
        "opensAt": stage.opens_at.isoformat() if stage.opens_at else "now",
        "closesAt": stage.closes_at.isoformat() if stage.closes_at else "",
        "portalUrl": _portal_url(competition_id, stage_id),
    }

    actor_id = actor.id if actor else None
    # Stable keys for auto-send; omit on force so admins can notify again.
    for competitor in competitors:
        context = {
            **context_base,
            "competitorName": _competitor_display_name(competitor),
            "coachName": _coach_name(competitor),
        }
        # Competitor
        c_dedupe = (
            None
            if force
            else f"EXERCISE_AVAILABLE:{competitor.id}:{stage_id}:competitor"
        )
        c_msg = _exercise_available_message(context, for_coach=False)
        c_result, _ = await send_and_log_sms(
            session,
            phone=_competitor_phone(competitor),
            message=c_msg,
            message_type=MESSAGE_TYPE_EXERCISE_AVAILABLE,
            trigger=trigger,
            recipient_role=RECIPIENT_COMPETITOR,
            competitor_id=competitor.id,
            user_id=competitor.user_id,
            competition_id=competition_id,
            stage_id=stage_id,
            triggered_by_user_id=actor_id,
            dedupe_key=c_dedupe,
        )
        if c_result.sent and c_result.error != "deduped":
            summary.competitor_sent += 1
            await _enqueue_outbox(
                session,
                event_key=MESSAGE_TYPE_EXERCISE_AVAILABLE,
                competition_id=competition_id,
                recipient_role="COMPETITOR",
                recipient_id=competitor.id,
                body=c_msg,
                dedupe_key=c_dedupe,
                payload=context,
            )
        elif not c_result.sent:
            summary.failed += 1

        # Coach
        coach_phone = _coach_phone(competitor)
        k_dedupe = (
            None if force else f"EXERCISE_AVAILABLE:{competitor.id}:{stage_id}:coach"
        )
        k_msg = _exercise_available_message(context, for_coach=True)
        k_result, _ = await send_and_log_sms(
            session,
            phone=coach_phone,
            message=k_msg,
            message_type=MESSAGE_TYPE_EXERCISE_AVAILABLE,
            trigger=trigger,
            recipient_role=RECIPIENT_COACH,
            competitor_id=competitor.id,
            competition_id=competition_id,
            stage_id=stage_id,
            triggered_by_user_id=actor_id,
            dedupe_key=k_dedupe,
        )
        if k_result.sent and k_result.error != "deduped":
            summary.coach_sent += 1
            await _enqueue_outbox(
                session,
                event_key=MESSAGE_TYPE_EXERCISE_AVAILABLE,
                competition_id=competition_id,
                recipient_role="COACH",
                recipient_id=competitor.id,
                body=k_msg,
                dedupe_key=k_dedupe,
                payload=context,
            )
        elif not k_result.sent:
            summary.failed += 1

    exercise.availability_notified_at = datetime.utcnow()
    await session.flush()
    if commit:
        await session.commit()
    return summary


async def notify_submission_received(
    session: AsyncSession,
    *,
    submission: Submission,
    trigger: str = "submission_finalise",
    commit: bool = False,
) -> NotifySummary:
    """Send SUBMISSION_RECEIVED SMS to competitor + coach (best-effort)."""
    summary = NotifySummary()
    competitor = await session.get(Competitor, submission.competitor_id)
    if competitor is None:
        return summary
    stage = await session.get(Stage, submission.stage_id) if submission.stage_id else None
    competition = await session.get(Competition, submission.competition_id)
    skill = (
        await session.get(Skill, competitor.skill_id) if competitor.skill_id else None
    )
    if competition is None or stage is None:
        return summary

    summary.competitors_considered = 1
    context = {
        "competitionName": competition.name,
        "skillName": skill.name if skill else "Skill",
        "stageName": stage.name,
        "competitorName": _competitor_display_name(competitor),
        "coachName": _coach_name(competitor),
        "receipt": submission.receipt or "",
        "state": submission.state,
        "portalUrl": _portal_url(submission.competition_id, stage.id),
    }

    c_dedupe = f"SUBMISSION_RECEIVED:{submission.id}:competitor"
    c_msg = _submission_received_message(context, for_coach=False)
    c_result, _ = await send_and_log_sms(
        session,
        phone=_competitor_phone(competitor),
        message=c_msg,
        message_type=MESSAGE_TYPE_SUBMISSION_RECEIVED,
        trigger=trigger,
        recipient_role=RECIPIENT_COMPETITOR,
        competitor_id=competitor.id,
        user_id=competitor.user_id,
        competition_id=submission.competition_id,
        stage_id=stage.id,
        submission_id=submission.id,
        dedupe_key=c_dedupe,
    )
    if c_result.sent and c_result.error != "deduped":
        summary.competitor_sent += 1
        await _enqueue_outbox(
            session,
            event_key=MESSAGE_TYPE_SUBMISSION_RECEIVED,
            competition_id=submission.competition_id,
            recipient_role="COMPETITOR",
            recipient_id=competitor.id,
            body=c_msg,
            dedupe_key=c_dedupe,
            payload=context,
        )
    elif not c_result.sent:
        summary.failed += 1

    k_dedupe = f"SUBMISSION_RECEIVED:{submission.id}:coach"
    k_msg = _submission_received_message(context, for_coach=True)
    k_result, _ = await send_and_log_sms(
        session,
        phone=_coach_phone(competitor),
        message=k_msg,
        message_type=MESSAGE_TYPE_SUBMISSION_RECEIVED,
        trigger=trigger,
        recipient_role=RECIPIENT_COACH,
        competitor_id=competitor.id,
        competition_id=submission.competition_id,
        stage_id=stage.id,
        submission_id=submission.id,
        dedupe_key=k_dedupe,
    )
    if k_result.sent and k_result.error != "deduped":
        summary.coach_sent += 1
        await _enqueue_outbox(
            session,
            event_key=MESSAGE_TYPE_SUBMISSION_RECEIVED,
            competition_id=submission.competition_id,
            recipient_role="COACH",
            recipient_id=competitor.id,
            body=k_msg,
            dedupe_key=k_dedupe,
            payload=context,
        )
    elif not k_result.sent:
        summary.failed += 1

    if commit:
        await session.commit()
    return summary


async def poll_deferred_exercise_availability(
    session: AsyncSession,
    *,
    actor: User | None = None,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """Find PUBLISHED exercises with open windows not yet notified and fan out."""
    now = datetime.utcnow()
    rows = (
        await session.execute(
            select(Exercise)
            .options(selectinload(Exercise.stage))
            .where(
                Exercise.status == "PUBLISHED",
                Exercise.availability_notified_at.is_(None),
            )
        )
    ).scalars().all()

    results: list[dict[str, Any]] = []
    for ex in rows:
        stage = ex.stage
        if stage is None:
            continue
        if not is_stage_window_open(stage, now=now):
            continue
        summary = await notify_exercise_available(
            session,
            competition_id=ex.competition_id,
            stage_id=ex.stage_id,
            trigger="poll_deferred",
            actor=actor,
            force=False,
            commit=False,
        )
        results.append(
            {
                "competitionId": str(ex.competition_id),
                "stageId": str(ex.stage_id),
                "exerciseId": str(ex.id),
                "competitorsConsidered": summary.competitors_considered,
                "competitorSent": summary.competitor_sent,
                "coachSent": summary.coach_sent,
                "failed": summary.failed,
                "skippedNotReady": summary.skipped_not_ready,
                "skippedAlreadyNotified": summary.skipped_already_notified,
            }
        )
    if commit:
        await session.commit()
    return results


@dataclass
class SkillBroadcastSummary:
    competitors_considered: int = 0
    competitor_sent: int = 0
    coach_sent: int = 0
    failed: int = 0
    skipped_no_phone: int = 0
    recipients: str = "both"
    template_key: str = "custom"


def _resolve_skill_template(
    *,
    template_key: str,
    message: str | None,
) -> str:
    key = (template_key or "custom").strip().lower()
    custom = (message or "").strip()
    if key == "custom":
        if not custom:
            raise AppError(
                "VALIDATION_ERROR",
                "Message body is required for a custom SMS",
                status_code=422,
                fields=[FieldError("message", "REQUIRED")],
            )
        return custom
    preset = SKILL_SMS_TEMPLATES.get(key)
    if preset is None:
        raise AppError(
            "VALIDATION_ERROR",
            f"Unknown templateKey '{template_key}'",
            status_code=422,
            fields=[FieldError("templateKey", "INVALID")],
        )
    # general_notice keeps the preset and injects message as {{customNote}}
    if key == "general_notice":
        return preset
    # Allow admin to override other preset bodies
    return custom if custom else preset


def _skill_portal_url(competition_id: uuid.UUID) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/competitor/competitions/{competition_id}"


async def send_skill_broadcast_sms(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    recipients: str = "both",
    template_key: str = "custom",
    message: str | None = None,
    competitor_ids: list[uuid.UUID] | None = None,
    actor: User | None = None,
    trigger: str = "skill_broadcast",
    commit: bool = True,
) -> SkillBroadcastSummary:
    """Send templated SMS to competitors and/or coaches for a skill cohort."""
    from fastapi import status

    recipients_norm = (recipients or "both").strip().lower()
    if recipients_norm not in {"competitors", "coaches", "both"}:
        raise AppError(
            "VALIDATION_ERROR",
            "recipients must be competitors, coaches, or both",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("recipients", "INVALID")],
        )

    body_template = _resolve_skill_template(template_key=template_key, message=message)

    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.competition_id != competition_id:
        raise AppError("SKILL_NOT_FOUND", "Skill not found in competition", status_code=404)

    stmt = select(Competitor).where(
        Competitor.competition_id == competition_id,
        Competitor.skill_id == skill_id,
    )
    if competitor_ids:
        stmt = stmt.where(Competitor.id.in_(competitor_ids))
    else:
        stmt = stmt.where(
            Competitor.status.notin_(["WITHDRAWN", "DISQUALIFIED", "DQ"])
        )

    competitors = list((await session.execute(stmt)).scalars().all())
    summary = SkillBroadcastSummary(
        competitors_considered=len(competitors),
        recipients=recipients_norm,
        template_key=(template_key or "custom").strip().lower(),
    )
    actor_id = actor.id if actor else None
    portal = _skill_portal_url(competition_id)

    zone_ids = {c.zone_id for c in competitors if c.zone_id}
    zones: dict[uuid.UUID, Zone] = {}
    if zone_ids:
        zone_rows = (
            await session.execute(select(Zone).where(Zone.id.in_(zone_ids)))
        ).scalars().all()
        zones = {z.id: z for z in zone_rows}

    send_competitors = recipients_norm in {"competitors", "both"}
    send_coaches = recipients_norm in {"coaches", "both"}

    for competitor in competitors:
        zone = zones.get(competitor.zone_id) if competitor.zone_id else None
        zone_name = zone.name if zone else ""
        zone_label = f" ({zone_name})" if zone_name else ""
        context = {
            "competitionName": competition.name,
            "skillName": skill.name,
            "competitorName": _competitor_display_name(competitor),
            "coachName": _coach_name(competitor),
            "zoneName": zone_name,
            "zoneLabel": zone_label,
            "portalUrl": portal,
            "customNote": (message or "").strip(),
        }
        rendered = _render(body_template, context)

        if send_competitors:
            phone = _competitor_phone(competitor)
            if not phone:
                summary.skipped_no_phone += 1
            else:
                result, _ = await send_and_log_sms(
                    session,
                    phone=phone,
                    message=rendered,
                    message_type=MESSAGE_TYPE_SKILL_BROADCAST,
                    trigger=trigger,
                    recipient_role=RECIPIENT_COMPETITOR,
                    competitor_id=competitor.id,
                    user_id=competitor.user_id,
                    competition_id=competition_id,
                    triggered_by_user_id=actor_id,
                    dedupe_key=None,
                )
                if result.sent:
                    summary.competitor_sent += 1
                    await _enqueue_outbox(
                        session,
                        event_key=MESSAGE_TYPE_SKILL_BROADCAST,
                        competition_id=competition_id,
                        recipient_role="COMPETITOR",
                        recipient_id=competitor.id,
                        body=rendered,
                        dedupe_key=None,
                        payload=context,
                    )
                else:
                    summary.failed += 1

        if send_coaches:
            coach_phone = _coach_phone(competitor)
            if not coach_phone:
                summary.skipped_no_phone += 1
            else:
                result, _ = await send_and_log_sms(
                    session,
                    phone=coach_phone,
                    message=rendered,
                    message_type=MESSAGE_TYPE_SKILL_BROADCAST,
                    trigger=trigger,
                    recipient_role=RECIPIENT_COACH,
                    competitor_id=competitor.id,
                    competition_id=competition_id,
                    triggered_by_user_id=actor_id,
                    dedupe_key=None,
                )
                if result.sent:
                    summary.coach_sent += 1
                    await _enqueue_outbox(
                        session,
                        event_key=MESSAGE_TYPE_SKILL_BROADCAST,
                        competition_id=competition_id,
                        recipient_role="COACH",
                        recipient_id=competitor.id,
                        body=rendered,
                        dedupe_key=None,
                        payload=context,
                    )
                else:
                    summary.failed += 1

    if commit:
        await session.commit()
    return summary
