"""Competitor portal discovery — my registrations and skill pathway stages."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Competition, Competitor, Exercise, Skill, Stage, Submission, User
from app.schemas.competitor_portal import (
    MyRegistrationOut,
    MyStageOut,
    MyStagesOut,
    MyStageSubmissionSummary,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _window_status(opens_at: datetime | None, closes_at: datetime | None, *, now: datetime) -> str:
    if opens_at is None and closes_at is None:
        return "unknown"
    if opens_at is not None and now < opens_at:
        return "upcoming"
    if closes_at is not None and now > closes_at:
        return "closed"
    return "open"


async def list_my_registrations(session: AsyncSession, *, actor: User) -> list[MyRegistrationOut]:
    competitors = (
        await session.execute(select(Competitor).where(Competitor.user_id == actor.id))
    ).scalars().all()

    out: list[MyRegistrationOut] = []
    for comp in competitors:
        competition = await session.get(Competition, comp.competition_id)
        if competition is None:
            continue
        skill = await session.get(Skill, comp.skill_id) if comp.skill_id else None
        skill_name = skill.name if skill is not None else "Draft application"
        skill_id = skill.id if skill is not None else None
        payload = comp.registration_payload if isinstance(comp.registration_payload, dict) else {}
        if skill is None and payload.get("skillIds"):
            try:
                maybe = uuid.UUID(str(payload["skillIds"][0]))
                skill = await session.get(Skill, maybe)
                if skill is not None:
                    skill_id = skill.id
                    skill_name = skill.name
            except (ValueError, TypeError, IndexError):
                pass
        out.append(
            MyRegistrationOut(
                competitorId=comp.id,
                competitionId=competition.id,
                competitionName=competition.name,
                skillId=skill_id,
                skillName=skill_name,
                status=comp.status,
                zoneId=comp.zone_id,
                flags=list(comp.flags or []),
                consentParticipationAt=comp.consent_participation_at,
                consentPublicAt=comp.consent_public_at,
                publicProfileVisible=bool(comp.public_profile_visible),
                consentFormUploadedAt=comp.consent_form_uploaded_at,
                hasCriteriaDocument=bool(
                    skill and skill.criteria_object_key and skill.criteria_file_name
                ),
                criteriaFileName=skill.criteria_file_name if skill else None,
            )
        )
    # Stable order: competition name then skill name
    out.sort(key=lambda r: (r.competitionName.lower(), r.skillName.lower()))
    return out


async def get_my_stages(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> MyStagesOut:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    competitor = (
        await session.execute(
            select(Competitor).where(
                Competitor.user_id == actor.id,
                Competitor.competition_id == competition_id,
            )
        )
    ).scalar_one_or_none()
    if competitor is None or competitor.status == "DRAFT":
        raise AppError(
            "COMPETITOR_NOT_FOUND",
            "You are not registered in this competition",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    skill = await session.get(Skill, competitor.skill_id)
    if skill is None:
        raise AppError(
            "SKILL_NOT_FOUND",
            "Registered skill not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    stages = (
        await session.execute(
            select(Stage)
            .where(Stage.competition_id == competition_id, Stage.skill_id == competitor.skill_id)
            .order_by(Stage.order.asc())
        )
    ).scalars().all()

    stage_ids = [s.id for s in stages]
    exercises_by_stage: dict[uuid.UUID, Exercise] = {}
    if stage_ids:
        for ex in (
            await session.execute(select(Exercise).where(Exercise.stage_id.in_(stage_ids)))
        ).scalars().all():
            exercises_by_stage[ex.stage_id] = ex

    submissions_by_stage: dict[uuid.UUID, Submission] = {}
    if stage_ids:
        for sub in (
            await session.execute(
                select(Submission).where(
                    Submission.competitor_id == competitor.id,
                    Submission.stage_id.in_(stage_ids),
                )
            )
        ).scalars().all():
            if sub.stage_id is not None:
                submissions_by_stage[sub.stage_id] = sub

    now = _utcnow()
    stage_outs: list[MyStageOut] = []
    for stage in stages:
        ex = exercises_by_stage.get(stage.id)
        published = ex is not None and ex.status == "PUBLISHED"
        sub = submissions_by_stage.get(stage.id)
        submission_summary = (
            MyStageSubmissionSummary(
                submissionId=sub.id,
                state=sub.state,
                uploadLocked=bool(sub.upload_locked),
                receipt=sub.receipt,
            )
            if sub is not None
            else MyStageSubmissionSummary()
        )
        stage_outs.append(
            MyStageOut(
                stageId=stage.id,
                order=stage.order,
                name=stage.name,
                type=stage.stage_type,
                opensAt=stage.opens_at,
                closesAt=stage.closes_at,
                exerciseAvailable=published,
                exerciseTitle=ex.title if published else None,
                exerciseStatus=ex.status if ex is not None else None,
                windowStatus=_window_status(stage.opens_at, stage.closes_at, now=now),
                submission=submission_summary,
            )
        )

    return MyStagesOut(
        competitionId=competition.id,
        competitionName=competition.name,
        competitorId=competitor.id,
        skillId=skill.id,
        skillName=skill.name,
        stages=stage_outs,
    )
