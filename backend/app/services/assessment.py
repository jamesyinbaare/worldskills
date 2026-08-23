"""US-ASM-01 — expert scoring against rubric (measurement + judgement, blind, COI-safe)."""

from __future__ import annotations

import re
import secrets
import uuid
from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability
from app.models import (
    Artefact,
    Competitor,
    ExpertAssignment,
    MarkingScheme,
    ResultPublication,
    Score,
    Skill,
    Stage,
    Submission,
    User,
)
from app.schemas.assessment import (
    AssessmentArtefactOut,
    AssessmentViewOut,
    BreakdownOut,
    CriterionMarkIn,
    PenaltyIn,
    PenaltyOut,
    ScoreMarkOut,
    ScorePut,
    ScorePutOut,
)
from app.services.assignments import assert_can_score
from app.services.audit import write_audit_event
from app.services.storage import ObjectStorage, get_object_storage

_SCOREABLE_STATES = {"ACCEPTED", "LATE"}

# Used when an exercise has a scheme/document but no structured criteria were entered.
# Experts need at least one criterion row to enter marks.
_DEFAULT_RUBRIC: dict[str, Any] = {
    "blindMode": True,
    "criteria": [
        {
            "id": "c_overall",
            "name": "Overall",
            "type": "JUDGEMENT",
            "max": 100,
        }
    ],
    "penalties": [],
}


def _rubric_from_scheme(scheme: MarkingScheme | None) -> dict[str, Any]:
    if scheme is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "No marking scheme resolved for submission",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("schemeId", "CONFIG_INCOMPLETE")],
        )
    if scheme.rubric and isinstance(scheme.rubric, dict):
        criteria = scheme.rubric.get("criteria")
        if criteria:
            return scheme.rubric
    # Document-only / legacy schemes: provide a default scoring rubric
    return dict(_DEFAULT_RUBRIC)


def _criterion_map(rubric: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c["id"]): c for c in rubric["criteria"]}


def _penalty_map(rubric: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(p["code"]): p for p in (rubric.get("penalties") or [])}


async def _resolve_scheme_for_submission(
    session: AsyncSession, submission: Submission
) -> MarkingScheme:
    from app.models import Exercise

    scheme_id = None
    if submission.stage_id:
        ex = (
            await session.execute(select(Exercise).where(Exercise.stage_id == submission.stage_id))
        ).scalar_one_or_none()
        if ex and ex.scheme_id and ex.status == "PUBLISHED":
            scheme_id = ex.scheme_id
    if scheme_id is None:
        competitor = await session.get(Competitor, submission.competitor_id)
        if competitor:
            skill = await session.get(Skill, competitor.skill_id)
            if skill and skill.scheme_id:
                scheme_id = skill.scheme_id
    if scheme_id is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "No marking scheme resolved for submission",
            status_code=409,
            fields=[FieldError("schemeId", "CONFIG_INCOMPLETE")],
        )
    scheme = await session.get(MarkingScheme, scheme_id)
    if scheme is None:
        raise AppError("CONFIG_INCOMPLETE", "Marking scheme missing", status_code=409)
    return scheme


async def _ensure_assigned(
    session: AsyncSession, *, competition_id: uuid.UUID, expert: User, competitor: Competitor
) -> ExpertAssignment | None:
    """Authorize scoring via global catalog skill areas; optional competition assignment bookkeeping."""
    from app.services import expert_skill_areas as expert_skill_areas_service

    if competitor.skill_id is None:
        raise AppError(
            "NOT_ASSIGNED",
            "Competitor has no skill area",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("expertId", "NOT_ASSIGNED")],
        )

    skill = await session.get(Skill, competitor.skill_id)
    if skill is None or skill.competition_id != competition_id:
        raise AppError(
            "NOT_ASSIGNED",
            "Competitor skill is invalid for this competition",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("expertId", "NOT_ASSIGNED")],
        )

    if skill.catalog_skill_id is None:
        raise AppError(
            "NOT_ASSIGNED",
            "Skill area is not linked to the catalog; cannot authorize expert",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("expertId", "NOT_ASSIGNED")],
        )

    has_area = await expert_skill_areas_service.expert_has_catalog_skill(
        session, expert_id=expert.id, catalog_skill_id=skill.catalog_skill_id
    )
    if not has_area:
        raise AppError(
            "NOT_ASSIGNED",
            "Expert is not assigned to this skill area",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("expertId", "NOT_ASSIGNED")],
        )

    # Optional zone restriction from competition bookkeeping
    result = await session.execute(
        select(ExpertAssignment).where(
            ExpertAssignment.competition_id == competition_id,
            ExpertAssignment.expert_id == expert.id,
            ExpertAssignment.skill_id == competitor.skill_id,
        )
    )
    rows = list(result.scalars().all())
    if rows:
        allowed = False
        matched: ExpertAssignment | None = None
        for row in rows:
            if row.zone_id is None or row.zone_id == competitor.zone_id:
                allowed = True
                matched = row
                break
        if not allowed:
            raise AppError(
                "NOT_ASSIGNED",
                "Expert is not assigned to this skill/zone",
                status_code=status.HTTP_403_FORBIDDEN,
                fields=[FieldError("expertId", "NOT_ASSIGNED")],
            )
        return matched

    return None


