"""Online competitor registration — config-driven form, window, abuse, duplicates."""

from __future__ import annotations

import base64
import logging
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
    CoachBioIn,
    FormFieldOut,
    RegistrationCreate,
    RegistrationDraftIn,
    RegistrationDraftOut,
    RegistrationFormAdminOut,
    RegistrationFormAdminUpdate,
    RegistrationFormOut,
    RegistrationOut,
    RegistrationWindowOut,
    RegistrationWindowUpdate,
)
from app.services.audit import write_audit_event
from app.services.eligibility import screen_competitor
from app.services.geography import resolve_zone_for_registration
from app.services.nominations import enqueue_notification
from app.services.sms.phone import is_valid_ghana_phone
from app.services.storage import ObjectStorage, get_object_storage

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[\w\s\-'.À-ȕ]+$", re.UNICODE)
_PASSPORT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\s]{4,62}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Testable abuse tokens (real CAPTCHA provider later)
_CAPTCHA_OK = {"ok", "valid", "pass"}
_CAPTCHA_RATE = {"rate-limited", "rate_limit"}

ALLOWED_GENDERS = frozenset({"Male", "Female"})
ALLOWED_AFFILIATION_TYPES = frozenset({"school", "company", "workshop"})
ALLOWED_ID_DOCUMENT_KINDS = frozenset({"GHANA_CARD", "OTHER"})
ALLOWED_OTHER_ID_TYPES = frozenset({"Passport", "Driver's License", "Student ID"})
ALLOWED_HEARD_ABOUT = frozenset(
    {
        "Social media",
        "Newspaper",
        "Friend",
        "Radio",
        "Television",
        "Website (CTVET/WorldSkills)",
        "Other means",
    }
)
_HEARD_ABOUT_VALUES = [
    "Social media",
    "Newspaper",
    "Friend",
    "Radio",
    "Television",
    "Website (CTVET/WorldSkills)",
    "Other means",
]
_QUOTA_EXCLUDED_STATUSES = frozenset({"REJECTED", "WITHDRAWN", "DRAFT"})
_DRAFT_STATUS = "DRAFT"
_GENDER_FIELD = {
    "name": "gender",
    "type": "enum",
    "required": True,
    "allowedValues": ["Male", "Female"],
}

# Injected when older competition form configs omit newer profile fields.
# Guardian contacts are optional informational fields for all ages.
_PROFILE_ENSURE_FIELDS: list[dict[str, Any]] = [
    {"name": "whatsapp", "type": "phone", "required": True},
    {"name": "guardianName", "type": "string", "required": False, "maxLength": 200},
    {"name": "guardianPhone", "type": "phone", "required": False},
    {
        "name": "heardAbout",
        "type": "enum",
        "required": True,
        "allowedValues": list(_HEARD_ABOUT_VALUES),
    },
]


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


def _ensure_profile_fields_on_form(form: RegistrationFormDefinition) -> None:
    """Guarantee WhatsApp, guardian, and how-heard even when older form configs omit them."""
    fields = list(form.fields or [])
    existing = {str(f.get("name")) for f in fields}
    missing = [dict(spec) for spec in _PROFILE_ENSURE_FIELDS if str(spec["name"]) not in existing]
    if missing:
        insert_at = next(
            (i + 1 for i, f in enumerate(fields) if str(f.get("name")) == "mobile"),
            next(
                (i + 1 for i, f in enumerate(fields) if str(f.get("name")) == "email"),
                len(fields),
            ),
        )
        for offset, spec in enumerate(missing):
            fields.insert(insert_at + offset, spec)

    # Keep heard-about options current for competitions that already have the field.
    for field in fields:
        if str(field.get("name")) == "heardAbout":
            field["type"] = "enum"
            field["required"] = True
            field["allowedValues"] = list(_HEARD_ABOUT_VALUES)
            break

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
    _ensure_profile_fields_on_form(form)
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
        minorAgeUnder=form.minor_age_under,
        minorReferenceDate=form.minor_reference_date,
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
        "idDocumentKind": payload.idDocumentKind,
        "otherIdType": payload.otherIdType,
        "hasPassport": payload.hasPassport,
        "passportNumber": payload.passportNumber,
        "passportExpiresOn": payload.passportExpiresOn,
        "affiliationType": payload.affiliationType,
        "organizationName": payload.organizationName,
        "organizationCity": payload.organizationCity,
        "organizationPhone": payload.organizationPhone,
        "organizationEmail": payload.organizationEmail,
        "heardAbout": payload.heardAbout,
        "institutionId": payload.institutionId,
        "regionId": payload.regionId,
        "zoneId": payload.zoneId,
        "skillIds": payload.skillIds,
        "coach": payload.coach,
        "declarationAccepted": payload.declarationAccepted,
        "photo": payload.photo,
        "guardianName": payload.guardianName,
        "guardianEmail": payload.guardianEmail,
        "guardianPhone": payload.guardianPhone,
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
            # Region validated in affiliation rules (catalog school carries region).
            continue

        if name in {
            "affiliationType",
            "organizationName",
            "organizationCity",
            "organizationPhone",
            "organizationEmail",
            "idDocumentKind",
            "otherIdType",
            "nationalId",
            "heardAbout",
            "guardianName",
            "guardianEmail",
            "guardianPhone",
        }:
            # Validated after the form loop (conditional / cross-field rules).
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
            if not is_valid_ghana_phone(str(value)):
                errors.append(FieldError(name, "PHONE_INVALID"))

        elif name == "nationalId":
            # Ghana Card pattern applied only when idDocumentKind is GHANA_CARD (see below).
            pass

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

    errors.extend(_validate_id_document(form, payload))
    errors.extend(_validate_affiliation(payload))
    errors.extend(_validate_heard_about(payload))

    return errors


