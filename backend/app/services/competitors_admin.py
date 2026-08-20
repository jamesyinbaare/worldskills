"""Admin competitor roster listing."""

from __future__ import annotations

import io
import re
import uuid
from datetime import date, datetime

from fastapi import status
from openpyxl import Workbook
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import Competition, Competitor, Institution, Region, Skill, User, Zone
from app.schemas.competitors_admin import AdminCompetitorItem


def _require_admin_list(actor: User) -> None:
    if is_admin_role(actor.role) or has_capability(actor.role, Capability.CONFIGURE_CYCLE):
        return
    raise AppError(
        "FORBIDDEN",
        "Admin role required to list competitors",
        status_code=status.HTTP_403_FORBIDDEN,
        fields=[FieldError("role", "FORBIDDEN")],
    )


async def list_admin_competitors(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    skill_id: uuid.UUID | None = None,
    q: str | None = None,
    status_filter: str | None = None,
) -> list[AdminCompetitorItem]:
    _require_admin_list(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    stmt = (
        select(Competitor, Skill, Institution, Zone)
        .join(Skill, Skill.id == Competitor.skill_id)
        .outerjoin(Institution, Institution.id == Competitor.institution_id)
        .outerjoin(Zone, Zone.id == Competitor.zone_id)
        .where(Competitor.competition_id == competition_id)
    )
    if skill_id is not None:
        stmt = stmt.where(Competitor.skill_id == skill_id)
    if status_filter and status_filter.strip():
        stmt = stmt.where(Competitor.status == status_filter.strip().upper())
    else:
        # Incomplete draft applications are not part of the admin roster.
        stmt = stmt.where(Competitor.status != "DRAFT")
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Competitor.ref_no.ilike(term),
                Competitor.given_names.ilike(term),
                Competitor.family_name.ilike(term),
                Skill.name.ilike(term),
                Institution.name.ilike(term),
            )
        )
    stmt = stmt.order_by(
        Skill.name.asc(),
        Competitor.family_name.asc().nullslast(),
        Competitor.given_names.asc().nullslast(),
        Competitor.ref_no.asc(),
    )
    rows = (await session.execute(stmt)).all()
    return [
        AdminCompetitorItem(
            competitorId=comp.id,
            refNo=comp.ref_no,
            givenNames=comp.given_names,
            familyName=comp.family_name,
            skillId=skill.id,
            skillName=skill.name,
            institutionId=inst.id if inst else None,
            institutionName=inst.name if inst else None,
            status=comp.status,
            eligibilityStatus=comp.eligibility_status,
            zoneId=zone.id if zone else None,
            zoneName=zone.name if zone else None,
            consentFormUploadedAt=comp.consent_form_uploaded_at,
            consentVerificationStatus=comp.consent_verification_status,
            hasMobile=bool((comp.mobile or comp.whatsapp or "").strip()),
            hasCoachPhone=_coach_has_phone(comp.coach),
        )
        for comp, skill, inst, zone in rows
    ]


def _coach_has_phone(coach: object) -> bool:
    if not isinstance(coach, dict):
        return False
    return bool(str(coach.get("contactNumber") or coach.get("whatsapp") or "").strip())


def _coach_name(coach: object) -> str:
    if not isinstance(coach, dict):
        return ""
    first = str(coach.get("firstName") or "").strip()
    surname = str(coach.get("surname") or "").strip()
    return " ".join(p for p in (first, surname) if p)


def _coach_field(coach: object, *keys: str) -> str:
    if not isinstance(coach, dict):
        return ""
    for key in keys:
        value = str(coach.get(key) or "").strip()
        if value:
            return value
    return ""


def _cell(value: object) -> str | int | float | date | datetime | None:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value
    return str(value)


def _slug_filename_part(value: str | None, fallback: str = "competitors") -> str:
    raw = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return (slug[:48] or fallback)


async def export_admin_competitors_xlsx(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    skill_id: uuid.UUID | None = None,
    q: str | None = None,
    status_filter: str | None = None,
) -> tuple[bytes, str]:
    """Build an Excel workbook of the admin competitor roster (same filters as list)."""
    _require_admin_list(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    skill_label: str | None = None
    if skill_id is not None:
        skill = await session.get(Skill, skill_id)
        if skill is None or skill.competition_id != competition_id:
            raise AppError("SKILL_NOT_FOUND", "Skill not found", status_code=404)
        skill_label = skill.name

    stmt = (
        select(Competitor, Skill, Institution, Zone, Region)
        .join(Skill, Skill.id == Competitor.skill_id)
        .outerjoin(Institution, Institution.id == Competitor.institution_id)
        .outerjoin(Zone, Zone.id == Competitor.zone_id)
        .outerjoin(Region, Region.id == Competitor.region_id)
        .where(Competitor.competition_id == competition_id)
    )
    if skill_id is not None:
        stmt = stmt.where(Competitor.skill_id == skill_id)
    if status_filter and status_filter.strip():
        stmt = stmt.where(Competitor.status == status_filter.strip().upper())
    else:
        stmt = stmt.where(Competitor.status != "DRAFT")
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Competitor.ref_no.ilike(term),
                Competitor.given_names.ilike(term),
                Competitor.family_name.ilike(term),
                Skill.name.ilike(term),
                Institution.name.ilike(term),
                Region.name.ilike(term),
            )
        )
    stmt = stmt.order_by(
        Skill.name.asc(),
        Competitor.family_name.asc().nullslast(),
        Competitor.given_names.asc().nullslast(),
        Competitor.ref_no.asc(),
    )
    rows = (await session.execute(stmt)).all()

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Competitors"
    headers = [
        "Ref No",
        "Given names",
        "Family name",
        "Gender",
        "Date of birth",
        "Email",
        "Mobile",
        "WhatsApp",
        "Skill",
        "Region",
        "Zone",
        "Institution",
        "Status",
        "Eligibility",
        "Consent verification",
        "Coach name",
        "Coach email",
        "Coach contact",
        "Coach WhatsApp",
    ]
    ws.append(headers)
    for comp, skill, inst, zone, region in rows:
        coach = comp.coach if isinstance(comp.coach, dict) else None
        ws.append(
            [
                _cell(comp.ref_no),
                _cell(comp.given_names),
                _cell(comp.family_name),
                _cell(comp.gender),
                _cell(comp.date_of_birth),
                _cell(comp.email),
                _cell(comp.mobile),
                _cell(comp.whatsapp),
                _cell(skill.name),
                _cell(region.name if region else None),
                _cell(zone.name if zone else None),
                _cell(inst.name if inst else None),
                _cell(comp.status),
                _cell(comp.eligibility_status),
                _cell(comp.consent_verification_status),
                _coach_name(coach),
                _coach_field(coach, "email"),
                _coach_field(coach, "contactNumber"),
                _coach_field(coach, "whatsapp"),
            ]
        )

    for col in ws.columns:
        max_len = 0
        letter = col[0].column_letter
        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        ws.column_dimensions[letter].width = min(max(12, max_len + 2), 40)

    buf = io.BytesIO()
    wb.save(buf)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    label = _slug_filename_part(skill_label or cycle.name, "competitors")
    filename = f"competitors-{label}-{stamp}.xlsx"
    return buf.getvalue(), filename