def _ensure_anon_code(submission: Submission, competitor: Competitor) -> str:
    if submission.anon_code:
        return submission.anon_code
    # Derive from ref_no; keep short opaque code
    code = f"A-{competitor.ref_no[-8:].upper()}" if competitor.ref_no else f"A-{secrets.token_hex(4).upper()}"
    submission.anon_code = code
    return code


_UNSAFE_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|\r\n]+')
_MULTI_SPACE = re.compile(r"\s+")
_MAX_DOWNLOAD_NAME_LEN = 180


def _sanitize_filename_segment(value: str, *, fallback: str = "file") -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("-", (value or "").strip())
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip(" .-_")
    return cleaned or fallback


def assessment_download_filename(
    *,
    anon_code: str,
    deliverable_code: str,
    original_filename: str,
) -> str:
    """Blind-safe download name: {anon}__{deliverable}__{original}."""
    anon = _sanitize_filename_segment(anon_code, fallback="anon")
    deliverable = _sanitize_filename_segment(deliverable_code, fallback="deliverable")
    original = _sanitize_filename_segment(Path(original_filename or "").name, fallback="artefact")
    name = f"{anon}__{deliverable}__{original}"
    if len(name) <= _MAX_DOWNLOAD_NAME_LEN:
        return name

    stem = Path(original).stem
    suffix = Path(original).suffix
    prefix = f"{anon}__{deliverable}__"
    budget = _MAX_DOWNLOAD_NAME_LEN - len(prefix) - len(suffix)
    if budget < 1:
        return (prefix + "file" + suffix)[:_MAX_DOWNLOAD_NAME_LEN]
    return f"{prefix}{stem[:budget]}{suffix}"


def compute_assessor_total(marks: list[Score], penalties: list[Score]) -> int:
    """Worked-example total: sum of this assessor's criterion raw − penalty deductions."""
    total = sum(int(m.raw or 0) for m in marks if m.score_type in {"MEASUREMENT", "JUDGEMENT"})
    total -= sum(int(p.penalty or p.raw or 0) for p in penalties if p.score_type == "PENALTY")
    return total


def compute_submission_total(all_scores: list[Score]) -> int:
    """Aggregate criterion totals − penalties.

    Measurement: average of raw across assessors.
    Judgement: if any standardised value is set, use that single value (raw preserved on rows);
    otherwise average raw marks across judges.
    """
    by_crit: dict[str, list[Score]] = {}
    penalty_total = 0
    for s in all_scores:
        if s.score_type == "PENALTY":
            penalty_total += int(s.penalty or abs(s.raw or 0))
            continue
        if s.score_type not in {"MEASUREMENT", "JUDGEMENT"}:
            continue
        by_crit.setdefault(s.criterion_id, []).append(s)

    total = 0
    for rows in by_crit.values():
        standardised_vals = [int(r.standardised) for r in rows if r.standardised is not None]
        if standardised_vals:
            # Spec: standardised is additive; all judge rows get the same standardised value
            total += standardised_vals[0]
            continue
        raws = [int(r.raw) for r in rows if r.raw is not None]
        if raws:
            total += round(sum(raws) / len(raws))
    return total - penalty_total


