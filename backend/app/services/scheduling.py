"""US-SCH-01 — schedule sessions, assign workstations, log H&S incidents."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import (
    Competitor,
    Cycle,
    HealthSafetyIncident,
    NotificationOutbox,
    ScheduleSession,
    Shortlist,
    ShortlistEntry,
    SlotAssignment,
    User,
    Venue,
)
from app.schemas.scheduling import AssignmentOut, IncidentOut, SessionOut
from app.services.audit import write_audit_event


def _require_schedule_capability(actor: User) -> None:
    if is_admin_role(actor.role) or has_capability(actor.role, Capability.CONFIGURE_CYCLE):
        return
    raise AppError(
        "FORBIDDEN",
        "Admin role required to manage schedule",
        status_code=403,
        fields=[FieldError("role", "FORBIDDEN")],
    )


def _session_out(row: ScheduleSession) -> SessionOut:
    return SessionOut(
        sessionId=row.id,
        cycleId=row.cycle_id,
        venueId=row.venue_id,
        startsAt=row.starts_at,
        endsAt=row.ends_at,
        workstations=row.workstations,
        state=row.state,
    )


def _assignment_out(row: SlotAssignment) -> AssignmentOut:
    return AssignmentOut(
        assignmentId=row.id,
        sessionId=row.session_id,
        competitorId=row.competitor_id,
        workstation=row.workstation,
        readiness=row.readiness,
    )


def _incident_out(row: HealthSafetyIncident) -> IncidentOut:
    return IncidentOut(
        incidentId=row.id,
        sessionId=row.session_id,
        cycleId=row.cycle_id,
        summary=row.summary,
        severity=row.severity,
        recordedAt=row.recorded_at,
    )


def _parse_dt(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


async def _load_venue(session: AsyncSession, cycle_id: uuid.UUID, venue_id: uuid.UUID) -> Venue:
    venue = await session.get(Venue, venue_id)
    if venue is None or venue.cycle_id != cycle_id:
        raise AppError("VENUE_NOT_FOUND", "Venue not found in cycle", status_code=404)
    if not venue.active:
        raise AppError(
            "VENUE_INACTIVE",
            "Venue is inactive",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("venueId", "VENUE_INACTIVE")],
        )
    if venue.capacity is None or venue.capacity < 1:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Venue capacity is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("capacity", "CONFIG_INCOMPLETE")],
        )
    return venue


async def _is_confirmed_advanced(
    session: AsyncSession, *, cycle_id: uuid.UUID, competitor_id: uuid.UUID
) -> bool:
    row = (
        await session.execute(
            select(ShortlistEntry.id)
            .join(Shortlist, ShortlistEntry.shortlist_id == Shortlist.id)
            .where(
                Shortlist.cycle_id == cycle_id,
                Shortlist.state == "CONFIRMED",
                ShortlistEntry.competitor_id == competitor_id,
                ShortlistEntry.outcome == "ADVANCE",
                ShortlistEntry.advanced.is_(True),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def create_session(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    venue_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    workstations: int,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> SessionOut:
    _require_schedule_capability(actor)

    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)

    venue = await _load_venue(session, cycle_id, venue_id)

    starts = _parse_dt(starts_at)
    ends = _parse_dt(ends_at)
    if ends <= starts:
        raise AppError(
            "INVALID_WINDOW",
            "Session endsAt must be after startsAt",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("endsAt", "INVALID_WINDOW")],
        )
    if workstations < 1:
        raise AppError(
            "INVALID_WORKSTATIONS",
            "workstations must be >= 1",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("workstations", "INVALID_WORKSTATIONS")],
        )
    if workstations > venue.capacity:
        raise AppError(
            "CAPACITY_EXCEEDED",
            "Session workstations exceed venue capacity",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("workstations", "CAPACITY_EXCEEDED")],
        )

    row = ScheduleSession(
        cycle_id=cycle_id,
        venue_id=venue_id,
        starts_at=starts,
        ends_at=ends,
        workstations=workstations,
        state="SCHEDULED",
        created_by=actor.id,
    )
    session.add(row)
    await session.flush()

    await write_audit_event(
        session,
        action="SCHEDULE_SESSION_CREATE",
        entity_type="ScheduleSession",
        entity_id=str(row.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=cycle_id,
        after={
            "venueId": str(venue_id),
            "workstations": workstations,
            "startsAt": starts.isoformat(),
            "endsAt": ends.isoformat(),
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(row)
    return _session_out(row)


async def assign_slot(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    competitor_id: uuid.UUID,
    workstation: str,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AssignmentOut:
    _require_schedule_capability(actor)

    workstation = (workstation or "").strip()
    if not workstation:
        raise AppError(
            "INVALID_WORKSTATION",
            "Workstation is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("workstation", "INVALID_WORKSTATION")],
        )

    # Lock session row to serialise capacity / slot checks under concurrency
    schedule = (
        await session.execute(
            select(ScheduleSession).where(ScheduleSession.id == session_id).with_for_update()
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise AppError("SESSION_NOT_FOUND", "Schedule session not found", status_code=404)

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None or competitor.cycle_id != schedule.cycle_id:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found in cycle", status_code=404)

    if not await _is_confirmed_advanced(session, cycle_id=schedule.cycle_id, competitor_id=competitor_id):
        raise AppError(
            "NOT_SHORTLISTED",
            "Only confirmed shortlisted (ADVANCE) competitors may be assigned",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("competitorId", "NOT_SHORTLISTED")],
        )

    existing_ws = (
        await session.execute(
            select(SlotAssignment)
            .where(
                SlotAssignment.session_id == session_id,
                SlotAssignment.workstation == workstation,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing_ws is not None and existing_ws.competitor_id != competitor_id:
        raise AppError(
            "SLOT_CONFLICT",
            "Workstation is already assigned for this session",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("workstation", "SLOT_CONFLICT")],
        )

    existing_comp = (
        await session.execute(
            select(SlotAssignment)
            .where(
                SlotAssignment.session_id == session_id,
                SlotAssignment.competitor_id == competitor_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    # Re-schedule: update workstation and re-notify with dedupe per workstation
    if existing_comp is not None:
        before = {"workstation": existing_comp.workstation}
        if existing_comp.workstation == workstation:
            return _assignment_out(existing_comp)
        # Free target must already have been checked; update in place
        if existing_ws is not None and existing_ws.id != existing_comp.id:
            raise AppError(
                "SLOT_CONFLICT",
                "Workstation is already assigned for this session",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("workstation", "SLOT_CONFLICT")],
            )
        existing_comp.workstation = workstation
        existing_comp.assigned_at = datetime.utcnow()
        existing_comp.assigned_by = actor.id
        assignment = existing_comp
        await _enqueue_slot_notification(
            session,
            cycle_id=schedule.cycle_id,
            competitor_id=competitor_id,
            session_id=session_id,
            workstation=workstation,
            assignment_id=assignment.id,
        )
        await write_audit_event(
            session,
            action="SCHEDULE_SLOT_ASSIGN",
            entity_type="SlotAssignment",
            entity_id=str(assignment.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            cycle_id=schedule.cycle_id,
            before=before,
            after={"workstation": workstation, "competitorId": str(competitor_id)},
            reason="RESCHEDULE",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        await session.refresh(assignment)
        return _assignment_out(assignment)

    assigned_count = (
        await session.execute(
            select(func.count())
            .select_from(SlotAssignment)
            .where(SlotAssignment.session_id == session_id)
        )
    ).scalar_one()
    if int(assigned_count) >= schedule.workstations:
        raise AppError(
            "CAPACITY_EXCEEDED",
            "Session is at capacity",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("sessionId", "CAPACITY_EXCEEDED")],
        )

    assignment = SlotAssignment(
        session_id=session_id,
        competitor_id=competitor_id,
        workstation=workstation,
        readiness="PENDING",
        assigned_by=actor.id,
    )
    session.add(assignment)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "SLOT_CONFLICT",
            "Workstation is already assigned for this session",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("workstation", "SLOT_CONFLICT")],
        ) from exc

    await _enqueue_slot_notification(
        session,
        cycle_id=schedule.cycle_id,
        competitor_id=competitor_id,
        session_id=session_id,
        workstation=workstation,
        assignment_id=assignment.id,
    )
    await write_audit_event(
        session,
        action="SCHEDULE_SLOT_ASSIGN",
        entity_type="SlotAssignment",
        entity_id=str(assignment.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=schedule.cycle_id,
        after={"workstation": workstation, "competitorId": str(competitor_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(assignment)
    return _assignment_out(assignment)


async def _enqueue_slot_notification(
    session: AsyncSession,
    *,
    cycle_id: uuid.UUID,
    competitor_id: uuid.UUID,
    session_id: uuid.UUID,
    workstation: str,
    assignment_id: uuid.UUID,
) -> None:
    dedupe_key = f"schedule-slot:{session_id}:{competitor_id}:{workstation}"
    prior = (
        await session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.dedupe_key == dedupe_key,
                NotificationOutbox.status.in_(["QUEUED", "SENT", "FALLBACK_SENT"]),
            )
        )
    ).scalar_one_or_none()
    if prior is not None:
        return
    session.add(
        NotificationOutbox(
            cycle_id=cycle_id,
            recipient_role="COMPETITOR",
            recipient_id=competitor_id,
            template="SCHEDULE_SLOT_ASSIGNED",
            event_key="SCHEDULE_SLOT_ASSIGNED",
            payload={
                "sessionId": str(session_id),
                "assignmentId": str(assignment_id),
                "workstation": workstation,
                "competitorId": str(competitor_id),
            },
            status="QUEUED",
            dedupe_key=dedupe_key,
        )
    )


async def record_incident(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    summary: str | None,
    severity: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> IncidentOut:
    _require_schedule_capability(actor)

    if summary is None or not str(summary).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Incident summary is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("summary", "REASON_REQUIRED")],
        )
    summary = str(summary).strip()

    schedule = await session.get(ScheduleSession, session_id)
    if schedule is None:
        raise AppError("SESSION_NOT_FOUND", "Schedule session not found", status_code=404)

    incident = HealthSafetyIncident(
        session_id=session_id,
        cycle_id=schedule.cycle_id,
        summary=summary,
        severity=(severity.strip().upper() if severity else None),
        recorded_by=actor.id,
    )
    session.add(incident)
    await session.flush()

    await write_audit_event(
        session,
        action="SCHEDULE_INCIDENT_RECORD",
        entity_type="HealthSafetyIncident",
        entity_id=str(incident.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=schedule.cycle_id,
        after={
            "sessionId": str(session_id),
            "summary": summary,
            "severity": incident.severity,
        },
        reason=summary,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(incident)
    return _incident_out(incident)
