"""Online competitor registration — config-driven form, window, abuse, duplicates."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import (
    Competitor,
    IdempotencyRecord,
    Institution,
    RegistrationFormDefinition,
    RegistrationWindow,
    Skill,
    User,
    UserRole,
)
from app.schemas.registrations import (
    FormFieldOut,
    RegistrationCreate,
    RegistrationFormAdminOut,
    RegistrationFormAdminUpdate,
    RegistrationFormOut,
    RegistrationOut,
    RegistrationWindowOut,
    RegistrationWindowUpdate,
)
from app.services.audit import write_audit_event
from app.services.consent import apply_minor_gate_on_registration, can_progress_past_pending_review
from app.services.eligibility import screen_competitor
from app.services.geography import resolve_zone_for_registration
from app.services.nominations import enqueue_notification
from app.services.storage import ObjectStorage, get_object_storage

_NAME_RE = re.compile(r"^[\w\s\-'.À-ȕ]+$", re.UNICODE)
_PASSPORT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\s]{4,62}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\-\s]{6,20}$")

# Testable abuse tokens (real CAPTCHA provider later)
_CAPTCHA_OK = {"ok", "valid", "pass"}
_CAPTCHA_RATE = {"rate-limited", "rate_limit"}

ALLOWED_GENDERS = frozenset({"Male", "Female"})
_QUOTA_EXCLUDED_STATUSES = frozenset({"REJECTED", "WITHDRAWN"})
_GENDER_FIELD = {
    "name": "gender",
    "type": "enum",
    "required": True,
    "allowedValues": ["Male", "Female"],
}


def _ensure_gender_on_form(form: RegistrationFormDefinition) -> None:
    """Guarantee gender is collected even when older form configs omit it."""
    fields = list(form.fields or [])
    if any(str(f.get("name")) == "gender" for f in fields):
        return
    insert_at = next(
        (i + 1 for i, f in enumerate(fields) if str(f.get("name")) == "familyName"),
        min(2, len(fields)),
    )
    fields.insert(insert_at, dict(_GENDER_FIELD))
    form.fields = fields


def _now() -> datetime:
    return datetime.utcnow()


def _as_naive(value: datetime) -> datetime:
    """Store UTC-wall times in TIMESTAMP WITHOUT TIME ZONE columns."""
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


async def load_form_config(
    session: AsyncSession, competition_id: uuid.UUID
) -> tuple[RegistrationFormDefinition, RegistrationWindow | None]:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.competition_id == competition_id)
        )
    ).scalar_one_or_none()
    if form is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Registration form definition missing for competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("form", "CONFIG_INCOMPLETE")],
        )
    window = (
        await session.execute(select(RegistrationWindow).where(RegistrationWindow.competition_id == competition_id))
    ).scalar_one_or_none()
    return form, window


def _window_open(window: RegistrationWindow | None, now: datetime | None = None) -> bool:
    if window is None:
        return False
    current = now or _now()
    return window.opens_at <= current <= window.closes_at


async def get_registration_form(session: AsyncSession, competition_id: uuid.UUID) -> RegistrationFormOut:
    form, window = await load_form_config(session, competition_id)
    open_now = _window_open(window)
    _ensure_gender_on_form(form)
    fields = [
        FormFieldOut(
            name=str(f.get("name")),
            type=str(f.get("type", "string")),
            required=bool(f.get("required", False)),
            maxLength=f.get("maxLength"),
            pattern=f.get("pattern"),
            allowedValues=f.get("allowedValues"),
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
        "gender": payload.gender,
        "dateOfBirth": payload.dateOfBirth,
        "email": payload.email,
        "mobile": payload.mobile,
        "whatsapp": payload.whatsapp,
        "nationalId": payload.nationalId,
        "hasPassport": payload.hasPassport,
        "passportNumber": payload.passportNumber,
        "passportExpiresOn": payload.passportExpiresOn,
        "institutionId": payload.institutionId,
        "regionId": payload.regionId,
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

        if name == "zoneId":
            # Zone is derived from region; ignore legacy form requirement.
            continue

        if name == "institutionId":
            # School is optional for COMPETITOR; INSTITUTION binding is enforced in create_registration.
            continue

        if name == "regionId":
            # Region is only required when registering without a school; school carries region.
            if payload.institutionId is not None:
                continue

        if name in {"hasPassport", "passportNumber", "passportExpiresOn"}:
            # Validated after the form loop (conditional requirement).
            continue

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

        elif name == "gender":
            allowed = field.get("allowedValues") or list(ALLOWED_GENDERS)
            if str(value) not in allowed:
                errors.append(FieldError(name, "INVALID_GENDER"))

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

    # Passport is always collected: yes/no, and number + expiry required when yes.
    if payload.hasPassport is None:
        errors.append(FieldError("hasPassport", "REQUIRED"))
    elif payload.hasPassport is True:
        number = (payload.passportNumber or "").strip()
        if not number:
            errors.append(FieldError("passportNumber", "REQUIRED"))
        elif not _PASSPORT_RE.match(number):
            errors.append(FieldError("passportNumber", "PASSPORT_INVALID"))
        if payload.passportExpiresOn is None:
            errors.append(FieldError("passportExpiresOn", "REQUIRED"))
        elif payload.passportExpiresOn < date.today():
            errors.append(FieldError("passportExpiresOn", "PASSPORT_EXPIRED"))
    elif payload.passportNumber and str(payload.passportNumber).strip():
        # Number supplied while answering No — ignore content, clear on persist.
        pass

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


async def _enforce_institution_nomination_quota(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    institution_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> None:
    """Fail-closed per-skill school quota (same max for every institution)."""
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.competition_id != competition_id:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            "Selected skill is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillIds", "SKILL_SELECTION_INVALID")],
        )
    if skill.school_quota is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "School quota not configured for this skill",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillIds", "CONFIG_INCOMPLETE")],
        )

    used = (
        await session.execute(
            select(func.count())
            .select_from(Competitor)
            .where(
                Competitor.competition_id == competition_id,
                Competitor.institution_id == institution_id,
                Competitor.skill_id == skill_id,
                Competitor.status.notin_(list(_QUOTA_EXCLUDED_STATUSES)),
            )
        )
    ).scalar_one()
    if int(used) >= int(skill.school_quota):
        raise AppError(
            "NOMINATION_LIMIT_REACHED",
            "Institution nomination limit reached for this skill",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillIds", "NOMINATION_LIMIT_REACHED")],
        )

async def create_registration(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: RegistrationCreate,
    *,
    idempotency_key: str | None = None,
    actor: User | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> tuple[RegistrationOut, int]:
    if actor is None and actor_id is None:
        raise AppError(
            "UNAUTHORIZED",
            "Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    resolved_actor_id = actor.id if actor is not None else actor_id
    resolved_actor_role = (
        actor.role.value if actor is not None else (actor_role or "ANONYMOUS")
    )
    bind_user_id: uuid.UUID | None = None
    effective_institution_id = payload.institutionId

    if actor is not None and actor.role == UserRole.INSTITUTION:
        if actor.institution_id is None:
            raise AppError(
                "FORBIDDEN",
                "Institution account is not linked to a school",
                status_code=status.HTTP_403_FORBIDDEN,
                fields=[FieldError("institutionId", "FORBIDDEN")],
            )
        if (
            payload.institutionId is not None
            and payload.institutionId != actor.institution_id
        ):
            raise AppError(
                "FORBIDDEN",
                "Cannot register for another institution",
                status_code=status.HTTP_403_FORBIDDEN,
                fields=[FieldError("institutionId", "FORBIDDEN")],
            )
        effective_institution_id = actor.institution_id
        payload = payload.model_copy(update={"institutionId": effective_institution_id})

    if actor is not None and actor.role == UserRole.COMPETITOR:
        bind_user_id = actor.id
        existing_for_user = (
            await session.execute(
                select(Competitor).where(
                    Competitor.competition_id == competition_id,
                    Competitor.user_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if existing_for_user is not None and not idempotency_key:
            raise AppError(
                "DUPLICATE",
                "You already have a registration for this competition",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("userId", "DUPLICATE")],
            )
        if existing_for_user is not None and idempotency_key:
            # Fall through to idempotency lookup below; if no record, still DUPLICATE
            pass

    if idempotency_key:
        existing = (
            await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.competition_id == competition_id,
                    IdempotencyRecord.key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return RegistrationOut.model_validate(existing.response_body), existing.status_code
        if bind_user_id is not None:
            existing_for_user = (
                await session.execute(
                    select(Competitor).where(
                        Competitor.competition_id == competition_id,
                        Competitor.user_id == bind_user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_for_user is not None:
                raise AppError(
                    "DUPLICATE",
                    "You already have a registration for this competition",
                    status_code=status.HTTP_409_CONFLICT,
                    fields=[FieldError("userId", "DUPLICATE")],
                )

    form, window = await load_form_config(session, competition_id)
    if not _window_open(window):
        raise AppError(
            "WINDOW_CLOSED",
            "Registration window is closed",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("window", "WINDOW_CLOSED")],
        )

    _check_abuse(payload.captchaToken)

    _ensure_gender_on_form(form)
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
    if skill is None or skill.competition_id != competition_id or not skill.active:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            "Selected skill is invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("skillIds", "SKILL_SELECTION_INVALID")],
        )

    if actor is not None and actor.role == UserRole.INSTITUTION:
        assert effective_institution_id is not None
        await _enforce_institution_nomination_quota(
            session,
            competition_id,
            institution_id=effective_institution_id,
            skill_id=skill_id,
        )

    if payload.zoneId is not None:
        raise AppError(
            "VALIDATION_ERROR",
            "zoneId must not be supplied; zone is derived from region",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("zoneId", "NOT_ACCEPTED")],
        )

    region_id, zone_id = await resolve_zone_for_registration(
        session,
        competition_id,
        region_id=payload.regionId,
        institution_id=payload.institutionId,
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
        store = storage or get_object_storage()
        stored = store.put(data, prefix=f"cycles/{competition_id}/photos", filename=f"{uuid.uuid4()}.{ext}")
        photo_key = stored.key

    flags: list[str] = []
    if payload.nationalId and payload.dateOfBirth:
        dup = (
            await session.execute(
                select(Competitor).where(
                    Competitor.competition_id == competition_id,
                    Competitor.national_id == payload.nationalId,
                    Competitor.date_of_birth == payload.dateOfBirth,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            flags.append("DUPLICATE_SUSPECTED")

    ref = _issue_ref()
    competitor = Competitor(
        competition_id=competition_id,
        user_id=bind_user_id,
        skill_id=skill_id,
        zone_id=zone_id,
        region_id=region_id,
        institution_id=payload.institutionId,
        ref_no=ref,
        status="PENDING_REVIEW",
        given_names=payload.givenNames,
        family_name=payload.familyName,
        gender=payload.gender,
        date_of_birth=payload.dateOfBirth,
        email=payload.email,
        mobile=payload.mobile,
        whatsapp=payload.whatsapp,
        national_id=payload.nationalId,
        nationality=(payload.nationality or "").strip().upper() or None,
        enrolment_attested=bool(payload.declarationAccepted),
        has_passport=bool(payload.hasPassport),
        passport_number=(payload.passportNumber or "").strip() or None
        if payload.hasPassport
        else None,
        passport_expires_on=payload.passportExpiresOn if payload.hasPassport else None,
        photo_key=photo_key,
        coach=payload.coach,
        flags=flags,
        public_profile_visible=False,
        guardian_name=payload.guardianName,
        guardian_email=payload.guardianEmail,
        guardian_phone=payload.guardianPhone,
        registration_payload={
            "skillIds": [str(s) for s in payload.skillIds],
            "gender": payload.gender,
            "nationality": (payload.nationality or "").strip().upper() or None,
            "hasPassport": bool(payload.hasPassport),
            "passportNumber": (payload.passportNumber or "").strip() or None
            if payload.hasPassport
            else None,
            "passportExpiresOn": payload.passportExpiresOn.isoformat()
            if payload.hasPassport and payload.passportExpiresOn
            else None,
            # Never persist captcha / raw photo bytes in payload
        },
    )
    session.add(competitor)
    await session.flush()

    screen = await screen_competitor(
        session,
        competitor.id,
        actor=actor,
        ip=ip,
        user_agent=user_agent,
        commit=False,
    )
    if not screen.eligible:
        failed_rules = list(screen.failedRules)
        await session.delete(competitor)
        await write_audit_event(
            session,
            action="REGISTRATION_REFUSED_ELIGIBILITY",
            entity_type="Competitor",
            entity_id=str(competitor.id),
            actor_id=resolved_actor_id,
            actor_role=resolved_actor_role,
            competition_id=competition_id,
            after={"failedRules": failed_rules, "reason": "ELIGIBILITY_FAILED"},
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "ELIGIBILITY_FAILED",
            "Registration failed eligibility screening",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("dateOfBirth", rule) for rule in failed_rules]
            or [FieldError("eligibility", "ELIGIBILITY_FAILED")],
        )

    # Institution on-behalf registration: school acts as registering authority;
    # guardian consent is not required for minors.
    if actor is None or actor.role != UserRole.INSTITUTION:
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
    if (
        (actor is None or actor.role != UserRole.INSTITUTION)
        and not can_progress_past_pending_review(competitor)
    ):
        message = (message + "; " if message else "") + "Guardian consent required before progression"

    await enqueue_notification(
        session,
        competition_id=competition_id,
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
        actor_id=resolved_actor_id,
        actor_role=resolved_actor_role,
        competition_id=competition_id,
        after={
            "competitorRef": ref,
            "status": competitor.status,
            "flags": list(competitor.flags or []),
            "userId": str(bind_user_id) if bind_user_id else None,
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
                competition_id=competition_id,
                key=idempotency_key,
                status_code=201,
                response_body=out.model_dump(mode="json"),
            )
        )

    await session.commit()
    return out, 201


DEFAULT_REGISTRATION_FIELDS: list[dict[str, Any]] = [
    {"name": "givenNames", "type": "string", "required": True, "maxLength": 100},
    {"name": "familyName", "type": "string", "required": True, "maxLength": 100},
    {
        "name": "gender",
        "type": "enum",
        "required": True,
        "allowedValues": ["Male", "Female"],
    },
    {"name": "dateOfBirth", "type": "date", "required": True},
    {"name": "email", "type": "email", "required": True},
    {"name": "mobile", "type": "phone", "required": True},
    {"name": "nationalId", "type": "string", "required": True},
    {"name": "hasPassport", "type": "boolean", "required": True},
    {"name": "passportNumber", "type": "string", "required": False, "maxLength": 64},
    {"name": "passportExpiresOn", "type": "date", "required": False},
    {"name": "institutionId", "type": "uuid", "required": False},
    {"name": "regionId", "type": "uuid", "required": False},
    {"name": "skillIds", "type": "array", "required": True},
    {"name": "declarationAccepted", "type": "boolean", "required": True},
    {"name": "photo", "type": "file", "required": True},
]


def _form_admin_out(form: RegistrationFormDefinition) -> RegistrationFormAdminOut:
    fields = [
        FormFieldOut(
            name=str(f.get("name")),
            type=str(f.get("type", "string")),
            required=bool(f.get("required", False)),
            maxLength=f.get("maxLength"),
            pattern=f.get("pattern"),
            allowedValues=f.get("allowedValues"),
        )
        for f in (form.fields or [])
    ]
    return RegistrationFormAdminOut(
        fields=fields,
        maxSkills=form.max_skills,
        photoMaxMb=form.photo_max_mb,
        photoFormats=list(form.photo_formats or []),
        nationalIdPattern=form.national_id_pattern,
        minorAgeUnder=form.minor_age_under,
        minorReferenceDate=form.minor_reference_date,
    )


async def get_registration_window(
    session: AsyncSession, competition_id: uuid.UUID
) -> RegistrationWindowOut | None:
    window = (
        await session.execute(select(RegistrationWindow).where(RegistrationWindow.competition_id == competition_id))
    ).scalar_one_or_none()
    if window is None:
        return None
    return RegistrationWindowOut(
        opensAt=window.opens_at.isoformat(),
        closesAt=window.closes_at.isoformat(),
    )


async def upsert_registration_window(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: RegistrationWindowUpdate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationWindowOut:
    opens_at = _as_naive(payload.opensAt)
    closes_at = _as_naive(payload.closesAt)
    if closes_at <= opens_at:
        raise AppError(
            "VALIDATION_ERROR",
            "closesAt must be after opensAt",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("closesAt", "BEFORE_OPENS")],
        )
    window = (
        await session.execute(select(RegistrationWindow).where(RegistrationWindow.competition_id == competition_id))
    ).scalar_one_or_none()
    before = None
    if window is None:
        window = RegistrationWindow(
            competition_id=competition_id,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        session.add(window)
    else:
        before = {"opensAt": window.opens_at.isoformat(), "closesAt": window.closes_at.isoformat()}
        window.opens_at = opens_at
        window.closes_at = closes_at
    await session.flush()
    after = {"opensAt": window.opens_at.isoformat(), "closesAt": window.closes_at.isoformat()}
    await write_audit_event(
        session,
        action="REGISTRATION_WINDOW_UPSERT",
        entity_type="RegistrationWindow",
        entity_id=str(window.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return RegistrationWindowOut(**after)


async def get_registration_form_admin(
    session: AsyncSession, competition_id: uuid.UUID
) -> RegistrationFormAdminOut | None:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.competition_id == competition_id)
        )
    ).scalar_one_or_none()
    if form is None:
        return None
    return _form_admin_out(form)


async def upsert_registration_form_admin(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: RegistrationFormAdminUpdate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> RegistrationFormAdminOut:
    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.competition_id == competition_id)
        )
    ).scalar_one_or_none()
    before = None
    if form is None:
        form = RegistrationFormDefinition(
            competition_id=competition_id,
            fields=list(DEFAULT_REGISTRATION_FIELDS),
            max_skills=1,
            photo_max_mb=2,
            photo_formats=["image/jpeg", "image/png"],
            national_id_pattern=None,
            minor_age_under=18,
            minor_reference_date=None,
        )
        session.add(form)
        await session.flush()
    else:
        before = _form_admin_out(form).model_dump(mode="json")

    if payload.useDefaults:
        form.fields = list(DEFAULT_REGISTRATION_FIELDS)
        form.max_skills = 1
        form.photo_max_mb = 2
        form.photo_formats = ["image/jpeg", "image/png"]
        form.national_id_pattern = None
        form.minor_age_under = 18
    else:
        if payload.fields is not None:
            form.fields = [f.model_dump(exclude_none=True) for f in payload.fields]
        if payload.maxSkills is not None:
            form.max_skills = payload.maxSkills
        if payload.photoMaxMb is not None:
            form.photo_max_mb = payload.photoMaxMb
        if payload.photoFormats is not None:
            form.photo_formats = list(payload.photoFormats)
        if payload.nationalIdPattern is not None:
            form.national_id_pattern = payload.nationalIdPattern or None
        if payload.minorAgeUnder is not None:
            form.minor_age_under = payload.minorAgeUnder
        if payload.minorReferenceDate is not None:
            form.minor_reference_date = payload.minorReferenceDate

    await session.flush()
    out = _form_admin_out(form)
    await write_audit_event(
        session,
        action="REGISTRATION_FORM_UPSERT",
        entity_type="RegistrationFormDefinition",
        entity_id=str(form.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=out.model_dump(mode="json"),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return out