def _validate_id_document(
    form: RegistrationFormDefinition, payload: RegistrationCreate
) -> list[FieldError]:
    """ID document is optional; validate format only when fields are provided."""
    errors: list[FieldError] = []
    kind = (payload.idDocumentKind or "").strip() or None
    other = (payload.otherIdType or "").strip() or None
    national_id = (payload.nationalId or "").strip() or None

    if not kind and not national_id and not other:
        return errors

    if kind and kind not in ALLOWED_ID_DOCUMENT_KINDS:
        errors.append(FieldError("idDocumentKind", "INVALID"))
        return errors

    if not kind:
        errors.append(FieldError("idDocumentKind", "REQUIRED"))
        return errors

    if not national_id:
        errors.append(FieldError("nationalId", "REQUIRED"))
    elif kind == "GHANA_CARD" and form.national_id_pattern:
        if not re.fullmatch(form.national_id_pattern, national_id):
            errors.append(FieldError("nationalId", "ID_INVALID"))

    if kind == "OTHER":
        if not other:
            errors.append(FieldError("otherIdType", "REQUIRED"))
        elif other not in ALLOWED_OTHER_ID_TYPES:
            errors.append(FieldError("otherIdType", "INVALID"))
    return errors


def _normalize_affiliation_type(raw: str | None) -> str | None:
    """Map blank / 'none' to unaffiliated (None); otherwise return stripped type."""
    aff = (raw or "").strip() or None
    if aff is None or aff == "none":
        return None
    return aff


def _validate_affiliation(payload: RegistrationCreate) -> list[FieldError]:
    errors: list[FieldError] = []
    aff = _normalize_affiliation_type(payload.affiliationType)
    if aff is None:
        # Unaffiliated: region required for zone derivation; no org / institution.
        if payload.regionId is None:
            errors.append(FieldError("regionId", "REQUIRED"))
        if payload.institutionId is not None:
            errors.append(FieldError("institutionId", "NOT_ALLOWED"))
        return errors
    if aff not in ALLOWED_AFFILIATION_TYPES:
        errors.append(FieldError("affiliationType", "INVALID"))
        return errors

    org_phone = (payload.organizationPhone or "").strip()
    org_email = (payload.organizationEmail or "").strip()
    if not org_phone:
        errors.append(FieldError("organizationPhone", "REQUIRED"))
    elif not is_valid_ghana_phone(org_phone):
        errors.append(FieldError("organizationPhone", "PHONE_INVALID"))
    if not org_email:
        errors.append(FieldError("organizationEmail", "REQUIRED"))
    elif not _EMAIL_RE.match(org_email):
        errors.append(FieldError("organizationEmail", "EMAIL_INVALID"))

    org_name = (payload.organizationName or "").strip() or None
    org_city = (payload.organizationCity or "").strip() or None

    if aff == "school":
        if payload.institutionId is not None:
            # Catalog school supplies region; free-text org name/city not needed.
            pass
        else:
            if not org_name:
                errors.append(FieldError("organizationName", "REQUIRED"))
            if payload.regionId is None:
                errors.append(FieldError("regionId", "REQUIRED"))
    else:
        # company / workshop
        if not org_name:
            errors.append(FieldError("organizationName", "REQUIRED"))
        if payload.regionId is None:
            errors.append(FieldError("regionId", "REQUIRED"))
        if not org_city:
            errors.append(FieldError("organizationCity", "REQUIRED"))
        if payload.institutionId is not None:
            errors.append(FieldError("institutionId", "NOT_ALLOWED"))

    return errors


def _validate_heard_about(payload: RegistrationCreate) -> list[FieldError]:
    heard = (payload.heardAbout or "").strip() or None
    if not heard:
        return [FieldError("heardAbout", "REQUIRED")]
    if heard not in ALLOWED_HEARD_ABOUT:
        return [FieldError("heardAbout", "INVALID")]
    return []


def _validate_guardian_contacts(payload: RegistrationCreate) -> list[FieldError]:
    """Guardian name/phone are optional informational fields; validate format if present."""
    errors: list[FieldError] = []
    phone = (payload.guardianPhone or "").strip() or None
    if phone and not is_valid_ghana_phone(phone):
        errors.append(FieldError("guardianPhone", "PHONE_INVALID"))
    return errors


