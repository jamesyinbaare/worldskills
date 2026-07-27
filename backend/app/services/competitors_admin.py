"""Admin competitor roster listing."""

from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability, is_admin_role
from app.models import Competition, Competitor, Institution, Skill, User, Zone
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
        )
        for comp, skill, inst, zone in rows
    ]
