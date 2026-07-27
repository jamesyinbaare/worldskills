"""Guardian consent for minors (US-REG-02) — participation + public-display scopes."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import (
    Competition,
    Competitor,
    ConsentRequest,
    RegistrationFormDefinition,
    User,
    UserRole,
)
from app.schemas.consent import (
    ConsentFormUploadOut,
    ConsentGrantIn,
    ConsentGrantOut,
    ConsentRequestIn,
    ConsentRequestOut,
    ConsentVerifyIn,
    ConsentVerifyOut,
    ConsentWithdrawOut,
)
from app.services.audit import write_audit_event
from app.services.consent_pdf import render_consent_form_pdf
from app.services.nominations import enqueue_notification
from app.services.storage import ObjectStorage, get_object_storage

_VALID_SCOPES = {"participation", "public"}
_TOKEN_TTL = timedelta(days=7)
_PDF_MAGIC = b"%PDF"


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
            "minorAgeUnder is not configured for this competition",
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


async def _load_form(session: AsyncSession, competition_id: uuid.UUID) -> RegistrationFormDefinition:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.competition_id == competition_id)
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
        competition_id=competitor.competition_id,
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

    form = await _load_form(session, competitor.competition_id)
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
        competition_id=competitor.competition_id,
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
        competition_id=competitor.competition_id,
        after={"scopes": granted, "by": granted_by, "at": now.isoformat()},
        reason="data-subject consent",
        ip=ip,
        user_agent=user_agent,
    )
    await enqueue_notification(
        session,
        competition_id=competitor.competition_id,
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
    competitor.consent_form_key = None
    competitor.consent_form_uploaded_at = None
    competitor.consent_form_sha256 = None

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
        competition_id=competitor.competition_id,
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


def _normalize_scopes(
    scopes: list[str],
    *,
    participation_already_granted: bool = False,
) -> list[str]:
    normalized = [s.strip().lower() for s in scopes if s and s.strip()]
    if not normalized:
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            "At least one consent scope is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )
    unknown = [s for s in normalized if s not in _VALID_SCOPES]
    if unknown:
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            f"Unknown scopes: {', '.join(unknown)}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )
    if (
        "participation" not in normalized
        and "public" in normalized
        and not participation_already_granted
    ):
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            "Participation consent is required before or with public-display consent",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )
    return normalized


def _apply_scopes(
    competitor: Competitor,
    scopes: list[str],
    *,
    granted_by: str,
    now: datetime,
) -> list[str]:
    granted: list[str] = []
    if "participation" in scopes:
        competitor.consent_participation_at = now
        competitor.consent_participation_by = granted_by
        granted.append("participation")
        flags = [f for f in _flag_list(competitor) if f != "CONSENT_PENDING"]
        _set_flags(competitor, flags)
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
    return granted


async def _require_owned_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
) -> Competitor:
    if actor.role != UserRole.COMPETITOR:
        raise AppError(
            "FORBIDDEN",
            "Competitor account required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None or competitor.user_id != actor.id:
        raise AppError(
            "COMPETITOR_NOT_FOUND",
            "Competitor not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return competitor


async def _require_owned_minor_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
) -> Competitor:
    competitor = await _require_owned_competitor(
        session, competitor_id, actor=actor
    )
    form = await _load_form(session, competitor.competition_id)
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
    return competitor


async def download_consent_form_pdf(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
) -> tuple[bytes, str]:
    competitor = await _require_owned_minor_competitor(
        session, competitor_id, actor=actor
    )
    competition = await session.get(Competition, competitor.competition_id)
    competition_name = competition.name if competition is not None else "Competition"
    pdf = render_consent_form_pdf(
        competition_name=competition_name,
        competitor_ref=competitor.ref_no,
        given_names=competitor.given_names,
        family_name=competitor.family_name,
        date_of_birth=competitor.date_of_birth,
        guardian_name=competitor.guardian_name,
        guardian_email=competitor.guardian_email,
        guardian_phone=competitor.guardian_phone,
    )
    filename = f"guardian-consent-{competitor.ref_no}.pdf"
    return pdf, filename


async def download_uploaded_consent_form(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str]:
    competitor = await _require_owned_competitor(
        session, competitor_id, actor=actor
    )
    if not competitor.consent_form_key:
        raise AppError(
            "CONSENT_FORM_NOT_FOUND",
            "No signed consent form has been uploaded",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    store = storage or get_object_storage()
    data = store.get(competitor.consent_form_key)
    stored_name = competitor.consent_form_key.rsplit("/", 1)[-1]
    filename = stored_name if stored_name.lower().endswith(".pdf") else (
        f"signed-consent-{competitor.ref_no}.pdf"
    )
    return data, filename


async def upload_signed_consent_form(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
    data: bytes,
    filename: str | None,
    content_type: str | None,
    scopes: list[str],
    granted_by: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> ConsentFormUploadOut:
    competitor = await _require_owned_minor_competitor(
        session, competitor_id, actor=actor
    )
    normalized = _normalize_scopes(
        scopes,
        participation_already_granted=has_participation_consent(competitor),
    )
    if "participation" not in normalized and not has_participation_consent(competitor):
        raise AppError(
            "CONSENT_SCOPE_MISSING",
            "Participation scope is required when uploading a signed consent form",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("scopes", "CONSENT_SCOPE_MISSING")],
        )

    ctype = (content_type or "").lower()
    name = (filename or "").lower()
    if not (ctype in {"application/pdf", "application/x-pdf"} or name.endswith(".pdf")):
        if not data.startswith(_PDF_MAGIC):
            raise AppError(
                "INVALID_FILE_TYPE",
                "Signed consent form must be a PDF",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("file", "INVALID_FILE_TYPE")],
            )
    if not data.startswith(_PDF_MAGIC):
        raise AppError(
            "INVALID_FILE_TYPE",
            "Signed consent form must be a PDF",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("file", "INVALID_FILE_TYPE")],
        )

    store = storage or get_object_storage()
    stored = store.put(
        data,
        prefix=f"consent/{competitor.competition_id}/{competitor.id}",
        filename=filename or "signed-consent.pdf",
    )

    now = _now()
    by = (granted_by or competitor.guardian_name or competitor.guardian_email or "guardian").strip()
    granted = _apply_scopes(competitor, normalized, granted_by=by, now=now)
    competitor.consent_form_key = stored.key
    competitor.consent_form_uploaded_at = now
    competitor.consent_form_sha256 = stored.sha256
    competitor.consent_verification_status = "PENDING"
    competitor.consent_verified_at = None
    competitor.consent_verified_by = None
    competitor.consent_verification_reason = None

    await write_audit_event(
        session,
        action="CONSENT_FORM_UPLOAD",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
        competition_id=competitor.competition_id,
        after={
            "scopes": granted,
            "by": by,
            "at": now.isoformat(),
            "key": stored.key,
            "sha256": stored.sha256,
        },
        reason="signed guardian consent form",
        ip=ip,
        user_agent=user_agent,
    )
    await write_audit_event(
        session,
        action="CONSENT_GRANT",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role="GUARDIAN",
        competition_id=competitor.competition_id,
        after={"scopes": granted, "by": by, "at": now.isoformat(), "via": "pdf"},
        reason="signed guardian consent form",
        ip=ip,
        user_agent=user_agent,
    )
    await enqueue_notification(
        session,
        competition_id=competitor.competition_id,
        recipient_role="ADMIN",
        template="CONSENT_GRANTED",
        payload={"competitorId": str(competitor.id), "scopes": granted, "via": "pdf"},
    )
    await session.commit()
    await session.refresh(competitor)
    return ConsentFormUploadOut(
        competitorId=competitor.id,
        status=competitor.status,
        scopesGranted=granted,
        publicProfileVisible=is_public_profile_visible(competitor),
        consentFormUploadedAt=now.isoformat(),
        sha256=stored.sha256,
    )


def _require_consent_admin(actor: User) -> None:
    if is_admin_role(actor.role) or has_capability(actor.role, Capability.CONFIGURE_CYCLE):
        return
    raise AppError(
        "FORBIDDEN",
        "Admin role required to manage consent verification",
        status_code=status.HTTP_403_FORBIDDEN,
        fields=[FieldError("role", "FORBIDDEN")],
    )


async def admin_download_uploaded_consent_form(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str]:
    _require_consent_admin(actor)
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)
    if not competitor.consent_form_key:
        raise AppError(
            "CONSENT_FORM_NOT_FOUND",
            "No signed consent form has been uploaded",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    store = storage or get_object_storage()
    data = store.get(competitor.consent_form_key)
    stored_name = competitor.consent_form_key.rsplit("/", 1)[-1]
    filename = stored_name if stored_name.lower().endswith(".pdf") else (
        f"signed-consent-{competitor.ref_no}.pdf"
    )
    return data, filename


async def verify_consent_form(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    payload: ConsentVerifyIn,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ConsentVerifyOut:
    _require_consent_admin(actor)
    outcome = (payload.outcome or "").strip().upper()
    if outcome not in {"VERIFIED", "REJECTED"}:
        raise AppError(
            "VALIDATION_ERROR",
            "outcome must be VERIFIED or REJECTED",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("outcome", "INVALID")],
        )
    if outcome == "REJECTED" and not (payload.reason or "").strip():
        raise AppError(
            "REASON_REQUIRED",
            "Reason is required when rejecting a consent form",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)
    if not competitor.consent_form_key:
        raise AppError(
            "CONSENT_FORM_NOT_FOUND",
            "No signed consent form has been uploaded",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    now = _now()
    reason = (payload.reason or "").strip() or None
    previous_status = competitor.status
    competitor.consent_verification_status = outcome
    competitor.consent_verified_at = now
    competitor.consent_verified_by = actor.id
    competitor.consent_verification_reason = reason if outcome == "REJECTED" else None

    # Completing admin review of the signed form advances registration.
    if outcome == "VERIFIED" and competitor.status in {
        "PENDING_REVIEW",
        "CONSENT_PENDING",
    }:
        competitor.status = "REGISTERED"
        flags = [f for f in _flag_list(competitor) if f != "CONSENT_PENDING"]
        _set_flags(competitor, flags)

    await write_audit_event(
        session,
        action="CONSENT_FORM_VERIFY",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
        competition_id=competitor.competition_id,
        after={
            "status": outcome,
            "competitorStatus": competitor.status,
            "previousCompetitorStatus": previous_status,
            "reason": competitor.consent_verification_reason,
            "at": now.isoformat(),
        },
        reason=competitor.consent_verification_reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(competitor)
    return ConsentVerifyOut(
        competitorId=competitor.id,
        consentVerificationStatus=competitor.consent_verification_status or outcome,
        consentVerifiedAt=now.isoformat(),
        consentVerificationReason=competitor.consent_verification_reason,
    )
