"""US-AUD-01 — audit query, append-only enforcement, DSAR processing."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import Select, or_, select
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import is_admin_role
from app.models import AuditEvent, Competitor, DsarJob, User, UserRole
from app.schemas.governance import AuditEventOut, AuditListOut, DsarJobOut
from app.services.audit import verify_audit_signature, write_audit_event


def _forbid_audit_mutation(mapper, connection, target: AuditEvent) -> None:  # noqa: ANN001, ARG001
    raise AppError(
        "AUDIT_IMMUTABLE",
        "Audit events are append-only and cannot be modified or deleted",
        status_code=status.HTTP_409_CONFLICT,
    )


sa_event.listen(AuditEvent, "before_update", _forbid_audit_mutation)
sa_event.listen(AuditEvent, "before_delete", _forbid_audit_mutation)


def _event_out(event: AuditEvent, *, include_sig_check: bool = True) -> AuditEventOut:
    return AuditEventOut(
        eventId=event.id,
        competitionId=event.competition_id,
        actorId=event.actor_id,
        actorRole=event.actor_role,
        action=event.action,
        entityType=event.entity_type,
        entityId=event.entity_id,
        before=event.before,
        after=event.after,
        reason=event.reason,
        timestamp=event.timestamp,
        signatureValid=verify_audit_signature(event) if include_sig_check else None,
    )


def _as_uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def list_audit_events(
    session: AsyncSession,
    *,
    entity: str | None = None,
    actor: uuid.UUID | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 100,
) -> AuditListOut:
    stmt: Select[tuple[AuditEvent]] = select(AuditEvent).order_by(AuditEvent.timestamp.desc())
    if entity:
        entity_uuid = _as_uuid_or_none(entity)
        if entity_uuid is not None:
            stmt = stmt.where(
                or_(AuditEvent.entity_id == entity, AuditEvent.competition_id == entity_uuid)
            )
        else:
            stmt = stmt.where(AuditEvent.entity_id == entity)
    if actor is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor)
    if from_ts is not None:
        stmt = stmt.where(AuditEvent.timestamp >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditEvent.timestamp <= to_ts)
    stmt = stmt.limit(min(max(limit, 1), 500))
    rows = list((await session.execute(stmt)).scalars().all())
    return AuditListOut(events=[_event_out(r) for r in rows])


async def refuse_audit_mutation(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    await write_audit_event(
        session,
        action="AUDIT_TAMPER_ATTEMPT",
        entity_type="AuditEvent",
        entity_id=str(event_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        after={"attempt": "mutate_or_delete"},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    raise AppError(
        "AUDIT_IMMUTABLE",
        "Audit events are append-only and cannot be modified or deleted",
        status_code=status.HTTP_409_CONFLICT,
    )


def _assert_subject_verified(actor: User, competitor: Competitor) -> None:
    if is_admin_role(actor.role):
        return
    if actor.role == UserRole.COMPETITOR and competitor.user_id == actor.id:
        return
    raise AppError(
        "SUBJECT_UNVERIFIED",
        "Caller is not a verified data subject for this record",
        status_code=status.HTTP_403_FORBIDDEN,
        fields=[FieldError("subjectId", "SUBJECT_UNVERIFIED")],
    )


def _export_competitor(competitor: Competitor) -> dict[str, Any]:
    return {
        "competitorId": str(competitor.id),
        "competitionId": str(competitor.competition_id),
        "refNo": competitor.ref_no,
        "status": competitor.status,
        "givenNames": competitor.given_names,
        "familyName": competitor.family_name,
        "dateOfBirth": competitor.date_of_birth.isoformat() if competitor.date_of_birth else None,
        "email": competitor.email,
        "mobile": competitor.mobile,
        "whatsapp": competitor.whatsapp,
        "nationalId": competitor.national_id,
        "photoKey": competitor.photo_key,
        "guardianName": competitor.guardian_name,
        "guardianEmail": competitor.guardian_email,
        "guardianPhone": competitor.guardian_phone,
        "consentParticipationAt": (
            competitor.consent_participation_at.isoformat()
            if competitor.consent_participation_at
            else None
        ),
        "consentPublicAt": (
            competitor.consent_public_at.isoformat() if competitor.consent_public_at else None
        ),
        "publicProfileVisible": competitor.public_profile_visible,
        "nationality": competitor.nationality,
        "eligibilityStatus": competitor.eligibility_status,
    }


async def _apply_erasure(competitor: Competitor) -> dict[str, Any]:
    before = _export_competitor(competitor)
    competitor.given_names = None
    competitor.family_name = None
    competitor.date_of_birth = None
    competitor.email = None
    competitor.mobile = None
    competitor.whatsapp = None
    competitor.national_id = None
    competitor.photo_key = None
    competitor.coach = None
    competitor.registration_payload = None
    competitor.guardian_name = None
    competitor.guardian_email = None
    competitor.guardian_phone = None
    competitor.consent_participation_at = None
    competitor.consent_participation_by = None
    competitor.consent_public_at = None
    competitor.consent_public_by = None
    competitor.public_profile_visible = False
    competitor.nationality = None
    competitor.eligibility_override_reason = None
    if competitor.status not in {"DISQUALIFIED", "WITHDRAWN"}:
        competitor.status = "ERASED"
    return before


async def _apply_withdraw(competitor: Competitor) -> dict[str, Any]:
    before = {
        "publicProfileVisible": competitor.public_profile_visible,
        "consentPublicAt": (
            competitor.consent_public_at.isoformat() if competitor.consent_public_at else None
        ),
    }
    competitor.public_profile_visible = False
    competitor.consent_public_at = None
    competitor.consent_public_by = None
    return before


async def create_and_process_dsar(
    session: AsyncSession,
    *,
    subject_id: uuid.UUID,
    request_type: str,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> DsarJobOut:
    req = request_type.strip().upper()
    if req not in {"ACCESS", "ERASURE", "WITHDRAW"}:
        raise AppError(
            "VALIDATION_ERROR",
            "type must be ACCESS, ERASURE, or WITHDRAW",
            status_code=422,
            fields=[FieldError("type", "INVALID")],
        )

    competitor = await session.get(Competitor, subject_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Subject competitor not found", status_code=404)

    _assert_subject_verified(actor, competitor)

    job = DsarJob(
        subject_id=subject_id,
        request_type=req,
        status="PROCESSING",
        requested_by=actor.id,
    )
    session.add(job)
    await session.flush()

    export: dict[str, Any] | None = None

    if req == "ACCESS":
        export = _export_competitor(competitor)
        summary = "Personal data export generated"
        await write_audit_event(
            session,
            action="DSAR_ACCESS",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=competitor.competition_id,
            after={"jobId": str(job.id)},
            ip=ip,
            user_agent=user_agent,
        )
    elif req == "ERASURE":
        before = await _apply_erasure(competitor)
        summary = "Personal fields erased; competition integrity stub retained"
        await write_audit_event(
            session,
            action="DSAR_ERASURE",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=competitor.competition_id,
            before={"hadEmail": bool(before.get("email")), "refNo": before.get("refNo")},
            after={"status": competitor.status, "jobId": str(job.id)},
            reason="lawful erasure",
            ip=ip,
            user_agent=user_agent,
        )
    else:
        before = await _apply_withdraw(competitor)
        summary = "Public-display consent withdrawn"
        await write_audit_event(
            session,
            action="DSAR_WITHDRAW",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            competition_id=competitor.competition_id,
            before=before,
            after={"publicProfileVisible": False, "jobId": str(job.id)},
            reason="consent withdrawal",
            ip=ip,
            user_agent=user_agent,
        )

    job.status = "COMPLETED"
    job.export_payload = export
    job.result_summary = summary
    job.completed_at = datetime.utcnow()
    await session.commit()

    return DsarJobOut(
        jobId=job.id,
        status=job.status,
        requestType=job.request_type,
        export=export,
        resultSummary=summary,
        completedAt=job.completed_at,
    )


async def get_dsar_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    actor: User,
) -> DsarJobOut:
    job = await session.get(DsarJob, job_id)
    if job is None:
        raise AppError("DSAR_NOT_FOUND", "DSAR job not found", status_code=404)

    if not is_admin_role(actor.role):
        if job.requested_by != actor.id:
            competitor = await session.get(Competitor, job.subject_id)
            if competitor is None or competitor.user_id != actor.id:
                raise AppError(
                    "SUBJECT_UNVERIFIED",
                    "Caller cannot view this DSAR job",
                    status_code=403,
                )

    return DsarJobOut(
        jobId=job.id,
        status=job.status,
        requestType=job.request_type,
        export=job.export_payload,
        resultSummary=job.result_summary,
        completedAt=job.completed_at,
    )
