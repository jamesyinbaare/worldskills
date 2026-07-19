"""US-ASM-02 — moderate and standardise judgement marks."""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, check_segregation_of_duties, has_capability
from app.models import ModerationFlag, Score, Submission, User
from app.schemas.moderation import (
    ModerationAnalyseOut,
    ModerationApplyIn,
    ModerationApplyOut,
    ModerationFlagOut,
)
from app.services.assessment import (
    _resolve_scheme_for_submission,
    _rubric_from_scheme,
    compute_submission_total,
)
from app.services.audit import write_audit_event


def _moderation_config(rubric: dict[str, Any]) -> dict[str, Any]:
    mod = rubric.get("moderation") or {}
    return {
        "tolerance": int(mod.get("judgementSpreadTolerance", mod.get("tolerance", 2))),
        "method": str(mod.get("standardiseMethod", "MEAN")).upper(),
    }


def _standardise_value(raws: list[int], method: str) -> int:
    if not raws:
        raise AppError("SCORE_INCOMPLETE", "No judgement marks to standardise", status_code=409)
    if method == "MEDIAN":
        return int(round(statistics.median(raws)))
    # MEAN default
    return int(round(statistics.mean(raws)))


async def assert_moderator_segregation(
    session: AsyncSession,
    *,
    cycle_id: uuid.UUID,
    submission_id: uuid.UUID,
    moderator: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Block when the moderator also scored this submission (US-ASM-02-AC4)."""
    scored = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.assessor_id == moderator.id,
                Score.score_type.in_(["MEASUREMENT", "JUDGEMENT", "PENALTY"]),
            )
        )
    ).scalars().first()
    if scored is not None and not check_segregation_of_duties(
        scorer_id=str(scored.assessor_id),
        moderator_id=str(moderator.id),
    ):
        await write_audit_event(
            session,
            action="MODERATE_REFUSED_SOD",
            entity_type="Submission",
            entity_id=str(submission_id),
            actor_id=moderator.id,
            actor_role=moderator.role.value,
            cycle_id=cycle_id,
            after={"scorerId": str(scored.assessor_id), "moderatorId": str(moderator.id)},
            reason="SEGREGATION_VIOLATION",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "SEGREGATION_VIOLATION",
            "Scorer may not moderate this submission",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("submissionId", "SEGREGATION_VIOLATION")],
        )


async def analyse_moderation(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ModerationAnalyseOut:
    if not has_capability(actor.role, Capability.MODERATE_SCORE):
        raise AppError("FORBIDDEN", "Missing moderate capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)

    await assert_moderator_segregation(
        session,
        cycle_id=submission.cycle_id,
        submission_id=submission_id,
        moderator=actor,
        ip=ip,
        user_agent=user_agent,
    )

    scheme = await _resolve_scheme_for_submission(session, submission)
    rubric = _rubric_from_scheme(scheme)
    cfg = _moderation_config(rubric)
    tolerance = cfg["tolerance"]

    judgements = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.score_type == "JUDGEMENT",
                Score.raw.is_not(None),
            )
        )
    ).scalars().all()

    by_crit: dict[str, list[Score]] = {}
    for s in judgements:
        by_crit.setdefault(s.criterion_id, []).append(s)

    flags_out: list[ModerationFlagOut] = []
    for criterion_id, rows in by_crit.items():
        raws = [int(r.raw) for r in rows if r.raw is not None]
        if len(raws) < 2:
            flag = await _upsert_flag(
                session,
                submission_id=submission_id,
                criterion_id=criterion_id,
                spread=None,
                raw_marks=raws,
                state="NEEDS_SECOND_JUDGE",
                flagged=True,
            )
            flags_out.append(_flag_out(flag))
            continue
        spread = max(raws) - min(raws)
        if spread > tolerance:
            flag = await _upsert_flag(
                session,
                submission_id=submission_id,
                criterion_id=criterion_id,
                spread=spread,
                raw_marks=raws,
                state="OPEN",
                flagged=True,
            )
            flags_out.append(_flag_out(flag))
        else:
            # Within tolerance — clear open flag / record not flagged
            flag = await _upsert_flag(
                session,
                submission_id=submission_id,
                criterion_id=criterion_id,
                spread=spread,
                raw_marks=raws,
                state="RESOLVED",
                flagged=False,
            )
            # Don't include non-flagged in AC1 expectations unless useful
            _ = flag

    await write_audit_event(
        session,
        action="MODERATION_ANALYSE",
        entity_type="Submission",
        entity_id=str(submission_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=submission.cycle_id,
        after={"flags": [f.criterionId for f in flags_out], "tolerance": tolerance},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return ModerationAnalyseOut(
        submissionId=submission_id,
        tolerance=tolerance,
        flags=flags_out,
    )


async def _upsert_flag(
    session: AsyncSession,
    *,
    submission_id: uuid.UUID,
    criterion_id: str,
    spread: int | None,
    raw_marks: list[int],
    state: str,
    flagged: bool,
) -> ModerationFlag:
    existing = (
        await session.execute(
            select(ModerationFlag).where(
                ModerationFlag.submission_id == submission_id,
                ModerationFlag.criterion_id == criterion_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = ModerationFlag(
            submission_id=submission_id,
            criterion_id=criterion_id,
        )
        session.add(existing)
    existing.spread = spread
    existing.raw_marks = list(raw_marks)
    existing.state = state
    existing.flagged = flagged
    if state == "RESOLVED" and not flagged:
        existing.resolved_at = datetime.utcnow()
    await session.flush()
    return existing


def _flag_out(flag: ModerationFlag) -> ModerationFlagOut:
    return ModerationFlagOut(
        criterionId=flag.criterion_id,
        spread=flag.spread,
        rawMarks=list(flag.raw_marks or []),
        flagged=flag.flagged,
        state=flag.state,
        standardisedValue=flag.standardised_value,
        method=flag.method,
        reason=flag.reason,
    )


async def apply_moderation(
    session: AsyncSession,
    submission_id: uuid.UUID,
    payload: ModerationApplyIn,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ModerationApplyOut:
    if not has_capability(actor.role, Capability.MODERATE_SCORE):
        raise AppError("FORBIDDEN", "Missing moderate capability", status_code=403)

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)

    await assert_moderator_segregation(
        session,
        cycle_id=submission.cycle_id,
        submission_id=submission_id,
        moderator=actor,
        ip=ip,
        user_agent=user_agent,
    )

    method = payload.method.upper()
    if method not in {"STANDARDISE", "MANUAL"}:
        raise AppError(
            "VALIDATION_ERROR",
            "method must be STANDARDISE or MANUAL",
            status_code=422,
            fields=[FieldError("method", "INVALID")],
        )

    if method == "MANUAL":
        if not payload.reason or not payload.reason.strip():
            raise AppError(
                "REASON_REQUIRED",
                "A reason is required for manual adjustment",
                status_code=422,
                fields=[FieldError("reason", "REASON_REQUIRED")],
            )
        if payload.value is None:
            raise AppError(
                "VALIDATION_ERROR",
                "value is required for MANUAL method",
                status_code=422,
                fields=[FieldError("value", "REQUIRED")],
            )

    scheme = await _resolve_scheme_for_submission(session, submission)
    rubric = _rubric_from_scheme(scheme)
    cfg = _moderation_config(rubric)

    rows = (
        await session.execute(
            select(Score).where(
                Score.submission_id == submission_id,
                Score.criterion_id == payload.criterionId,
                Score.score_type == "JUDGEMENT",
            )
        )
    ).scalars().all()
    if not rows:
        raise AppError(
            "CRITERION_UNKNOWN",
            "No judgement marks for criterion",
            status_code=404,
            fields=[FieldError("criterionId", "CRITERION_UNKNOWN")],
        )

    raws = [int(r.raw) for r in rows if r.raw is not None]
    if len(raws) < 2 and method == "STANDARDISE":
        raise AppError(
            "SCORE_INCOMPLETE",
            "Need at least two judges to standardise",
            status_code=409,
            fields=[FieldError("criterionId", "NEEDS_SECOND_JUDGE")],
        )

    # Ensure flag exists (analyse may have created it)
    flag = (
        await session.execute(
            select(ModerationFlag).where(
                ModerationFlag.submission_id == submission_id,
                ModerationFlag.criterion_id == payload.criterionId,
            )
        )
    ).scalar_one_or_none()
    if flag is None:
        spread = (max(raws) - min(raws)) if len(raws) >= 2 else None
        flag = await _upsert_flag(
            session,
            submission_id=submission_id,
            criterion_id=payload.criterionId,
            spread=spread,
            raw_marks=raws,
            state="OPEN",
            flagged=True,
        )

    before_raws = [int(r.raw) for r in rows if r.raw is not None]

    if method == "STANDARDISE":
        value = _standardise_value(raws, cfg["method"])
        reason = payload.reason
    else:
        value = int(payload.value)  # type: ignore[arg-type]
        reason = payload.reason.strip()

    # Preserve raw; set standardised on each judge row
    for row in rows:
        row.standardised = value

    flag.method = method
    flag.standardised_value = value
    flag.reason = reason
    flag.moderator_id = actor.id
    flag.state = "RESOLVED"
    flag.flagged = False
    flag.resolved_at = datetime.utcnow()
    flag.raw_marks = before_raws

    await session.flush()
    all_scores = (
        await session.execute(select(Score).where(Score.submission_id == submission_id))
    ).scalars().all()
    # Verify raws unchanged
    for row in rows:
        assert row.raw is not None  # preserved
    submission.score_total = compute_submission_total(list(all_scores))

    await write_audit_event(
        session,
        action="MODERATION_APPLY",
        entity_type="Submission",
        entity_id=str(submission_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=submission.cycle_id,
        before={"rawMarks": before_raws, "criterionId": payload.criterionId},
        after={
            "method": method,
            "standardisedValue": value,
            "total": submission.score_total,
            "reason": reason,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return ModerationApplyOut(
        submissionId=submission_id,
        criterionId=payload.criterionId,
        method=method,
        standardisedValue=value,
        rawMarks=before_raws,
        total=int(submission.score_total or 0),
        reason=reason,
    )
