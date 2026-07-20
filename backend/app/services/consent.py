"""Guardian consent for minors (US-REG-02) — participation + public-display scopes."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Competitor, ConsentRequest, RegistrationFormDefinition
from app.schemas.consent import (
    ConsentGrantIn,
    ConsentGrantOut,
    ConsentRequestIn,
    ConsentRequestOut,
    ConsentWithdrawOut,
)
from app.services.audit import write_audit_event
from app.services.nominations import enqueue_notification

_VALID_SCOPES = {"participation", "public"}
_TOKEN_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.utcnow()


def compute_age(dob: date, *, on: date) -> int:
    years = on.year - dob.year
    if (on.month, on.day) < (dob.month, dob.day):
        years -= 1
    return years


def is_minor(
    dob: date | None,
    *,
    minor_age_under: int | None,
    reference_date: date | None,
) -> bool:
    """True when competitor is under the configured minor threshold (fail closed if config missing)."""
    if dob is None:
        return False
    if minor_age_under is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "minorAgeUnder is not configured for this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("minorAgeUnder", "CONFIG_INCOMPLETE")],
        )
    ref = reference_date or date.today()
    return compute_age(dob, on=ref) < minor_age_under


def has_participation_consent(competitor: Competitor) -> bool:
    return competitor.consent_participation_at is not None


def is_public_profile_visible(competitor: Competitor) -> bool:
    """Public display defaults withheld until explicit public-scope consent."""
    return bool(competitor.public_profile_visible and competitor.consent_public_at is not None)


def can_progress_past_pending_review(competitor: Competitor) -> bool:
    """Minors marked CONSENT_PENDING cannot progress until participation consent."""
    flags = list(competitor.flags or [])
    if "CONSENT_PENDING" in flags or competitor.status == "CONSENT_PENDING":
        return has_participation_consent(competitor)
    return True


def _flag_list(competitor: Competitor) -> list[str]:
    return list(competitor.flags or [])


def _set_flags(competitor: Competitor, flags: list[str]) -> None:
    competitor.flags = flags


async def _load_form(session: AsyncSession, cycle_id: uuid.UUID) -> RegistrationFormDefinition:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.cycle_id == cycle_id)
        )
    ).scalar_one_or_none()
    if form is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Registration form definition missing",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("form", "CONFIG_INCOMPLETE")],
        )
    return form


async def apply_minor_gate_on_registration(
    session: AsyncSession,
    competitor: Competitor,
    *,
    form: RegistrationFormDefinition,
    guardian_name: str | None,
    guardian_email: str | None,
    guardian_phone: str | None,
) -> ConsentRequest | None:
    """If minor without participation consent → CONSENT_PENDING. Optionally open a consent request."""
    if not is_minor(
        competitor.date_of_birth,
        minor_age_under=form.minor_age_under,
        reference_date=form.minor_reference_date,
    ):
        return None

    # Privacy by default — public stays off
    competitor.public_profile_visible = False
    flags = _flag_list(competitor)
    if "CONSENT_PENDING" not in flags:
        flags.append("CONSENT_PENDING")
    _set_flags(competitor, flags)
    competitor.status = "CONSENT_PENDING"

    if guardian_name and guardian_email:
        competitor.guardian_name = guardian_name.strip()
        competitor.guardian_email = guardian_email.strip()
        competitor.guardian_phone = guardian_phone.strip() if guardian_phone else None
        return await _create_consent_request(session, competitor)

    return None


async def _create_consent_request(session: AsyncSession, competitor: Competitor) -> ConsentRequest:
    token = secrets.token_urlsafe(24)
    req = ConsentRequest(
        competitor_id=competitor.id,
        token=token,
        expires_at=_now() + _TOKEN_TTL,
    )
    session.add(req)
    await session.flush()
    await enqueue_notification(
        session,
        cycle_id=competitor.cycle_id,
        recipient_role="GUARDIAN",
        recipient_id=competitor.id,
        template="CONSENT_REQUEST",
        payload={
            "competitorId": str(competitor.id),
            "guardianEmail": competitor.guardian_email,
            # token included so guardian link can be built; channel later respects prefs
            "token": token,
        },
    )
    return req


async def create_consent_request(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    payload: ConsentRequestIn,
    *,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ConsentRequestOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    form = await _load_form(session, competitor.cycle_id)
    if not is_minor(
        competitor.date_of_birth,
        minor_age_under=form.minor_age_under,
        reference_date=form.minor_reference_date,
    ):
        raise AppError(
            "CONSENT_NOT_REQUIRED",
            "Competitor is not a minor under cycle rules",
            status_code=status.HTTP_409_CONFLICT,
        )

    if not payload.guardianName.strip() or not payload.guardianEmail.strip():
        raise AppError(
            "GUARDIAN_REQUIRED",
            "Guardian identity and contact are required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("guardianName", "GUARDIAN_REQUIRED")],
        )

    competitor.guardian_name = payload.guardianName.strip()
    competitor.guardian_email = payload.guardianEmail.strip()
    competitor.guardian_phone = payload.guardianPhone.strip() if payload.guardianPhone else None

    flags = _flag_list(competitor)
    if "CONSENT_PENDING" not in flags:
        flags.append("CONSENT_PENDING")
    _set_flags(competitor, flags)
    if competitor.status not in {"CONSENT_PENDING", "PENDING_REVIEW"}:
        competitor.status = "CONSENT_PENDING"
    elif not has_participation_consent(competitor):
        competitor.status = "CONSENT_PENDING"

    req = await _create_consent_request(session, competitor)
    await write_audit_event(
        session,
        action="CONSENT_REQUEST",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor_id,
        actor_role=actor_role or "SYSTEM",
        cycle_id=competitor.cycle_id,
        after={"expiresAt": req.expires_at.isoformat()},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return ConsentRequestOut(
        competitorId=competitor.id,
        status=competitor.status,
        expiresAt=req.expires_at.isoformat(),
        token=req.token,
    )


async def grant_consent(
    session: AsyncSession,
    token: str,
    payload: ConsentGrantIn,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ConsentGrantOut:
    req = (
        await session.execute(select(ConsentRequest).where(ConsentRequest.token == token))
    ).scalar_one_or_none()
    if req is None or (req.expires_at < _now()) or req.consumed_at is not None:
        raise AppError(
            "CONSENT_TOKEN_INVALID",
            "Consent token is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
            fields=[FieldError("token", "CONSENT_TOKEN_INVALID")],
        )

    scopes = [s.strip().lower() for s in payload.scopes if s and s.strip()]
    if not scopes:
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            "At least one consent scope is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )
    unknown = [s for s in scopes if s not in _VALID_SCOPES]
    if unknown:
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            f"Unknown scopes: {', '.join(unknown)}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )

    competitor = await session.get(Competitor, req.competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    granted_by = (payload.grantedBy or competitor.guardian_email or competitor.guardian_name or "guardian").strip()
    now = _now()
    granted: list[str] = []

    if "participation" in scopes:
        competitor.consent_participation_at = now
        competitor.consent_participation_by = granted_by
        granted.append("participation")
        flags = [f for f in _flag_list(competitor) if f != "CONSENT_PENDING"]
        _set_flags(competitor, flags)
        # Lift block — back to PENDING_REVIEW for admin / registration progression
        competitor.status = "PENDING_REVIEW"

    if "public" in scopes:
        if not has_participation_consent(competitor) and "participation" not in scopes:
            raise AppError(
                "CONSENT_SCOPE_MISSING",
                "Participation consent is required before or with public-display consent",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
            )
        competitor.consent_public_at = now
        competitor.consent_public_by = granted_by
        competitor.public_profile_visible = True
        granted.append("public")

    req.consumed_at = now

    await write_audit_event(
        session,
        action="CONSENT_GRANT",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_role="GUARDIAN",
        cycle_id=competitor.cycle_id,
        after={"scopes": granted, "by": granted_by, "at": now.isoformat()},
        reason="data-subject consent",
        ip=ip,
        user_agent=user_agent,
    )
    await enqueue_notification(
        session,
        cycle_id=competitor.cycle_id,
        recipient_role="ADMIN",
        template="CONSENT_GRANTED",
        payload={"competitorId": str(competitor.id), "scopes": granted},
    )
    await session.commit()
    await session.refresh(competitor)
    return ConsentGrantOut(
        competitorId=competitor.id,
        status=competitor.status,
        scopesGranted=granted,
        publicProfileVisible=is_public_profile_visible(competitor),
    )


async def withdraw_consent(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ConsentWithdrawOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    competitor.consent_participation_at = None
    competitor.consent_participation_by = None
    competitor.consent_public_at = None
    competitor.consent_public_by = None
    competitor.public_profile_visible = False

    flags = _flag_list(competitor)
    if "CONSENT_WITHDRAWN" not in flags:
        flags.append("CONSENT_WITHDRAWN")
    if "CONSENT_PENDING" not in flags:
        flags.append("CONSENT_PENDING")
    _set_flags(competitor, flags)
    competitor.status = "CONSENT_PENDING"

    await write_audit_event(
        session,
        action="CONSENT_WITHDRAW",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor_id,
        actor_role=actor_role or "GUARDIAN",
        cycle_id=competitor.cycle_id,
        after={"publicProfileVisible": False, "flags": flags},
        reason="data-subject withdrawal",
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(competitor)
    return ConsentWithdrawOut(
        competitorId=competitor.id,
        status=competitor.status,
        flags=_flag_list(competitor),
        publicProfileVisible=False,
    )