def _coach_payload_is_blank(raw: CoachBioIn | dict[str, Any] | None) -> bool:
    if raw is None:
        return True
    if isinstance(raw, CoachBioIn):
        data = raw.model_dump(mode="json")
    elif isinstance(raw, dict):
        data = raw
    else:
        return False
    keys = (
        "surname",
        "firstName",
        "otherName",
        "contactNumber",
        "email",
        "whatsapp",
        "dateOfBirth",
    )
    return not any(str(data.get(k) or "").strip() for k in keys)


def _validate_and_normalize_coach(payload: RegistrationCreate) -> dict[str, Any] | None:
    """Coach bio-data is optional; when any field is provided, all required fields must be valid."""
    raw = payload.coach
    if _coach_payload_is_blank(raw):
        return None
    try:
        if isinstance(raw, CoachBioIn):
            coach = raw
        else:
            coach = CoachBioIn.model_validate(raw)
    except Exception as exc:
        fields: list[FieldError] = []
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            for err in exc.errors():
                loc = err.get("loc") or ()
                name = str(loc[0]) if loc else "coach"
                fields.append(FieldError(f"coach.{name}", "REQUIRED"))
        if not fields:
            fields = [FieldError("coach", "REQUIRED")]
        raise AppError(
            "VALIDATION_ERROR",
            "Coach / team leader details are incomplete or invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=fields,
        ) from exc

    if coach.dateOfBirth >= date.today():
        raise AppError(
            "VALIDATION_ERROR",
            "Coach date of birth is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("coach.dateOfBirth", "INVALID_DATE")],
        )
    if not is_valid_ghana_phone(coach.contactNumber):
        raise AppError(
            "VALIDATION_ERROR",
            "Coach contact number is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("coach.contactNumber", "PHONE_INVALID")],
        )
    whatsapp = coach.resolved_whatsapp()
    if not is_valid_ghana_phone(whatsapp):
        raise AppError(
            "VALIDATION_ERROR",
            "Coach WhatsApp number is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("coach.contactNumber", "PHONE_INVALID")],
        )
    if not _EMAIL_RE.match(coach.email):
        raise AppError(
            "VALIDATION_ERROR",
            "Coach email is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("coach.email", "EMAIL_INVALID")],
        )
    data = coach.model_dump(mode="json")
    data["whatsapp"] = whatsapp
    return data


def _validate_photo(form: RegistrationFormDefinition, payload: RegistrationCreate) -> tuple[bytes, str] | None:
    # Photo required if listed in form
    photo_required = any(f.get("name") == "photo" and f.get("required") for f in (form.fields or []))
    if payload.photo is None:
        if photo_required:
            raise AppError(
                "PHOTO_INVALID",
                "Photo is required",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("photo", "PHOTO_INVALID")],
            )
        return None

    formats = [str(f).lower() for f in (form.photo_formats or ["image/jpeg", "image/png"])]
    content_type = payload.photo.contentType.lower()
    if content_type not in formats:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        )
    try:
        data = base64.b64decode(payload.photo.contentBase64, validate=True)
    except Exception as exc:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        ) from exc

    max_bytes = form.photo_max_mb * 1024 * 1024
    if len(data) > max_bytes or len(data) == 0:
        raise AppError(
            "PHOTO_INVALID",
            f"Accepted formats: {', '.join(formats)}; max {form.photo_max_mb}MB",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("photo", "PHOTO_INVALID")],
        )
    # Minimal EXIF strip stub: JPEG APP1 segment removal is best-effort; store raw for MVP.
    return data, content_type


def _issue_ref() -> str:
    return f"WSGH-{date.today().year}-{uuid.uuid4().hex[:8].upper()}"


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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

