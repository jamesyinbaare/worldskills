"""Online competitor registration — config-driven form, window, abuse, duplicates."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import (
    Competitor,
    IdempotencyRecord,
    Institution,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    Zone,
)
from app.schemas.registrations import (
    FormFieldOut,
    RegistrationCreate,
    RegistrationFormOut,
    RegistrationOut,
)
from app.services.audit import write_audit_event
from app.services.consent import apply_minor_gate_on_registration, can_progress_past_pending_review
from app.services.nominations import enqueue_notification
from app.services.storage import LocalObjectStorage

_NAME_RE = re.compile(r"^[\w\s\-'.À-ȕ]+$", re.UNICODE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\-\s]{6,20}$")

# Testable abuse tokens (real CAPTCHA provider later)
_CAPTCHA_OK = {"ok", "valid", "pass"}
_CAPTCHA_RATE = {"rate-limited", "rate_limit"}


def _now() -> datetime:
    return datetime.utcnow()


async def load_form_config(
    session: AsyncSession, cycle_id: uuid.UUID
) -> tuple[RegistrationFormDefinition, RegistrationWindow | None]:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.cycle_id == cycle_id)
        )
    ).scalar_one_or_none()
    if form is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Registration form definition missing for cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("form", "CONFIG_INCOMPLETE")],
        )
    window = (
        await session.execute(select(RegistrationWindow).where(RegistrationWindow.cycle_id == cycle_id))
    ).scalar_one_or_none()
    return form, window


def _window_open(window: RegistrationWindow | None, now: datetime | None = None) -> bool:
    if window is None:
        return False
    current = now or _now()
    return window.opens_at <= current <= window.closes_at


async def get_registration_form(session: AsyncSession, cycle_id: uuid.UUID) -> RegistrationFormOut:
    form, window = await load_form_config(session, cycle_id)
    open_now = _window_open(window)
    fields = [
        FormFieldOut(
            name=str(f.get("name")),
            type=str(f.get("type", "string")),
            required=bool(f.get("required", False)),
            maxLength=f.get("maxLength"),
            pattern=f.get("pattern"),
        )
        for f in (form.fields or [])
    ]
    return RegistrationFormOut(
        fields=fields,
        maxSkills=form.max_skills,
        photoMaxMb=form.photo_max_mb,
        photoFormats=list(form.photo_formats or []),
        readOnly=not open_now,
        window=(
            {"opensAt": window.opens_at.isoformat(), "closesAt": window.closes_at.isoformat()}
            if window
            else None
        ),
    )


def _check_abuse(captcha_token: str | None) -> None:
    if captcha_token is None or captcha_token.strip() == "":
        raise AppError(
            "ABUSE_SUSPECTED",
            "CAPTCHA required",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("captchaToken", "ABUSE_SUSPECTED")],
        )
    token = captcha_token.strip().lower()
    if token in _CAPTCHA_RATE:
        raise AppError(
            "ABUSE_SUSPECTED",
            "Rate limit exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            fields=[FieldError("captchaToken", "ABUSE_SUSPECTED")],
        )
    if token not in _CAPTCHA_OK:
        raise AppError(
            "ABUSE_SUSPECTED",
            "CAPTCHA verification failed",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("captchaToken", "ABUSE_SUSPECTED")],
        )


def _field_value(payload: RegistrationCreate, name: str) -> Any:
    mapping = {
        "givenNames": payload.givenNames,
        "familyName": payload.familyName,
        "dateOfBirth": payload.dateOfBirth,
        "email": payload.email,
        "mobile": payload.mobile,
        "whatsapp": payload.whatsapp,
        "nationalId": payload.nationalId,
        "institutionId": payload.institutionId,
        "zoneId": payload.zoneId,
        "skillIds": payload.skillIds,
        "coach": payload.coach,
        "declarationAccepted": payload.declarationAccepted,
        "photo": payload.photo,
    }
    return mapping.get(name)


def _validate_against_form(form: RegistrationFormDefinition, payload: RegistrationCreate) -> list[FieldError]:
    errors: list[FieldError] = []
    for field in form.fields or []:
        name = str(field.get("name"))
        required = bool(field.get("required", False))
        value = _field_value(payload, name)

        if required and (value is None or value == "" or value == [] or value is False):
            if name == "declarationAccepted":
                errors.append(FieldError(name, "DECLARATION_REQUIRED"))
            else:
                errors.append(FieldError(name, "REQUIRED"))
            continue

        if value is None or value == "":
            continue

        if name in {"givenNames", "familyName"}:
            s = str(value)
            max_len = int(field.get("maxLength") or 100)
            if len(s) > max_len or not _NAME_RE.match(s):
                errors.append(FieldError(name, "INVALID_CHARS" if s.strip() else "REQUIRED"))

        elif name == "dateOfBirth":
            if not isinstance(value, date) or value >= date.today():
                errors.append(FieldError(name, "INVALID_DATE"))

        elif name == "email":
            if not _EMAIL_RE.match(str(value)):
                errors.append(FieldError(name, "EMAIL_INVALID"))

        elif name in {"mobile", "whatsapp"}:
            if not _PHONE_RE.match(str(value).replace(" ", "")):
                errors.append(FieldError(name, "PHONE_INVALID"))

        elif name == "nationalId" and form.national_id_pattern:
            if not re.fullmatch(form.national_id_pattern, str(value)):
                errors.append(FieldError(name, "ID_INVALID"))

        elif name == "declarationAccepted" and value is not True:
            errors.append(FieldError(name, "DECLARATION_REQUIRED"))

    return errors


def _validate_photo(form: RegistrationFormDefinition, payload: RegistrationCreate) -> tuple[bytes, str] | None:
    # Photo required if listed in form
    photo_required = any(f.get("name") == "photo" and f.get("required") for f in (form.fields or []))
    if payload.photo is None:
        if photo_required:
            raise AppError(
                "PHOTO_INVALID",
                "Photo is required",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("photo", "PHOTO_INVALID")],
            )
        return None

    formats = [str(f).lower() for f in (form.photo_formats or ["image/jpeg", "image/png"])]
    content_type = payload.photo.contentType.lower()
    if content_type not in formats:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        )
    try:
        data = base64.b64decode(payload.photo.contentBase64, validate=True)
    except Exception as exc:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        ) from exc

    max_bytes = form.photo_max_mb * 1024 * 1024
    if len(data) > max_bytes or len(data) == 0:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        )
    # Minimal EXIF strip stub: JPEG APP1 segment removal is best-effort; store raw for MVP.
    return data, content_type


def _issue_ref() -> str:
    return f"WSG-{date.today().year}-{uuid.uuid4().hex[:8].upper()}"


async def create_registration(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    payload: RegistrationCreate,
    *,
    idempotency_key: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: LocalObjectStorage | None = None,
) -> tuple[RegistrationOut, int]:
    if idempotency_key:
        existing = (
            await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.cycle_id == cycle_id,
                    IdempotencyRecord.key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return RegistrationOut.model_validate(existing.response_body), existing.status_code

    form, window = await load_form_config(session, cycle_id)
    if not _window_open(window):
        raise AppError(
            "WINDOW_CLOSED",
            "Registration window is closed",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("window", "WINDOW_CLOSED")],
        )

    _check_abuse(payload.captchaToken)

    field_errors = _validate_against_form(form, payload)
    if field_errors:
        raise AppError(
            "VALIDATION_ERROR",
            "Registration validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=field_errors,
        )

    if len(payload.skillIds) != form.max_skills:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            f"Exactly {form.max_skills} skill(s) must be selected",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillIds", "SKILL_SELECTION_INVALID")],
        )

    skill_id = payload.skillIds[0]
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.cycle_id != cycle_id or not skill.active:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            "Selected skill is invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillIds", "SKILL_SELECTION_INVALID")],
        )

    if payload.zoneId is None:
        raise AppError(
            "VALIDATION_ERROR",
            "Zone is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("zoneId", "REQUIRED")],
        )
    zone = await session.get(Zone, payload.zoneId)
    if zone is None or zone.cycle_id != cycle_id:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid zone",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("zoneId", "REQUIRED")],
        )

    if payload.institutionId is not None:
        inst = await session.get(Institution, payload.institutionId)
        if inst is None or not inst.active:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid institution",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("institutionId", "REQUIRED")],
            )

    photo_data = _validate_photo(form, payload)
    photo_key: str | None = None
    if photo_data is not None:
        data, content_type = photo_data
        ext = "jpg" if "jpeg" in content_type else "png"
        store = storage or LocalObjectStorage()
        stored = store.put(data, prefix=f"cycles/{cycle_id}/photos", filename=f"{uuid.uuid4()}.{ext}")
        photo_key = stored.key

    flags: list[str] = []
    if payload.nationalId and payload.dateOfBirth:
        dup = (
            await session.execute(
                select(Competitor).where(
                    Competitor.cycle_id == cycle_id,
                    Competitor.national_id == payload.nationalId,
                    Competitor.date_of_birth == payload.dateOfBirth,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            flags.append("DUPLICATE_SUSPECTED")

    ref = _issue_ref()
    competitor = Competitor(
        cycle_id=cycle_id,
        skill_id=skill_id,
        zone_id=payload.zoneId,
        institution_id=payload.institutionId,
        ref_no=ref,
        status="PENDING_REVIEW",
        given_names=payload.givenNames,
        family_name=payload.familyName,
        date_of_birth=payload.dateOfBirth,
        email=payload.email,
        mobile=payload.mobile,
        whatsapp=payload.whatsapp,
        national_id=payload.nationalId,
        photo_key=photo_key,
        coach=payload.coach,
        flags=flags,
        public_profile_visible=False,
        guardian_name=payload.guardianName,
        guardian_email=payload.guardianEmail,
        guardian_phone=payload.guardianPhone,
        registration_payload={
            "skillIds": [str(s) for s in payload.skillIds],
            # Never persist captcha / raw photo bytes in payload
        },
    )
    session.add(competitor)
    await session.flush()

    await apply_minor_gate_on_registration(
        session,
        competitor,
        form=form,
        guardian_name=payload.guardianName,
        guardian_email=payload.guardianEmail,
        guardian_phone=payload.guardianPhone,
    )

    message = None
    if "DUPLICATE_SUSPECTED" in (competitor.flags or []):
        message = "Registration received; identity check is pending admin review"
    if not can_progress_past_pending_review(competitor):
        message = (message + "; " if message else "") + "Guardian consent required before progression"

    await enqueue_notification(
        session,
        cycle_id=cycle_id,
        recipient_role="COMPETITOR",
        recipient_id=competitor.id,
        template="REGISTRATION_CONFIRMATION",
        payload={"competitorRef": ref, "email": payload.email},
    )
    await write_audit_event(
        session,
        action="REGISTRATION_CREATE",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor_id,
        actor_role=actor_role or "ANONYMOUS",
        cycle_id=cycle_id,
        after={
            "competitorRef": ref,
            "status": competitor.status,
            "flags": list(competitor.flags or []),
            # no PII in after snapshot beyond ref
        },
        ip=ip,
        user_agent=user_agent,
    )

    out = RegistrationOut(
        competitorId=competitor.id,
        competitorRef=ref,
        status=competitor.status,
        flags=list(competitor.flags or []),
        message=message,
    )

    if idempotency_key:
        session.add(
            IdempotencyRecord(
                cycle_id=cycle_id,
                key=idempotency_key,
                status_code=201,
                response_body=out.model_dump(mode="json"),
            )
        )

    await session.commit()
    return out, 201
