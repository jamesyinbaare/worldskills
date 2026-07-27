"""Admin / chief scoring overview and submission-total resolution."""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability
from app.models import (
    Competitor,
    Exercise,
    ModerationFlag,
    ResultPublication,
    Score,
    Skill,
    Stage,
    Submission,
    User,
)
from app.schemas.scoring_overview import (
    AssessorTotalOut,
    CriterionAssessorMarkOut,
    CriterionScoringOut,
    ResolveTotalIn,
    ResolveTotalOut,
    ScoringDetailOut,
    ScoringListItemOut,
)
from app.services.assessment import (
    _ensure_anon_code,
    _resolve_scheme_for_submission,
    _rubric_from_scheme,
    compute_assessor_total,
    compute_submission_total,
)
from app.services.audit import write_audit_event
from app.services.moderation import assert_moderator_segregation


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.email


def _competitor_name(comp: Competitor | None) -> str | None:
    if comp is None:
        return None
    parts = [p for p in (comp.given_names, comp.family_name) if p]
    return " ".join(parts) if parts else None


async def _stage_released(
    session: AsyncSession, competition_id: uuid.UUID, stage_id: uuid.UUID | None
) -> bool:
    if stage_id is None:
        return False
    row = (
        await session.execute(
            select(ResultPublication.id).where(
                ResultPublication.competition_id == competition_id,
                ResultPublication.stage_id == stage_id,
                ResultPublication.state == "RELEASED",
            )
        )
    ).scalar_one_or_none()
    return row is not None


def _assessor_breakdown(
    scores: list[Score], users: dict[uuid.UUID, User]
) -> list[AssessorTotalOut]:
    by_assessor: dict[uuid.UUID, list[Score]] = {}
    for s in scores:
        by_assessor.setdefault(s.assessor_id, []).append(s)

    outs: list[AssessorTotalOut] = []
    for assessor_id, rows in by_assessor.items():
        marks = [r for r in rows if r.score_type in {"MEASUREMENT", "JUDGEMENT"}]
        pens = [r for r in rows if r.score_type == "PENALTY"]
        user = users.get(assessor_id)
        outs.append(
            AssessorTotalOut(
                assessorId=assessor_id,
                assessorName=_display_name(user),
                assessorEmail=user.email if user else None,
                total=compute_assessor_total(marks, pens),
                markCount=len(marks),
                finalized=any(r.status == "FINAL" for r in marks),
            )
        )
    outs.sort(key=lambda a: (a.assessorName or "", str(a.assessorId)))
    return outs


def _totals_disagree(assessor_totals: list[AssessorTotalOut]) -> bool:
    if len(assessor_totals) < 2:
        return False
    values = {a.total for a in assessor_totals}
    return len(values) > 1


async def list_scoring_overview(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    skill_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
) -> list[ScoringListItemOut]:
    if not has_capability(actor.role, Capability.MODERATE_SCORE):
        raise AppError("FORBIDDEN", "Missing moderate capability", status_code=403)

    submissions = (
        await session.execute(
            select(Submission).where(
                Submission.competition_id == competition_id,
                Submission.state.in_(["ACCEPTED", "LATE"]),
            )
        )
    ).scalars().all()

    items: list[ScoringListItemOut] = []
    for submission in submissions:
        competitor = await session.get(Competitor, submission.competitor_id)
        if competitor is None:
            continue
        if skill_id is not None and competitor.skill_id != skill_id:
            continue
        if stage_id is not None and submission.stage_id != stage_id:
            continue

        skill = await session.get(Skill, competitor.skill_id) if competitor.skill_id else None
        stage = await session.get(Stage, submission.stage_id) if submission.stage_id else None
        exercise = None
        if submission.stage_id:
            exercise = (
                await session.execute(
                    select(Exercise).where(Exercise.stage_id == submission.stage_id)
                )
            ).scalar_one_or_none()

        scheme = None
        blind = True
        try:
            scheme = await _resolve_scheme_for_submission(session, submission)
            rubric = _rubric_from_scheme(scheme)
            blind = bool(rubric.get("blindMode", True))
            _ensure_anon_code(submission, competitor)
        except AppError:
            rubric = {"blindMode": True, "criteria": []}

        scores = (
            await session.execute(select(Score).where(Score.submission_id == submission.id))
        ).scalars().all()
        assessor_ids = {s.assessor_id for s in scores}
        users: dict[uuid.UUID, User] = {}
        if assessor_ids:
            for u in (
                await session.execute(select(User).where(User.id.in_(assessor_ids)))
            ).scalars().all():
                users[u.id] = u
        assessor_totals = _assessor_breakdown(list(scores), users)

        open_flags = (
            await session.execute(
                select(ModerationFlag).where(
                    ModerationFlag.submission_id == submission.id,
                    ModerationFlag.flagged.is_(True),
                )
            )
        ).scalars().all()

        released = await _stage_released(
            session, competition_id, submission.stage_id
        )

        items.append(
            ScoringListItemOut(
                submissionId=submission.id,
                anonCode=submission.anon_code,
                state=submission.state,
                skillId=competitor.skill_id,
                skillName=skill.name if skill else None,
                stageId=submission.stage_id,
                stageName=stage.name if stage else None,
                exerciseTitle=exercise.title if exercise else None,
                competitorId=None if blind else competitor.id,
                competitorRef=None if blind else competitor.ref_no,
                competitorName=None if blind else _competitor_name(competitor),
                blindMode=blind,
                submissionTotal=submission.score_total,
                assessorCount=len(assessor_totals),
                assessorTotals=assessor_totals,
                disagreement=_totals_disagree(assessor_totals) or len(open_flags) > 0,
                openFlags=len(open_flags),
                resultsReleased=released,
            )
        )

    await session.flush()
    items.sort(
        key=lambda i: (
            i.skillName or "",
            i.stageName or "",
            i.anonCode or str(i.submissionId),
        )
    )
    return items