async def assert_scoring_not_released(
    session: AsyncSession,
    submission: Submission,
) -> None:
    """Block expert score edits when results for this stage/exercise are released."""
    if submission.stage_id is None:
        return
    released = (
        await session.execute(
            select(ResultPublication).where(
                ResultPublication.competition_id == submission.competition_id,
                ResultPublication.stage_id == submission.stage_id,
                ResultPublication.state == "RELEASED",
            )
        )
    ).scalars().first()
    if released is not None:
        raise AppError(
            "RESULTS_RELEASED",
            "Results for this exercise have been released; scores can no longer be updated",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("stageId", "RESULTS_RELEASED")],
        )


async def get_assessment_view(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AssessmentViewOut:
    if not has_capability(actor.role, Capability.SCORE_SUBMISSION):
        raise AppError("FORBIDDEN", "Missing score capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)
    if submission.state not in _SCOREABLE_STATES:
        raise AppError(
            "SUBMISSION_NOT_READY",
            f"Submission state is {submission.state}; only ACCEPTED or LATE can be scored",
            status_code=409,
            fields=[FieldError("state", "SUBMISSION_NOT_READY")],
        )

    competitor = await session.get(Competitor, submission.competitor_id)
    assert competitor is not None
    await _ensure_assigned(session, competition_id=submission.competition_id, expert=actor, competitor=competitor)
    await assert_can_score(
        session,
        competition_id=submission.competition_id,
        expert=actor,
        competitor=competitor,
        submission_id=submission.id,
        ip=ip,
        user_agent=user_agent,
    )

    scheme = await _resolve_scheme_for_submission(session, submission)
    rubric = _rubric_from_scheme(scheme)
    blind = bool(rubric.get("blindMode", False))
    anon = _ensure_anon_code(submission, competitor)
    await session.flush()

    my_scores = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.assessor_id == actor.id,
                Score.score_type.in_(["MEASUREMENT", "JUDGEMENT"]),
            )
        )
    ).scalars().all()

    artefacts = (
        await session.execute(
            select(Artefact)
            .where(
                Artefact.submission_id == submission_id,
                Artefact.complete.is_(True),
                Artefact.quarantined.is_(False),
                Artefact.scan_status == "CLEAN",
            )
            .order_by(Artefact.deliverable_code, Artefact.created_at)
        )
    ).scalars().all()

    return AssessmentViewOut(
        submissionId=submission.id,
        anonCode=anon,
        state=submission.state,
        blindMode=blind,
        competitorId=None if blind else competitor.id,
        givenNames=None if blind else competitor.given_names,
        familyName=None if blind else competitor.family_name,
        institutionId=None if blind else competitor.institution_id,
        photoKey=None if blind else competitor.photo_key,
        criteria=list(rubric.get("criteria") or []),
        penalties=list(rubric.get("penalties") or []),
        myMarks=[
            ScoreMarkOut(
                criterionId=s.criterion_id,
                type=s.score_type,
                value=s.raw,
                assessorId=s.assessor_id,
                judgeId=s.judge_id,
                comment=s.comment,
                status=s.status,
            )
            for s in my_scores
        ],
        total=submission.score_total,
        artefacts=[
            AssessmentArtefactOut(
                artefactId=a.id,
                deliverableCode=a.deliverable_code,
                filename=a.filename,
                contentType=a.content_type,
                size=int(a.size or 0),
                scanStatus=a.scan_status,
            )
            for a in artefacts
        ],
    )


