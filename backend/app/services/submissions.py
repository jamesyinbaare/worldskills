"""US-SUB-02 — competitor submission with scanning, deadlines, resumable uploads."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Artefact, Competitor, Exercise, Stage, Submission, User
from app.services.audit import write_audit_event
from app.services.exercises import deliverables_to_submission_rules
from app.services.stages import assert_stage_available
from app.services.storage import ObjectStorage, ScanResult, get_object_storage


IMMUTABLE_STATES = {"ACCEPTED", "LATE", "ACCEPTED_PENDING_SCAN"}


def _utcnow() -> datetime:
    return datetime.utcnow()


async def _rules(session: AsyncSession, stage: Stage) -> dict[str, Any]:
    ex = (
        await session.execute(select(Exercise).where(Exercise.stage_id == stage.id))
    ).scalar_one_or_none()
    if ex is not None:
        if ex.status != "PUBLISHED":
            raise AppError(
                "EXERCISE_NOT_PUBLISHED",
                "Exercise for this stage is not published",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("exercise", "EXERCISE_NOT_PUBLISHED")],
            )
        rules = deliverables_to_submission_rules(ex)
        if not rules.get("requiredDeliverables"):
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Published Exercise has no required deliverables",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("deliverables", "CONFIG_INCOMPLETE")],
            )
        return rules
    if not stage.submission_rules or not isinstance(stage.submission_rules, dict):
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Stage submission_rules are not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("submission_rules", "CONFIG_INCOMPLETE")],
        )
    required = stage.submission_rules.get("requiredDeliverables")
    if not required:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Stage has no requiredDeliverables",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("requiredDeliverables", "CONFIG_INCOMPLETE")],
        )
    return stage.submission_rules


def _deliverable_rule(rules: dict[str, Any], code: str) -> dict[str, Any]:
    for item in rules.get("requiredDeliverables") or []:
        if item.get("code") == code:
            return item
    raise AppError(
        "DELIVERABLE_UNKNOWN",
        f"Unknown deliverable '{code}'",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        fields=[FieldError("deliverableCode", "DELIVERABLE_UNKNOWN")],
    )


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _validate_file_against_rule(rule: dict[str, Any], *, filename: str, size: int) -> None:
    formats = [str(f).lower() for f in (rule.get("formats") or [])]
    ext = _extension(filename)
    if formats and ext not in formats:
        raise AppError(
            "FILE_TYPE",
            f"File type '.{ext}' is not allowed for {rule.get('code')}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("filename", "FILE_TYPE")],
        )
    max_mb = rule.get("maxMb")
    if max_mb is not None and size > int(max_mb) * 1024 * 1024:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds {max_mb}MB limit",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("size", "FILE_TOO_LARGE")],
        )


async def _load_owned_submission(
    session: AsyncSession, submission_id: uuid.UUID, actor: User
) -> tuple[Submission, Competitor, Stage]:
    result = await session.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND", "Submission not found", status_code=404)

    comp_result = await session.execute(
        select(Competitor).where(Competitor.id == submission.competitor_id)
    )
    competitor = comp_result.scalar_one()
    if competitor.user_id != actor.id:
        raise AppError("FORBIDDEN", "Not your submission", status_code=403)

    if submission.stage_id is None:
        raise AppError("CONFIG_INCOMPLETE", "Submission has no stage", status_code=409)

    stage = await session.get(Stage, submission.stage_id)
    if stage is None:
        raise AppError("CONFIG_INCOMPLETE", "Stage missing", status_code=409)
    return submission, competitor, stage


def _assert_uploadable(submission: Submission) -> None:
    if submission.upload_locked or submission.state in IMMUTABLE_STATES:
        raise AppError(
            "SUBMISSION_LOCKED",
            "Submission is locked; further uploads are blocked",
            status_code=status.HTTP_409_CONFLICT,
        )


def _effective_deadline(stage: Stage, submission: Submission, rules: dict[str, Any]) -> datetime:
    deadline = submission.deadline_at or stage.closes_at
    if submission.timed_expires_at and (
        deadline is None or submission.timed_expires_at < deadline
    ):
        deadline = submission.timed_expires_at
    if deadline is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Stage/submission deadline is not configured",
            status_code=409,
            fields=[FieldError("closesAt", "CONFIG_INCOMPLETE")],
        )
    return deadline


def _deadline_status(
    stage: Stage, submission: Submission, *, now: datetime, rules: dict[str, Any]
) -> str:
    """Return 'ok', 'block', or 'flag' based on closesAt / timed expiry and late policy."""
    policy = str(rules.get("latePolicy") or "block").lower()
    deadline = _effective_deadline(stage, submission, rules)
    if now <= deadline:
        return "ok"
    if policy in {"flag-late", "flag_late", "flag"}:
        return "flag"
    return "block"


def _compute_content_hash(artefacts: list[Artefact]) -> str:
    parts = sorted(
        f"{a.deliverable_code}:{a.sha256 or ''}" for a in artefacts if a.complete and not a.quarantined
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def open_submission(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Submission:
    stage = await session.get(Stage, stage_id)
    if stage is None or stage.competition_id != competition_id:
        raise AppError("STAGE_NOT_FOUND", "Stage not found in cycle", status_code=404)
    rules = await _rules(session, stage)

    comp_result = await session.execute(
        select(Competitor).where(Competitor.user_id == actor.id, Competitor.competition_id == competition_id)
    )
    competitor = comp_result.scalar_one_or_none()
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "No competitor bound to this account", status_code=404)
    if stage.skill_id is not None and competitor.skill_id != stage.skill_id:
        raise AppError(
            "FORBIDDEN",
            "Stage is not part of your skill pathway",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if competitor.eligibility_status not in {None, "ELIGIBLE", "OPEN_CATEGORY"}:
        if competitor.eligibility_status == "INELIGIBLE":
            raise AppError("INELIGIBLE", "Competitor is not eligible", status_code=409)
    if competitor.status not in {
        "REGISTERED",
        "ACTIVE_IN_STAGE",
        "PENDING_REVIEW",
        "CONSENT_PENDING",
    }:
        # Allow REGISTERED / ACTIVE_IN_STAGE / PENDING_REVIEW / legacy CONSENT_PENDING
        if competitor.status == "INELIGIBLE":
            raise AppError("INELIGIBLE", "Competitor cannot submit", status_code=409)

    existing = await session.execute(
        select(Submission).where(
            Submission.competitor_id == competitor.id, Submission.stage_id == stage_id
        )
    )
    prior = existing.scalar_one_or_none()
    if prior is not None:
        return prior

    now = _utcnow()
    assert_stage_available(stage, now=now)
    timed_seconds = rules.get("timedDurationSeconds")
    timed_started = now if timed_seconds else None
    timed_expires = (now + timedelta(seconds=int(timed_seconds))) if timed_seconds else None

    submission = Submission(
        competition_id=competition_id,
        competitor_id=competitor.id,
        stage_id=stage_id,
        state="OPEN",
        deadline_at=stage.closes_at,
        timed_started_at=timed_started,
        timed_expires_at=timed_expires,
        upload_locked=False,
        late=False,
    )
    session.add(submission)
    await session.flush()

    if competitor.status == "REGISTERED":
        competitor.status = "ACTIVE_IN_STAGE"

    await write_audit_event(
        session,
        action="SUBMISSION_OPEN",
        entity_type="Submission",
        entity_id=str(submission.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after={
            "state": submission.state,
            "stageId": str(stage_id),
            "deadlineAt": submission.deadline_at.isoformat() if submission.deadline_at else None,
            "timedExpiresAt": (
                submission.timed_expires_at.isoformat() if submission.timed_expires_at else None
            ),
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(submission)
    return submission


async def upload_artefact(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    deliverable_code: str,
    filename: str,
    content_type: str | None,
    data: bytes,
    storage: ObjectStorage | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Artefact:
    submission, _competitor, stage = await _load_owned_submission(session, submission_id, actor)
    _assert_uploadable(submission)

    # Auto-expire timed projects that are past timer
    now = _utcnow()
    if submission.timed_expires_at and now >= submission.timed_expires_at:
        raise AppError(
            "DEADLINE_PASSED",
            "Timed project has expired; use finalise / timer capture",
            status_code=409,
        )

    rules = await _rules(session, stage)
    rule = _deliverable_rule(rules, deliverable_code)
    _validate_file_against_rule(rule, filename=filename, size=len(data))

    store = storage or get_object_storage()
    stored, scan = store.put_raw(
        data,
        prefix=f"submissions/{submission_id}/{deliverable_code}",
        filename=filename,
    )

    # Replace prior complete artefact for same deliverable code
    prior = (
        await session.execute(
            select(Artefact).where(
                Artefact.submission_id == submission_id,
                Artefact.deliverable_code == deliverable_code,
                Artefact.complete.is_(True),
            )
        )
    ).scalars().all()
    for old in prior:
        await session.delete(old)

    artefact = Artefact(
        submission_id=submission_id,
        deliverable_code=deliverable_code,
        filename=filename,
        content_type=content_type,
        size=stored.size,
        storage_key=stored.key,
        sha256=stored.sha256,
        scan_status="INFECTED" if scan == ScanResult.INFECTED else "CLEAN",
        quarantined=scan == ScanResult.INFECTED,
        complete=True,
        received_bytes=stored.size,
        total_size=stored.size,
        completed_at=_utcnow() if scan != ScanResult.INFECTED else None,
    )
    session.add(artefact)

    if scan == ScanResult.INFECTED:
        submission.state = "QUARANTINED"
        await session.flush()
        await write_audit_event(
            session,
            action="ARTEFACT_QUARANTINED",
            entity_type="Artefact",
            entity_id=str(artefact.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=submission.competition_id,
            after={"deliverableCode": deliverable_code, "scan": "INFECTED"},
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "FILE_INFECTED",
            "File failed malware scan and was quarantined; replace it",
            status_code=400,
            fields=[FieldError(deliverable_code, "FILE_INFECTED")],
        )

    if submission.state in {"OPEN", "QUARANTINED"}:
        submission.state = "UPLOADED"
    await session.flush()
    await write_audit_event(
        session,
        action="ARTEFACT_UPLOAD",
        entity_type="Artefact",
        entity_id=str(artefact.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=submission.competition_id,
        after={"deliverableCode": deliverable_code, "scan": artefact.scan_status, "sha256": artefact.sha256},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(artefact)
    return artefact


async def init_resumable_upload(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    deliverable_code: str,
    filename: str,
    content_type: str | None,
    total_size: int,
    storage: ObjectStorage | None = None,
) -> Artefact:
    submission, _competitor, stage = await _load_owned_submission(session, submission_id, actor)
    _assert_uploadable(submission)
    rules = await _rules(session, stage)
    rule = _deliverable_rule(rules, deliverable_code)
    _validate_file_against_rule(rule, filename=filename, size=total_size)

    store = storage or get_object_storage()
    upload_id = secrets.token_hex(16)
    key = f"submissions/{submission_id}/{deliverable_code}/partial-{upload_id}"
    # Touch empty partial file
    path = store.root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")

    artefact = Artefact(
        submission_id=submission_id,
        deliverable_code=deliverable_code,
        filename=filename,
        content_type=content_type,
        size=0,
        storage_key=key,
        scan_status="PENDING",
        quarantined=False,
        upload_id=upload_id,
        total_size=total_size,
        received_bytes=0,
        complete=False,
    )
    session.add(artefact)
    await session.commit()
    await session.refresh(artefact)
    return artefact


async def append_resumable_chunk(
    session: AsyncSession,
    submission_id: uuid.UUID,
    upload_id: str,
    *,
    actor: User,
    data: bytes,
    content_range: str | None,
    storage: ObjectStorage | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Artefact:
    submission, _competitor, stage = await _load_owned_submission(session, submission_id, actor)
    _assert_uploadable(submission)

    result = await session.execute(
        select(Artefact).where(
            Artefact.submission_id == submission_id,
            Artefact.upload_id == upload_id,
        )
    )
    artefact = result.scalar_one_or_none()
    if artefact is None:
        raise AppError("UPLOAD_NOT_FOUND", "Resumable upload session not found", status_code=404)
    if artefact.complete:
        return artefact

    offset = artefact.received_bytes
    if content_range:
        # bytes start-end/total
        try:
            unit, rng = content_range.split(" ", 1)
            if unit.lower() != "bytes":
                raise ValueError
            span, total = rng.split("/")
            start_s, end_s = span.split("-")
            start = int(start_s)
            end = int(end_s)
            total_i = int(total)
            if artefact.total_size and total_i != artefact.total_size:
                raise AppError("UPLOAD_SIZE_MISMATCH", "totalSize mismatch", status_code=409)
            if start != offset:
                # Allow resume from last offset — tell client where we are
                raise AppError(
                    "UPLOAD_OFFSET_MISMATCH",
                    f"Resume from byte {offset}",
                    status_code=409,
                    fields=[FieldError("Content-Range", f"EXPECTED_{offset}")],
                )
            if end - start + 1 != len(data):
                raise AppError("UPLOAD_CHUNK_SIZE", "Chunk size does not match Content-Range", status_code=422)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid Content-Range",
                status_code=422,
                fields=[FieldError("Content-Range", "INVALID")],
            ) from exc

    store = storage or get_object_storage()
    assert artefact.storage_key is not None
    new_offset = store.append_chunk(artefact.storage_key, data, expected_offset=offset)
    artefact.received_bytes = new_offset
    artefact.size = new_offset

    if artefact.total_size is not None and new_offset >= artefact.total_size:
        # Finalise chunked file: scan then mark complete
        raw = store.get(artefact.storage_key)
        scan = store.scanner.scan(raw)
        artefact.sha256 = hashlib.sha256(raw).hexdigest()
        artefact.complete = True
        artefact.completed_at = _utcnow()
        if scan == ScanResult.INFECTED:
            # Move to quarantine prefix
            q_key = f"quarantine/{artefact.storage_key}"
            q_path = store.root / q_key
            q_path.parent.mkdir(parents=True, exist_ok=True)
            q_path.write_bytes(raw)
            store.delete(artefact.storage_key)
            artefact.storage_key = q_key
            artefact.scan_status = "INFECTED"
            artefact.quarantined = True
            submission.state = "QUARANTINED"
            await session.flush()
            await write_audit_event(
                session,
                action="ARTEFACT_QUARANTINED",
                entity_type="Artefact",
                entity_id=str(artefact.id),
                actor_id=actor.id,
                actor_role=actor.role.value,
                competition_id=submission.competition_id,
                after={"scan": "INFECTED", "uploadId": upload_id},
                ip=ip,
                user_agent=user_agent,
            )
            await session.commit()
            raise AppError(
                "FILE_INFECTED",
                "File failed malware scan and was quarantined; replace it",
                status_code=400,
            )
        artefact.scan_status = "CLEAN"
        # Replace prior completes for same code
        priors = (
            await session.execute(
                select(Artefact).where(
                    Artefact.submission_id == submission_id,
                    Artefact.deliverable_code == artefact.deliverable_code,
                    Artefact.complete.is_(True),
                    Artefact.id != artefact.id,
                )
            )
        ).scalars().all()
        for old in priors:
            await session.delete(old)
        if submission.state in {"OPEN", "QUARANTINED"}:
            submission.state = "UPLOADED"
        await write_audit_event(
            session,
            action="ARTEFACT_UPLOAD",
            entity_type="Artefact",
            entity_id=str(artefact.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=submission.competition_id,
            after={"scan": "CLEAN", "uploadId": upload_id, "sha256": artefact.sha256},
            ip=ip,
            user_agent=user_agent,
        )

    await session.commit()
    await session.refresh(artefact)
    return artefact


async def finalise_submission(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    force_timer: bool = False,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Submission:
    submission, _competitor, stage = await _load_owned_submission(session, submission_id, actor)
    if submission.state in {"ACCEPTED", "LATE"} and submission.content_hash:
        return submission  # idempotent

    now = _utcnow()
    rules = await _rules(session, stage)

    # Timed auto-capture path
    timer_expired = bool(
        submission.timed_expires_at and now >= submission.timed_expires_at
    )
    if force_timer or timer_expired:
        submission.upload_locked = True

    deadline_mode = _deadline_status(stage, submission, now=now, rules=rules)
    if deadline_mode == "block" and not (force_timer or timer_expired):
        # Timer-expiry finalise is allowed even when block policy (capture what's there)
        raise AppError(
            "DEADLINE_PASSED",
            "Submission deadline has passed",
            status_code=409,
            fields=[FieldError("deadline", "DEADLINE_PASSED")],
        )

    artefacts = (
        await session.execute(
            select(Artefact).where(
                Artefact.submission_id == submission_id,
                Artefact.complete.is_(True),
            )
        )
    ).scalars().all()

    if any(a.quarantined or a.scan_status == "INFECTED" for a in artefacts):
        submission.state = "QUARANTINED"
        await session.commit()
        raise AppError(
            "FILE_INFECTED",
            "Replace quarantined artefacts before finalising",
            status_code=409,
            fields=[FieldError("artefacts", "FILE_INFECTED")],
        )

    pending = [a for a in artefacts if a.scan_status == "PENDING"]
    clean = [a for a in artefacts if a.scan_status == "CLEAN" and not a.quarantined]

    required_codes = [d["code"] for d in rules["requiredDeliverables"]]
    present = {a.deliverable_code for a in clean}
    missing = [c for c in required_codes if c not in present]

    if missing and not (force_timer or timer_expired):
        raise AppError(
            "DELIVERABLE_MISSING",
            "Required deliverables are missing",
            status_code=409,
            fields=[FieldError(code, "DELIVERABLE_MISSING") for code in missing],
        )

    # Edge: scan pending at deadline → ACCEPTED_PENDING_SCAN
    if pending and (deadline_mode != "ok" or force_timer or timer_expired):
        submission.state = "ACCEPTED_PENDING_SCAN"
        submission.submitted_at = now
        submission.upload_locked = True
        submission.late = deadline_mode == "flag" or (
            deadline_mode == "block" and (force_timer or timer_expired)
        )
        submission.receipt = secrets.token_hex(8).upper()
        submission.content_hash = _compute_content_hash(list(clean) + list(pending))
        await write_audit_event(
            session,
            action="SUBMISSION_FINALISE",
            entity_type="Submission",
            entity_id=str(submission.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=submission.competition_id,
            after={"state": submission.state, "hash": submission.content_hash, "receipt": submission.receipt},
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        await session.refresh(submission)
        return submission

    if missing and (force_timer or timer_expired):
        # Capture whatever is present on timer expiry (may be incomplete)
        pass
    elif missing:
        raise AppError(
            "DELIVERABLE_MISSING",
            "Required deliverables are missing",
            status_code=409,
            fields=[FieldError(code, "DELIVERABLE_MISSING") for code in missing],
        )

    content_hash = _compute_content_hash(list(clean))
    if not content_hash or (not clean and not (force_timer or timer_expired)):
        raise AppError(
            "INTEGRITY_FAILED",
            "Unable to hash submission contents",
            status_code=409,
            fields=[FieldError("hash", "INTEGRITY_FAILED")],
        )

    submission.content_hash = content_hash
    submission.submitted_at = now
    submission.upload_locked = True
    submission.receipt = secrets.token_hex(8).upper()
    if deadline_mode == "flag":
        submission.late = True
        submission.state = "LATE"
    else:
        submission.late = False
        submission.state = "ACCEPTED"

    await write_audit_event(
        session,
        action="SUBMISSION_FINALISE",
        entity_type="Submission",
        entity_id=str(submission.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=submission.competition_id,
        before={"state": "UPLOADED"},
        after={
            "state": submission.state,
            "hash": submission.content_hash,
            "receipt": submission.receipt,
            "late": submission.late,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(submission)
    return submission


async def reopen_submission(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Submission:
    """Allow replacing artefacts and re-finalising while the deadline is still open."""
    submission, _competitor, stage = await _load_owned_submission(session, submission_id, actor)
    now = _utcnow()
    rules = await _rules(session, stage)

    if submission.timed_expires_at and now >= submission.timed_expires_at:
        raise AppError(
            "DEADLINE_PASSED",
            "Timed project has expired; submission cannot be reopened",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("timedExpiresAt", "DEADLINE_PASSED")],
        )

    if _deadline_status(stage, submission, now=now, rules=rules) != "ok":
        raise AppError(
            "DEADLINE_PASSED",
            "Submission deadline has passed; submission cannot be reopened",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("deadline", "DEADLINE_PASSED")],
        )

    if not submission.upload_locked and submission.state not in IMMUTABLE_STATES:
        return submission

    before = {
        "state": submission.state,
        "uploadLocked": submission.upload_locked,
        "receipt": submission.receipt,
        "hash": submission.content_hash,
    }

    artefacts = (
        await session.execute(
            select(Artefact).where(
                Artefact.submission_id == submission_id,
                Artefact.complete.is_(True),
            )
        )
    ).scalars().all()
    has_clean = any(
        a.scan_status == "CLEAN" and not a.quarantined for a in artefacts
    )

    submission.upload_locked = False
    submission.late = False
    submission.state = "UPLOADED" if has_clean else "OPEN"
    # Keep prior receipt/hash visible until the next finalise replaces them.
    await write_audit_event(
        session,
        action="SUBMISSION_REOPEN",
        entity_type="Submission",
        entity_id=str(submission.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=submission.competition_id,
        before=before,
        after={
            "state": submission.state,
            "uploadLocked": False,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(submission)
    return submission


async def expire_timer(
    session: AsyncSession,
    submission_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Submission:
    """AC5 — capture current artefacts and lock further uploads."""
    submission, _c, _s = await _load_owned_submission(session, submission_id, actor)
    now = _utcnow()
    if submission.timed_expires_at and now < submission.timed_expires_at:
        # Allow tests to force-expire by setting expires in the past; otherwise require expiry
        raise AppError(
            "TIMER_ACTIVE",
            "Timed project has not expired yet",
            status_code=409,
        )
    submission.upload_locked = True
    return await finalise_submission(
        session, submission_id, actor=actor, force_timer=True, ip=ip, user_agent=user_agent
    )