async def get_scoring_detail(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
) -> ScoringDetailOut:
    if not has_capability(actor.role, Capability.MODERATE_SCORE):
        raise AppError("FORBIDDEN", "Missing moderate capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)

    competitor = await session.get(Competitor, submission.competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor missing", status_code=404)

    skill = await session.get(Skill, competitor.skill_id) if competitor.skill_id else None
    stage = await session.get(Stage, submission.stage_id) if submission.stage_id else None
    exercise = None
    if submission.stage_id:
        exercise = (
            await session.execute(select(Exercise).where(Exercise.stage_id == submission.stage_id))
        ).scalar_one_or_none()

    scheme = await _resolve_scheme_for_submission(session, submission)
    rubric = _rubric_from_scheme(scheme)
    blind = bool(rubric.get("blindMode", True))
    _ensure_anon_code(submission, competitor)

    scores = (
        await session.execute(select(Score).where(Score.submission_id == submission_id))
    ).scalars().all()
    assessor_ids = {s.assessor_id for s in scores}
    users: dict[uuid.UUID, User] = {}
    if assessor_ids:
        for u in (
            await session.execute(select(User).where(User.id.in_(assessor_ids)))
        ).scalars().all():
            users[u.id] = u

    assessor_totals = _assessor_breakdown(list(scores), users)

    criteria_out: list[CriterionScoringOut] = []
    for crit in rubric.get("criteria") or []:
        cid = str(crit.get("id") or crit.get("criterionId") or "")
        if not cid:
            continue
        ctype = str(crit.get("type", "MEASUREMENT")).upper()
        rows = [
            s
            for s in scores
            if s.criterion_id == cid and s.score_type in {"MEASUREMENT", "JUDGEMENT"}
        ]
        marks = [
            CriterionAssessorMarkOut(
                assessorId=r.assessor_id,
                assessorName=_display_name(users.get(r.assessor_id)),
                type=r.score_type,
                raw=r.raw,
                standardised=r.standardised,
                status=r.status,
                comment=r.comment,
            )
            for r in rows
        ]
        raws = [int(m.raw) for m in marks if m.raw is not None]
        std = next((int(m.standardised) for m in marks if m.standardised is not None), None)
        criteria_out.append(
            CriterionScoringOut(
                criterionId=cid,
                name=str(crit.get("name") or crit.get("label") or cid),
                type=ctype,
                max=int(crit["max"]) if crit.get("max") is not None else None,
                marks=marks,
                standardisedValue=std,
                disagreement=len(set(raws)) > 1 if len(raws) >= 2 else False,
            )
        )

    open_flags = (
        await session.execute(
            select(ModerationFlag).where(
                ModerationFlag.submission_id == submission_id,
                ModerationFlag.flagged.is_(True),
            )
        )
    ).scalars().all()

    released = await _stage_released(
        session, submission.competition_id, submission.stage_id
    )
    await session.flush()

    return ScoringDetailOut(
        submissionId=submission.id,
        anonCode=submission.anon_code,
        state=submission.state,
        skillId=competitor.skill_id,
        skillName=skill.name if skill else None,
        stageId=submission.stage_id,
        stageName=stage.name if stage else None,
        exerciseTitle=exercise.title if exercise else None,
        blindMode=blind,
        competitorId=None if blind else competitor.id,
        competitorRef=None if blind else competitor.ref_no,
        competitorName=None if blind else _competitor_name(competitor),
        submissionTotal=submission.score_total,
        assessorTotals=assessor_totals,
        criteria=criteria_out,
        disagreement=_totals_disagree(assessor_totals)
        or any(c.disagreement for c in criteria_out)
        or len(open_flags) > 0,
        openFlags=len(open_flags),
        resultsReleased=released,
    )


async def resolve_submission_total(
    session: AsyncSession,
    submission_id: uuid.UUID,
    payload: ResolveTotalIn,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ResolveTotalOut:
    if not has_capability(actor.role, Capability.MODERATE_SCORE):
        raise AppError("FORBIDDEN", "Missing moderate capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)

    await assert_moderator_segregation(
        session,
        competition_id=submission.competition_id,
        submission_id=submission_id,
        moderator=actor,
        ip=ip,
        user_agent=user_agent,
    )

    scores = list(
        (
            await session.execute(select(Score).where(Score.submission_id == submission_id))
        ).scalars().all()
    )
    if not scores:
        raise AppError(
            "SCORE_INCOMPLETE",
            "No scores to resolve",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("submissionId", "SCORE_INCOMPLETE")],
        )

    assessor_ids = {s.assessor_id for s in scores}
    users: dict[uuid.UUID, User] = {}
    if assessor_ids:
        for u in (
            await session.execute(select(User).where(User.id.in_(assessor_ids)))
        ).scalars().all():
            users[u.id] = u
    assessor_totals = _assessor_breakdown(scores, users)
    before_total = submission.score_total

    method = payload.method
    reason = (payload.reason or "").strip() or None

    criterion_rows = [
        s for s in scores if s.score_type in {"MEASUREMENT", "JUDGEMENT"} and s.raw is not None
    ]
    by_crit: dict[str, list[Score]] = {}
    for s in criterion_rows:
        by_crit.setdefault(s.criterion_id, []).append(s)

    if method == "AVERAGE":
        if len(assessor_totals) < 1:
            raise AppError(
                "SCORE_INCOMPLETE",
                "Need at least one assessor total to average",
                status_code=409,
            )
        for _cid, rows in by_crit.items():
            raws = [int(r.raw) for r in rows if r.raw is not None]
            if not raws:
                continue
            value = int(round(statistics.mean(raws)))
            for row in rows:
                row.standardised = value
        # Leave penalties as-is (shared across assessors via compute_submission_total)
    else:
        assessor_id = payload.assessorId
        assert assessor_id is not None
        if assessor_id not in assessor_ids:
            raise AppError(
                "VALIDATION_ERROR",
                "Assessor has no marks on this submission",
                status_code=422,
                fields=[FieldError("assessorId", "NOT_FOUND")],
            )
        if not reason:
            raise AppError(
                "REASON_REQUIRED",
                "A reason is required when selecting one assessor",
                status_code=422,
                fields=[FieldError("reason", "REASON_REQUIRED")],
            )
        for _cid, rows in by_crit.items():
            selected = next((r for r in rows if r.assessor_id == assessor_id), None)
            if selected is None or selected.raw is None:
                continue
            value = int(selected.raw)
            for row in rows:
                row.standardised = value
        # Use only selected assessor's penalties in the aggregate
        for s in scores:
            if s.score_type != "PENALTY":
                continue
            if s.assessor_id != assessor_id:
                s.penalty = 0
                s.raw = 0

    await session.flush()
    all_scores = list(
        (
            await session.execute(select(Score).where(Score.submission_id == submission_id))
        ).scalars().all()
    )
    submission.score_total = compute_submission_total(all_scores)

    await write_audit_event(
        session,
        action="SCORING_RESOLVE_TOTAL",
        entity_type="Submission",
        entity_id=str(submission_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=submission.competition_id,
        before={"total": before_total},
        after={
            "method": method,
            "assessorId": str(payload.assessorId) if payload.assessorId else None,
            "total": submission.score_total,
            "reason": reason,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    refreshed_totals = _assessor_breakdown(all_scores, users)
    return ResolveTotalOut(
        submissionId=submission_id,
        method=method,
        assessorId=payload.assessorId,
        total=int(submission.score_total or 0),
        assessorTotals=refreshed_totals,
        reason=reason,
    )