async def download_assessment_artefact(
    session: AsyncSession,
    submission_id: uuid.UUID,
    artefact_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str, str]:
    """Download a CLEAN artefact for an assigned expert scoring this submission."""
    if not has_capability(actor.role, Capability.SCORE_SUBMISSION):
        raise AppError("FORBIDDEN", "Missing score capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)
    if submission.state not in _SCOREABLE_STATES:
        raise AppError(
            "SUBMISSION_NOT_READY",
            f"Submission state is {submission.state}; only ACCEPTED or LATE can be scored",
            status_code=409,
            fields=[FieldError("state", "SUBMISSION_NOT_READY")],
        )

    competitor = await session.get(Competitor, submission.competitor_id)
    assert competitor is not None
    await _ensure_assigned(
        session, competition_id=submission.competition_id, expert=actor, competitor=competitor
    )
    await assert_can_score(
        session,
        competition_id=submission.competition_id,
        expert=actor,
        competitor=competitor,
        submission_id=submission.id,
        ip=ip,
        user_agent=user_agent,
    )

    artefact = await session.get(Artefact, artefact_id)
    if (
        artefact is None
        or artefact.submission_id != submission_id
        or not artefact.complete
        or artefact.quarantined
        or artefact.scan_status != "CLEAN"
        or not artefact.storage_key
    ):
        raise AppError(
            "ARTEFACT_NOT_FOUND",
            "Artefact not available for download",
            status_code=404,
            fields=[FieldError("artefactId", "ARTEFACT_NOT_FOUND")],
        )

    anon = _ensure_anon_code(submission, competitor)
    await session.flush()

    store = storage or get_object_storage()
    data = store.get(artefact.storage_key)
    content_type = artefact.content_type or "application/octet-stream"
    download_name = assessment_download_filename(
        anon_code=anon,
        deliverable_code=artefact.deliverable_code,
        original_filename=artefact.filename,
    )
    return data, download_name, content_type


async def put_scores(
    session: AsyncSession,
    submission_id: uuid.UUID,
    payload: ScorePut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ScorePutOut:
    if not has_capability(actor.role, Capability.SCORE_SUBMISSION):
        raise AppError("FORBIDDEN", "Missing score capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)
    if submission.state not in _SCOREABLE_STATES:
        raise AppError(
            "SUBMISSION_NOT_READY",
            f"Submission state is {submission.state}; only ACCEPTED or LATE can be scored",
            status_code=409,
        )

    await assert_scoring_not_released(session, submission)

    competitor = await session.get(Competitor, submission.competitor_id)
    assert competitor is not None
    await _ensure_assigned(session, competition_id=submission.competition_id, expert=actor, competitor=competitor)
    await assert_can_score(
        session,
        competition_id=submission.competition_id,
        expert=actor,
        competitor=competitor,
        submission_id=submission.id,
        ip=ip,
        user_agent=user_agent,
    )

    scheme = await _resolve_scheme_for_submission(session, submission)
    rubric = _rubric_from_scheme(scheme)
    criteria = _criterion_map(rubric)
    penalties_cfg = _penalty_map(rubric)
    _ensure_anon_code(submission, competitor)

    # Validate marks before mutating
    for mark in payload.criterionMarks:
        crit = criteria.get(mark.criterionId)
        if crit is None:
            raise AppError(
                "CRITERION_UNKNOWN",
                f"Unknown criterion '{mark.criterionId}'",
                status_code=422,
                fields=[FieldError(mark.criterionId, "CRITERION_UNKNOWN")],
            )
        expected_type = str(crit.get("type", "MEASUREMENT")).upper()
        if mark.type.upper() != expected_type:
            raise AppError(
                "CRITERION_TYPE_MISMATCH",
                f"Criterion {mark.criterionId} expects {expected_type}",
                status_code=422,
                fields=[FieldError(mark.criterionId, "CRITERION_TYPE_MISMATCH")],
            )
        max_mark = int(crit["max"])
        if mark.value < 0 or mark.value > max_mark:
            raise AppError(
                "MARK_OUT_OF_RANGE",
                f"Mark must be between 0 and {max_mark}",
                status_code=422,
                fields=[FieldError(mark.criterionId, "MARK_OUT_OF_RANGE")],
            )

    for pen in payload.penalties:
        cfg = penalties_cfg.get(pen.code)
        if cfg is None:
            raise AppError(
                "PENALTY_UNKNOWN",
                f"Unknown penalty '{pen.code}'",
                status_code=422,
                fields=[FieldError(pen.code, "PENALTY_UNKNOWN")],
            )
        deduction = pen.deduction if pen.deduction is not None else int(cfg.get("deduction", 0))
        cap = int(cfg.get("cap", deduction))
        if deduction > cap:
            raise AppError(
                "PENALTY_EXCEEDS_CAP",
                f"Penalty exceeds configured cap of {cap}",
                status_code=422,
                fields=[FieldError(pen.code, "PENALTY_EXCEEDS_CAP")],
            )

    if payload.finalize:
        required_ids = set(criteria.keys())
        provided = {m.criterionId for m in payload.criterionMarks}
        # Also count existing DRAFT/FINAL marks for this assessor that aren't being replaced
        existing = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == submission_id,
                    Score.assessor_id == actor.id,
                    Score.score_type.in_(["MEASUREMENT", "JUDGEMENT"]),
                )
            )
        ).scalars().all()
        existing_ids = {s.criterion_id for s in existing}
        covered = provided | existing_ids
        # Marks in payload replace; if payload omits a criterion that was never scored → incomplete
        # If payload is partial finalize, only payload + prior counts; but empty overwrites? 
        # Spec: all criteria complete before finalise. Use union of payload marks (must include all).
        if required_ids - provided:
            missing = sorted(required_ids - provided)
            raise AppError(
                "SCORE_INCOMPLETE",
                "All criteria must be marked before finalise",
                status_code=409,
                fields=[FieldError(c, "SCORE_INCOMPLETE") for c in missing],
            )

    status_value = "FINAL" if payload.finalize else "DRAFT"
    saved_marks: list[Score] = []

    for mark in payload.criterionMarks:
        score_type = mark.type.upper()
        existing = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == submission_id,
                    Score.assessor_id == actor.id,
                    Score.criterion_id == mark.criterionId,
                    Score.score_type == score_type,
                )
            )
        ).scalar_one_or_none()
        judge_id = mark.judgeId or actor.id
        if existing is None:
            existing = Score(
                submission_id=submission_id,
                assessor_id=actor.id,
                criterion_id=mark.criterionId,
                score_type=score_type,
            )
            session.add(existing)
        existing.raw = mark.value
        existing.comment = mark.comment
        existing.judge_id = judge_id
        existing.status = status_value
        saved_marks.append(existing)

    saved_pens: list[Score] = []
    for pen in payload.penalties:
        cfg = penalties_cfg[pen.code]
        deduction = pen.deduction if pen.deduction is not None else int(cfg.get("deduction", 0))
        existing = (
            await session.execute(
                select(Score).where(
                    Score.submission_id == submission_id,
                    Score.assessor_id == actor.id,
                    Score.criterion_id == pen.code,
                    Score.score_type == "PENALTY",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Score(
                submission_id=submission_id,
                assessor_id=actor.id,
                criterion_id=pen.code,
                score_type="PENALTY",
            )
            session.add(existing)
        existing.raw = -deduction
        existing.penalty = deduction
        existing.status = status_value
        existing.comment = f"Penalty {pen.code}"
        saved_pens.append(existing)

    await session.flush()

    # Running totals for this assessor + whole submission
    my_criterion = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.assessor_id == actor.id,
                Score.score_type.in_(["MEASUREMENT", "JUDGEMENT"]),
            )
        )
    ).scalars().all()
    my_pens = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.assessor_id == actor.id,
                Score.score_type == "PENALTY",
            )
        )
    ).scalars().all()
    assessor_total = compute_assessor_total(list(my_criterion), list(my_pens))

    all_scores = (
        await session.execute(select(Score).where(Score.submission_id == submission_id))
    ).scalars().all()
    submission.score_total = compute_submission_total(list(all_scores))
    if submission.state == "ACCEPTED" and payload.finalize:
        submission.state = "ACCEPTED"  # keep; SCORED transition optional for ASM-03

    await write_audit_event(
        session,
        action="SCORE_SAVE",
        entity_type="Submission",
        entity_id=str(submission.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=submission.competition_id,
        after={
            "finalize": payload.finalize,
            "assessorTotal": assessor_total,
            "submissionTotal": submission.score_total,
            "marks": [
                {"criterionId": m.criterionId, "type": m.type, "value": m.value}
                for m in payload.criterionMarks
            ],
            "penalties": [{"code": p.code, "deduction": p.deduction} for p in payload.penalties],
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return ScorePutOut(
        total=assessor_total,
        status=status_value,
        breakdown=BreakdownOut(
            marks=[
                ScoreMarkOut(
                    criterionId=s.criterion_id,
                    type=s.score_type,
                    value=s.raw,
                    assessorId=s.assessor_id,
                    judgeId=s.judge_id,
                    comment=s.comment,
                    status=s.status,
                )
                for s in my_criterion
            ],
            penalties=[
                PenaltyOut(code=p.criterion_id, deduction=int(p.penalty or 0)) for p in my_pens
            ],
            total=assessor_total,
        ),
    )