async def _find_competitor_draft_for_user(
    session: AsyncSession,
    competition_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Competitor | None:
    return (
        await session.execute(
            select(Competitor).where(
                Competitor.competition_id == competition_id,
                Competitor.user_id == user_id,
                Competitor.status == _DRAFT_STATUS,
            )
        )
    ).scalar_one_or_none()


async def _find_competitor_for_user(
    session: AsyncSession,
    competition_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Competitor | None:
    return (
        await session.execute(
            select(Competitor).where(
                Competitor.competition_id == competition_id,
                Competitor.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _draft_payload_dict(competitor: Competitor) -> dict[str, Any]:
    raw = competitor.registration_payload
    return dict(raw) if isinstance(raw, dict) else {}


async def _draft_out(session: AsyncSession, competitor: Competitor) -> RegistrationDraftOut:
    payload = _draft_payload_dict(competitor)
    skill_ids_raw = payload.get("skillIds") or []
    skill_ids: list[uuid.UUID] = []
    for item in skill_ids_raw:
        try:
            skill_ids.append(uuid.UUID(str(item)))
        except (ValueError, TypeError):
            continue
    if not skill_ids and competitor.skill_id is not None:
        skill_ids = [competitor.skill_id]

    has_passport = payload.get("hasPassport")
    if has_passport is None:
        has_passport = bool(competitor.has_passport) if competitor.has_passport else None

    coach = competitor.coach if isinstance(competitor.coach, dict) else payload.get("coach")
    if coach is not None and not isinstance(coach, dict):
        coach = None

    current_step = payload.get("currentStep")
    try:
        step_out = int(current_step) if current_step is not None else None
    except (TypeError, ValueError):
        step_out = None

    updated = competitor.updated_at or _now()

    institution_name: str | None = None
    institution_code: str | None = None
    if competitor.institution_id is not None:
        inst = await session.get(Institution, competitor.institution_id)
        if inst is not None:
            institution_name = inst.name
            institution_code = inst.code
    if not institution_name and isinstance(payload.get("institutionName"), str):
        institution_name = payload["institutionName"] or None
    if not institution_code and isinstance(payload.get("institutionCode"), str):
        institution_code = payload["institutionCode"] or None

    return RegistrationDraftOut(
        competitorId=competitor.id,
        status=competitor.status,
        updatedAt=updated,
        currentStep=step_out,
        givenNames=competitor.given_names or payload.get("givenNames"),
        familyName=competitor.family_name or payload.get("familyName"),
        gender=competitor.gender or payload.get("gender"),
        dateOfBirth=competitor.date_of_birth
        or (
            date.fromisoformat(payload["dateOfBirth"])
            if isinstance(payload.get("dateOfBirth"), str)
            else payload.get("dateOfBirth")
        ),
        email=competitor.email or payload.get("email"),
        mobile=competitor.mobile or payload.get("mobile"),
        whatsapp=competitor.whatsapp or payload.get("whatsapp"),
        nationalId=competitor.national_id or payload.get("nationalId"),
        idDocumentKind=getattr(competitor, "id_document_kind", None)
        or payload.get("idDocumentKind"),
        otherIdType=getattr(competitor, "other_id_type", None) or payload.get("otherIdType"),
        nationality=competitor.nationality or payload.get("nationality"),
        hasPassport=has_passport,
        passportNumber=competitor.passport_number or payload.get("passportNumber"),
        passportExpiresOn=competitor.passport_expires_on
        or (
            date.fromisoformat(payload["passportExpiresOn"])
            if isinstance(payload.get("passportExpiresOn"), str)
            else payload.get("passportExpiresOn")
        ),
        affiliationType=getattr(competitor, "affiliation_type", None)
        or payload.get("affiliationType"),
        organizationName=getattr(competitor, "organization_name", None)
        or payload.get("organizationName"),
        organizationCity=getattr(competitor, "organization_city", None)
        or payload.get("organizationCity"),
        organizationPhone=getattr(competitor, "organization_phone", None)
        or payload.get("organizationPhone"),
        organizationEmail=getattr(competitor, "organization_email", None)
        or payload.get("organizationEmail"),
        heardAbout=getattr(competitor, "heard_about", None) or payload.get("heardAbout"),
        institutionId=competitor.institution_id
        or (
            uuid.UUID(str(payload["institutionId"]))
            if payload.get("institutionId")
            else None
        ),
        regionId=competitor.region_id
        or (uuid.UUID(str(payload["regionId"])) if payload.get("regionId") else None),
        skillIds=skill_ids,
        coach=coach,
        declarationAccepted=payload.get("declarationAccepted"),
        hasPhoto=bool(competitor.photo_key),
        institutionName=institution_name,
        institutionCode=institution_code,
        guardianName=competitor.guardian_name or payload.get("guardianName"),
        guardianEmail=competitor.guardian_email or payload.get("guardianEmail"),
        guardianPhone=competitor.guardian_phone or payload.get("guardianPhone"),
    )


async def get_registration_draft(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> RegistrationDraftOut:
    if actor.role != UserRole.COMPETITOR:
        raise AppError(
            "FORBIDDEN",
            "Only competitors may load registration drafts",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    draft = await _find_competitor_draft_for_user(session, competition_id, actor.id)
    if draft is None:
        raise AppError(
            "DRAFT_NOT_FOUND",
            "No registration draft found for this competition",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return await _draft_out(session, draft)


async def upsert_registration_draft(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: RegistrationDraftIn,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> RegistrationDraftOut:
    if actor.role != UserRole.COMPETITOR:
        raise AppError(
            "FORBIDDEN",
            "Only competitors may save registration drafts",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    form, window = await load_form_config(session, competition_id)
    if not _window_open(window):
        raise AppError(
            "WINDOW_CLOSED",
            "Registration window is closed",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("window", "WINDOW_CLOSED")],
        )

    existing = await _find_competitor_for_user(session, competition_id, actor.id)
    if existing is not None and existing.status != _DRAFT_STATUS:
        raise AppError(
            "DUPLICATE",
            "You already have a registration for this competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("userId", "DUPLICATE")],
        )

    draft = existing
    if draft is None:
        draft = Competitor(
            competition_id=competition_id,
            user_id=actor.id,
            skill_id=None,
            zone_id=None,
            region_id=None,
            institution_id=None,
            ref_no=None,
            status=_DRAFT_STATUS,
            flags=[],
            registration_payload={},
            has_passport=False,
            enrolment_attested=False,
            public_profile_visible=False,
            updated_at=_now(),
        )
        session.add(draft)
        await session.flush()

    data = payload.model_dump(exclude_unset=True)
    payload_json = _draft_payload_dict(draft)

    if "givenNames" in data:
        draft.given_names = (data["givenNames"] or "").strip() or None
        payload_json["givenNames"] = draft.given_names
    if "familyName" in data:
        draft.family_name = (data["familyName"] or "").strip() or None
        payload_json["familyName"] = draft.family_name
    if "gender" in data:
        draft.gender = data["gender"]
        payload_json["gender"] = data["gender"]
    if "dateOfBirth" in data:
        draft.date_of_birth = data["dateOfBirth"]
        payload_json["dateOfBirth"] = (
            data["dateOfBirth"].isoformat() if data["dateOfBirth"] else None
        )
    if "email" in data:
        draft.email = (data["email"] or "").strip().lower() or None
        payload_json["email"] = draft.email
    if "mobile" in data:
        draft.mobile = (data["mobile"] or "").strip() or None
        payload_json["mobile"] = draft.mobile
    if "whatsapp" in data:
        draft.whatsapp = (data["whatsapp"] or "").strip() or None
        payload_json["whatsapp"] = draft.whatsapp
    if "nationalId" in data:
        draft.national_id = (data["nationalId"] or "").strip() or None
        payload_json["nationalId"] = draft.national_id
    if "idDocumentKind" in data:
        draft.id_document_kind = (data["idDocumentKind"] or "").strip() or None
        payload_json["idDocumentKind"] = draft.id_document_kind
        if draft.id_document_kind != "OTHER":
            draft.other_id_type = None
            payload_json["otherIdType"] = None
    if "otherIdType" in data:
        draft.other_id_type = (data["otherIdType"] or "").strip() or None
        payload_json["otherIdType"] = draft.other_id_type
    if "nationality" in data:
        draft.nationality = (data["nationality"] or "").strip().upper() or None
        payload_json["nationality"] = draft.nationality
    if "hasPassport" in data:
        draft.has_passport = bool(data["hasPassport"]) if data["hasPassport"] is not None else False
        payload_json["hasPassport"] = data["hasPassport"]
        if data["hasPassport"] is False:
            draft.passport_number = None
            draft.passport_expires_on = None
            payload_json["passportNumber"] = None
            payload_json["passportExpiresOn"] = None
    if "passportNumber" in data:
        draft.passport_number = (data["passportNumber"] or "").strip() or None
        payload_json["passportNumber"] = draft.passport_number
    if "passportExpiresOn" in data:
        draft.passport_expires_on = data["passportExpiresOn"]
        payload_json["passportExpiresOn"] = (
            data["passportExpiresOn"].isoformat() if data["passportExpiresOn"] else None
        )
    if "affiliationType" in data:
        draft.affiliation_type = (data["affiliationType"] or "").strip() or None
        payload_json["affiliationType"] = draft.affiliation_type
    if "organizationName" in data:
        draft.organization_name = (data["organizationName"] or "").strip() or None
        payload_json["organizationName"] = draft.organization_name
    if "organizationCity" in data:
        draft.organization_city = (data["organizationCity"] or "").strip() or None
        payload_json["organizationCity"] = draft.organization_city
    if "organizationPhone" in data:
        draft.organization_phone = (data["organizationPhone"] or "").strip() or None
        payload_json["organizationPhone"] = draft.organization_phone
    if "organizationEmail" in data:
        draft.organization_email = (
            (data["organizationEmail"] or "").strip().lower() or None
        )
        payload_json["organizationEmail"] = draft.organization_email
    if "heardAbout" in data:
        draft.heard_about = (data["heardAbout"] or "").strip() or None
        payload_json["heardAbout"] = draft.heard_about
    if "institutionId" in data:
        draft.institution_id = data["institutionId"]
        payload_json["institutionId"] = (
            str(data["institutionId"]) if data["institutionId"] else None
        )
        if data["institutionId"] is None:
            payload_json["institutionName"] = None
            payload_json["institutionCode"] = None
        else:
            inst = await session.get(Institution, data["institutionId"])
            if inst is not None:
                payload_json["institutionName"] = inst.name
                payload_json["institutionCode"] = inst.code
    if "regionId" in data:
        draft.region_id = data["regionId"]
        payload_json["regionId"] = str(data["regionId"]) if data["regionId"] else None
    if "guardianName" in data:
        draft.guardian_name = (data["guardianName"] or "").strip() or None
        payload_json["guardianName"] = draft.guardian_name
    if "guardianEmail" in data:
        draft.guardian_email = (data["guardianEmail"] or "").strip() or None
        payload_json["guardianEmail"] = draft.guardian_email
    if "guardianPhone" in data:
        draft.guardian_phone = (data["guardianPhone"] or "").strip() or None
        payload_json["guardianPhone"] = draft.guardian_phone
    if "declarationAccepted" in data:
        payload_json["declarationAccepted"] = data["declarationAccepted"]
        draft.enrolment_attested = bool(data["declarationAccepted"])
    if "currentStep" in data and data["currentStep"] is not None:
        payload_json["currentStep"] = int(data["currentStep"])

    if "skillIds" in data and data["skillIds"] is not None:
        skill_ids = list(data["skillIds"])
        payload_json["skillIds"] = [str(s) for s in skill_ids]
        if skill_ids:
            skill = await session.get(Skill, skill_ids[0])
            if skill is not None and skill.competition_id == competition_id and skill.active:
                draft.skill_id = skill.id
            else:
                draft.skill_id = None
        else:
            draft.skill_id = None

    if "coach" in data:
        coach_raw = data["coach"]
        if coach_raw is None:
            draft.coach = None
            payload_json["coach"] = None
        elif isinstance(coach_raw, dict):
            cleaned: dict[str, Any] = {}
            for key, value in coach_raw.items():
                if isinstance(value, str):
                    stripped = value.strip()
                    cleaned[key] = stripped or None
                elif isinstance(value, date):
                    cleaned[key] = value.isoformat()
                else:
                    cleaned[key] = value
            draft.coach = cleaned
            payload_json["coach"] = cleaned

    if "photo" in data and data["photo"] is not None:
        photo_data = _validate_photo_optional(form, payload.photo)
        blob, content_type = photo_data
        ext = "jpg" if "jpeg" in content_type else "png"
        store = storage or get_object_storage()
        stored = store.put(
            blob,
            prefix=f"cycles/{competition_id}/photos",
            filename=f"{uuid.uuid4()}.{ext}",
        )
        draft.photo_key = stored.key
        payload_json["hasPhoto"] = True
        payload_json["photoContentType"] = content_type

    # Best-effort zone resolution when geography fields are present
    try:
        region_id, zone_id = await resolve_zone_for_registration(
            session,
            competition_id,
            region_id=draft.region_id,
            institution_id=draft.institution_id,
        )
        if region_id is not None:
            draft.region_id = region_id
        if zone_id is not None:
            draft.zone_id = zone_id
    except AppError:
        pass

    draft.status = _DRAFT_STATUS
    draft.updated_at = _now()
    draft.registration_payload = payload_json

    await write_audit_event(
        session,
        action="REGISTRATION_DRAFT_SAVE",
        entity_type="Competitor",
        entity_id=str(draft.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after={"status": _DRAFT_STATUS, "currentStep": payload_json.get("currentStep")},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(draft)
    return await _draft_out(session, draft)


async def get_registration_draft_photo(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str, str]:
    """Return saved draft photo bytes, content-type, and filename for the actor."""
    if actor.role != UserRole.COMPETITOR:
        raise AppError(
            "FORBIDDEN",
            "Only competitors may load registration draft photos",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    draft = await _find_competitor_draft_for_user(session, competition_id, actor.id)
    if draft is None or not draft.photo_key:
        raise AppError(
            "DRAFT_PHOTO_NOT_FOUND",
            "No saved photo on this registration draft",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    store = storage or get_object_storage()
    try:
        data = store.get(draft.photo_key)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            "FILE_NOT_FOUND",
            "Draft photo could not be read",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    payload = _draft_payload_dict(draft)
    content_type = payload.get("photoContentType")
    if not isinstance(content_type, str) or not content_type:
        key_lower = draft.photo_key.lower()
        if key_lower.endswith(".png"):
            content_type = "image/png"
        else:
            content_type = "image/jpeg"
    ext = "png" if "png" in content_type else "jpg"
    filename = f"registration-photo.{ext}"
    return data, content_type, filename


def _validate_photo_optional(form: RegistrationFormDefinition, photo) -> tuple[bytes, str]:
    """Validate provided photo bytes/type without requiring presence."""
    fake = RegistrationCreate(photo=photo)
    # Temporarily mark photo as not required
    original = list(form.fields or [])
    patched = []
    for field in original:
        if str(field.get("name")) == "photo":
            patched.append({**field, "required": False})
        else:
            patched.append(field)
    form.fields = patched
    try:
        result = _validate_photo(form, fake)
        if result is None:
            raise AppError(
                "PHOTO_INVALID",
                "Photo is invalid",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("photo", "PHOTO_INVALID")],
            )
        return result
    finally:
        form.fields = original


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
        from app.services import settings as settings_service

        if not await settings_service.institution_registration_enabled(session):
            raise AppError(
                "INSTITUTION_REGISTRATION_DISABLED",
                "Institution registration is currently disabled",
                status_code=status.HTTP_403_FORBIDDEN,
            )
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
        payload = payload.model_copy(
            update={
                "institutionId": effective_institution_id,
                "affiliationType": "school",
                "organizationName": None,
                "organizationCity": None,
            }
        )

    draft_to_finalize: Competitor | None = None
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
        if existing_for_user is not None:
            if existing_for_user.status == _DRAFT_STATUS:
                draft_to_finalize = existing_for_user
            elif not idempotency_key:
                raise AppError(
                    "DUPLICATE",
                    "You already have a registration for this competition",
                    status_code=status.HTTP_409_CONFLICT,
                    fields=[FieldError("userId", "DUPLICATE")],
                )

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
        if bind_user_id is not None and draft_to_finalize is None:
            existing_for_user = (
                await session.execute(
                    select(Competitor).where(
                        Competitor.competition_id == competition_id,
                        Competitor.user_id == bind_user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_for_user is not None and existing_for_user.status != _DRAFT_STATUS:
                raise AppError(
                    "DUPLICATE",
                    "You already have a registration for this competition",
                    status_code=status.HTTP_409_CONFLICT,
                    fields=[FieldError("userId", "DUPLICATE")],
                )
            if existing_for_user is not None and existing_for_user.status == _DRAFT_STATUS:
                draft_to_finalize = existing_for_user

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
    _ensure_profile_fields_on_form(form)
    field_errors = _validate_against_form(form, payload)
    field_errors.extend(_validate_guardian_contacts(payload))
    # Draft may already hold a saved photo; omit photo REQUIRED in that case.
    if (
        draft_to_finalize is not None
        and draft_to_finalize.photo_key
        and payload.photo is None
    ):
        field_errors = [
            err
            for err in field_errors
            if not (err.name == "photo" and err.reason == "REQUIRED")
        ]
    if field_errors:
        raise AppError(
            "VALIDATION_ERROR",
            "Registration validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=field_errors,
        )

    if len(payload.skillIds) != form.max_skills:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            f"Exactly {form.max_skills} skill(s) must be selected",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("skillIds", "SKILL_SELECTION_INVALID")],
        )

    skill_id = payload.skillIds[0]
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.competition_id != competition_id or not skill.active:
        raise AppError(
            "SKILL_SELECTION_INVALID",
            "Selected skill is invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("institutionId", "REQUIRED")],
            )

    photo_data = None
    try:
        photo_data = _validate_photo(form, payload)
    except AppError as photo_err:
        if (
            photo_err.code == "PHOTO_INVALID"
            and payload.photo is None
            and draft_to_finalize is not None
            and draft_to_finalize.photo_key
        ):
            photo_data = None
        else:
            raise
    photo_key: str | None = None
    if photo_data is not None:
        data, content_type = photo_data
        ext = "jpg" if "jpeg" in content_type else "png"
        store = storage or get_object_storage()
        stored = store.put(data, prefix=f"cycles/{competition_id}/photos", filename=f"{uuid.uuid4()}.{ext}")
        photo_key = stored.key
    elif draft_to_finalize is not None and draft_to_finalize.photo_key:
        photo_key = draft_to_finalize.photo_key

    coach_data = _validate_and_normalize_coach(payload)

    flags: list[str] = []
    if payload.nationalId and payload.dateOfBirth:
        dup = (
            await session.execute(
                select(Competitor).where(
                    Competitor.competition_id == competition_id,
                    Competitor.national_id == payload.nationalId,
                    Competitor.date_of_birth == payload.dateOfBirth,
                    Competitor.status != _DRAFT_STATUS,
                )
            )
        ).scalar_one_or_none()
        if dup is not None and (draft_to_finalize is None or dup.id != draft_to_finalize.id):
            flags.append("DUPLICATE_SUSPECTED")

    ref = _issue_ref()
    id_kind = (payload.idDocumentKind or "").strip() or None
    other_id = (
        (payload.otherIdType or "").strip() or None if id_kind == "OTHER" else None
    )
    aff = _normalize_affiliation_type(payload.affiliationType)
    org_name = (payload.organizationName or "").strip() or None
    org_city = (payload.organizationCity or "").strip() or None
    org_phone = (payload.organizationPhone or "").strip() or None
    org_email = (payload.organizationEmail or "").strip().lower() or None
    if aff is None:
        org_name = None
        org_city = None
        org_phone = None
        org_email = None
    elif aff == "school" and payload.institutionId is not None:
        org_name = None
        org_city = None
    elif aff == "school":
        org_city = None
    registration_payload = {
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
        "affiliationType": aff,
        "organizationName": org_name,
        "organizationCity": org_city,
        "organizationPhone": org_phone,
        "organizationEmail": org_email,
        "idDocumentKind": id_kind,
        "otherIdType": other_id,
        "heardAbout": (payload.heardAbout or "").strip() or None,
    }

    if draft_to_finalize is not None:
        competitor = draft_to_finalize
        competitor.skill_id = skill_id
        competitor.zone_id = zone_id
        competitor.region_id = region_id
        competitor.institution_id = payload.institutionId
        competitor.ref_no = ref
        competitor.status = "PENDING_REVIEW"
        competitor.given_names = payload.givenNames
        competitor.family_name = payload.familyName
        competitor.gender = payload.gender
        competitor.date_of_birth = payload.dateOfBirth
        competitor.email = payload.email
        competitor.mobile = payload.mobile
        competitor.whatsapp = payload.whatsapp
        competitor.national_id = payload.nationalId
        competitor.id_document_kind = id_kind
        competitor.other_id_type = other_id
        competitor.affiliation_type = aff
        competitor.organization_name = org_name
        competitor.organization_city = org_city
        competitor.organization_phone = (payload.organizationPhone or "").strip() or None
        competitor.organization_email = (
            (payload.organizationEmail or "").strip().lower() or None
        )
        competitor.heard_about = (payload.heardAbout or "").strip() or None
        competitor.nationality = (payload.nationality or "").strip().upper() or None
        competitor.enrolment_attested = bool(payload.declarationAccepted)
        competitor.has_passport = bool(payload.hasPassport)
        competitor.passport_number = (
            (payload.passportNumber or "").strip() or None if payload.hasPassport else None
        )
        competitor.passport_expires_on = (
            payload.passportExpiresOn if payload.hasPassport else None
        )
        competitor.photo_key = photo_key
        competitor.coach = coach_data
        competitor.flags = flags
        competitor.public_profile_visible = False
        competitor.guardian_name = payload.guardianName
        competitor.guardian_email = payload.guardianEmail
        competitor.guardian_phone = payload.guardianPhone
        competitor.registration_payload = registration_payload
        competitor.updated_at = _now()
    else:
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
            id_document_kind=id_kind,
            other_id_type=other_id,
            affiliation_type=aff,
            organization_name=org_name,
            organization_city=org_city,
            organization_phone=(payload.organizationPhone or "").strip() or None,
            organization_email=(payload.organizationEmail or "").strip().lower() or None,
            heard_about=(payload.heardAbout or "").strip() or None,
            nationality=(payload.nationality or "").strip().upper() or None,
            enrolment_attested=bool(payload.declarationAccepted),
            has_passport=bool(payload.hasPassport),
            passport_number=(payload.passportNumber or "").strip() or None
            if payload.hasPassport
            else None,
            passport_expires_on=payload.passportExpiresOn if payload.hasPassport else None,
            photo_key=photo_key,
            coach=coach_data,
            flags=flags,
            public_profile_visible=False,
            guardian_name=payload.guardianName,
            guardian_email=payload.guardianEmail,
            guardian_phone=payload.guardianPhone,
            registration_payload=registration_payload,
            updated_at=_now(),
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

    # Guardian contacts are informational only — consent is not enforced on registration.

    message = None
    if "DUPLICATE_SUSPECTED" in (competitor.flags or []):
        message = "Registration received; identity check is pending admin review"

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
    await _best_effort_registration_sms(session, competitor, competition_id, ref)
    return out, 201


async def _best_effort_registration_sms(
    session: AsyncSession,
    competitor: Competitor,
    competition_id: uuid.UUID,
    competitor_ref: str,
) -> None:
    try:
        from app.services import competition_sms

        await competition_sms.notify_registration_received(
            session,
            competitor=competitor,
            competition_id=competition_id,
            competitor_ref=competitor_ref,
            trigger="registration_create",
            commit=True,
        )
    except Exception:
        logger.exception(
            "REGISTRATION_CONFIRMATION SMS failed competitor=%s",
            competitor.id,
        )


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
    {"name": "whatsapp", "type": "phone", "required": True},
    {
        "name": "idDocumentKind",
        "type": "enum",
        "required": False,
        "allowedValues": ["GHANA_CARD", "OTHER"],
    },
    {
        "name": "otherIdType",
        "type": "enum",
        "required": False,
        "allowedValues": ["Passport", "Driver's License", "Student ID"],
    },
    {"name": "nationalId", "type": "string", "required": False},
    {"name": "guardianName", "type": "string", "required": False, "maxLength": 200},
    {"name": "guardianPhone", "type": "phone", "required": False},
    {
        "name": "heardAbout",
        "type": "enum",
        "required": True,
        "allowedValues": list(_HEARD_ABOUT_VALUES),
    },
    {"name": "hasPassport", "type": "boolean", "required": True},
    {"name": "passportNumber", "type": "string", "required": False, "maxLength": 64},
    {"name": "passportExpiresOn", "type": "date", "required": False},
    {
        "name": "affiliationType",
        "type": "enum",
        "required": False,
        "allowedValues": ["school", "company", "workshop", "none"],
    },
    {"name": "organizationName", "type": "string", "required": False, "maxLength": 200},
    {"name": "organizationCity", "type": "string", "required": False, "maxLength": 120},
    {"name": "organizationPhone", "type": "phone", "required": False},
    {"name": "organizationEmail", "type": "email", "required": False},
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
