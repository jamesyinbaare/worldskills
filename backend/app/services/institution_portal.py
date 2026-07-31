"""Institution portal — school roster and per-skill nomination quotas."""

from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import (
    Competition,
    CompetitionStatus,
    Competitor,
    Institution,
    InstitutionCompetitionMembership,
    NominationLimit,
    RegistrationWindow,
    Skill,
    User,
    UserRole,
    Zone,
)
from app.schemas.institution_portal import (
    InstitutionCompetitionOut,
    CompetitionSchoolQuotasOut,
    CompetitionSchoolQuotasUpsert,
    InstitutionCompetitionMembershipOut,
    InstitutionNominationLimitsOut,
    InstitutionNominationLimitsUpsert,
    InstitutionRegistrationOut,
    NominationQuotaOut,
    NominationQuotasOut,
)
from app.services.audit import write_audit_event

_QUOTA_EXCLUDED_STATUSES = frozenset({"REJECTED", "WITHDRAWN", "DRAFT"})


def _require_institution_actor(actor: User) -> uuid.UUID:
    if actor.role != UserRole.INSTITUTION or actor.institution_id is None:
        raise AppError(
            "FORBIDDEN",
            "Institution account required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return actor.institution_id


async def _count_used(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    institution_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> int:
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
    return int(used)


async def list_institution_registrations(
    session: AsyncSession, *, actor: User
) -> list[InstitutionRegistrationOut]:
    institution_id = _require_institution_actor(actor)
    competitors = (
        await session.execute(
            select(Competitor).where(Competitor.institution_id == institution_id)
        )
    ).scalars().all()

    out: list[InstitutionRegistrationOut] = []
    for comp in competitors:
        if comp.status == "DRAFT":
            continue
        competition = await session.get(Competition, comp.competition_id)
        skill = await session.get(Skill, comp.skill_id)
        if competition is None or skill is None:
            continue
        out.append(
            InstitutionRegistrationOut(
                competitorId=comp.id,
                competitorRef=comp.ref_no,
                competitionId=competition.id,
                competitionName=competition.name,
                competitionStatus=competition.status.value,
                skillId=skill.id,
                skillName=skill.name,
                status=comp.status,
                givenNames=comp.given_names,
                familyName=comp.family_name,
                gender=comp.gender,
            )
        )
    out.sort(
        key=lambda r: (
            r.competitionName.lower(),
            r.skillName.lower(),
            (r.familyName or "").lower(),
            (r.givenNames or "").lower(),
        )
    )
    return out


async def list_institution_competitions(
    session: AsyncSession, *, actor: User
) -> list[InstitutionCompetitionOut]:
    _require_institution_actor(actor)

    rows = (
        await session.execute(
            select(Competition, RegistrationWindow)
            .outerjoin(
                RegistrationWindow,
                RegistrationWindow.competition_id == Competition.id,
            )
            .where(Competition.status != CompetitionStatus.DRAFT)
            .order_by(Competition.period_start.desc(), Competition.name.asc())
        )
    ).all()

    out: list[InstitutionCompetitionOut] = []
    for competition, window in rows:
        out.append(
            InstitutionCompetitionOut(
                competitionId=competition.id,
                name=competition.name,
                status=competition.status.value,
                period={
                    "start": competition.period_start.isoformat(),
                    "end": competition.period_end.isoformat(),
                },
                description=competition.description,
                window=(
                    {
                        "opensAt": window.opens_at.isoformat(),
                        "closesAt": window.closes_at.isoformat(),
                    }
                    if window is not None
                    else None
                ),
            )
        )
    return out


async def get_nomination_quotas(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> NominationQuotasOut:
    if actor.role != UserRole.INSTITUTION or actor.institution_id is None:
        raise AppError(
            "FORBIDDEN",
            "Institution account required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    institution_id = actor.institution_id

    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    quotas = await _build_skill_quotas(
        session,
        competition_id=competition_id,
        institution_id=institution_id,
    )
    return NominationQuotasOut(
        competitionId=competition_id,
        institutionId=institution_id,
        quotas=quotas,
    )


async def _build_skill_quotas(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    institution_id: uuid.UUID | None = None,
) -> list[NominationQuotaOut]:
    skills = (
        await session.execute(
            select(Skill)
            .where(Skill.competition_id == competition_id, Skill.active.is_(True))
            .order_by(Skill.name.asc())
        )
    ).scalars().all()

    quotas: list[NominationQuotaOut] = []
    for skill in skills:
        used = 0
        if institution_id is not None:
            used = await _count_used(
                session,
                competition_id=competition_id,
                institution_id=institution_id,
                skill_id=skill.id,
            )
        if skill.school_quota is None:
            quotas.append(
                NominationQuotaOut(
                    skillId=skill.id,
                    skillName=skill.name,
                    max=0,
                    used=used,
                    remaining=0,
                    configured=False,
                )
            )
            continue
        max_n = int(skill.school_quota)
        quotas.append(
            NominationQuotaOut(
                skillId=skill.id,
                skillName=skill.name,
                max=max_n,
                used=used,
                remaining=max(0, max_n - used),
                configured=True,
            )
        )
    return quotas


async def get_competition_school_quotas(
    session: AsyncSession,
    competition_id: uuid.UUID,
) -> CompetitionSchoolQuotasOut:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    quotas = await _build_skill_quotas(session, competition_id=competition_id)
    return CompetitionSchoolQuotasOut(competitionId=competition_id, quotas=quotas)


async def upsert_competition_school_quotas(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: CompetitionSchoolQuotasUpsert,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> CompetitionSchoolQuotasOut:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    for item in payload.limits:
        skill = await session.get(Skill, item.skillId)
        if skill is None or skill.competition_id != competition_id:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid skill for competition",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("skillId", "INVALID")],
            )
        skill.school_quota = item.maxNominations

    await session.flush()
    await write_audit_event(
        session,
        action="COMPETITION_SCHOOL_QUOTAS_UPSERT",
        entity_type="Competition",
        entity_id=str(competition_id),
        actor_id=actor.id,
        actor_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
        competition_id=competition_id,
        after={
            "limits": [
                {"skillId": str(i.skillId), "maxNominations": i.maxNominations}
                for i in payload.limits
            ],
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return await get_competition_school_quotas(session, competition_id)


async def get_admin_institution_nomination_limits(
    session: AsyncSession,
    competition_id: uuid.UUID,
    institution_id: uuid.UUID,
) -> InstitutionNominationLimitsOut:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    institution = await session.get(Institution, institution_id)
    if institution is None:
        raise AppError(
            "INSTITUTION_NOT_FOUND",
            "Institution not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    membership = (
        await session.execute(
            select(InstitutionCompetitionMembership).where(
                InstitutionCompetitionMembership.competition_id == competition_id,
                InstitutionCompetitionMembership.institution_id == institution_id,
            )
        )
    ).scalar_one_or_none()

    quotas = await _build_skill_quotas(
        session,
        competition_id=competition_id,
        institution_id=institution_id,
    )
    return InstitutionNominationLimitsOut(
        competitionId=competition_id,
        institutionId=institution_id,
        zoneId=membership.zone_id if membership else None,
        limits=quotas,
    )


async def list_competition_institution_memberships(
    session: AsyncSession,
    competition_id: uuid.UUID,
) -> list[InstitutionCompetitionMembershipOut]:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    rows = (
        await session.execute(
            select(InstitutionCompetitionMembership, Institution, Zone)
            .join(
                Institution,
                Institution.id == InstitutionCompetitionMembership.institution_id,
            )
            .join(Zone, Zone.id == InstitutionCompetitionMembership.zone_id)
            .where(InstitutionCompetitionMembership.competition_id == competition_id)
            .order_by(Institution.name.asc())
        )
    ).all()

    out: list[InstitutionCompetitionMembershipOut] = []
    for membership, institution, zone in rows:
        configured = (
            await session.execute(
                select(func.count())
                .select_from(Skill)
                .where(
                    Skill.competition_id == competition_id,
                    Skill.active.is_(True),
                    Skill.school_quota.is_not(None),
                )
            )
        ).scalar_one()
        out.append(
            InstitutionCompetitionMembershipOut(
                institutionId=institution.id,
                institutionName=institution.name,
                institutionCode=institution.code,
                zoneId=zone.id,
                zoneName=zone.name,
                configuredSkillCount=int(configured),
            )
        )
    return out


async def upsert_institution_nomination_limits(
    session: AsyncSession,
    competition_id: uuid.UUID,
    institution_id: uuid.UUID,
    payload: InstitutionNominationLimitsUpsert,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> InstitutionNominationLimitsOut:
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    zone = await session.get(Zone, payload.zoneId)
    if zone is None or zone.competition_id != competition_id:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid zone for competition",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("zoneId", "INVALID")],
        )

    membership = (
        await session.execute(
            select(InstitutionCompetitionMembership).where(
                InstitutionCompetitionMembership.competition_id == competition_id,
                InstitutionCompetitionMembership.institution_id == institution_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = InstitutionCompetitionMembership(
            competition_id=competition_id,
            institution_id=institution_id,
            zone_id=payload.zoneId,
        )
        session.add(membership)
    else:
        membership.zone_id = payload.zoneId

    existing = (
        await session.execute(
            select(NominationLimit).where(
                NominationLimit.competition_id == competition_id,
                NominationLimit.institution_id == institution_id,
            )
        )
    ).scalars().all()
    by_skill = {row.skill_id: row for row in existing}

    for item in payload.limits:
        skill = await session.get(Skill, item.skillId)
        if skill is None or skill.competition_id != competition_id:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid skill for competition",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("skillId", "INVALID")],
            )
        # Global per-skill school quota (applies to every institution)
        skill.school_quota = item.maxNominations
        row = by_skill.get(item.skillId)
        if row is None:
            session.add(
                NominationLimit(
                    competition_id=competition_id,
                    institution_id=institution_id,
                    skill_id=item.skillId,
                    max_nominations=item.maxNominations,
                )
            )
        else:
            row.max_nominations = item.maxNominations

    await session.flush()

    await write_audit_event(
        session,
        action="INSTITUTION_NOMINATION_LIMITS_UPSERT",
        entity_type="Institution",
        entity_id=str(institution_id),
        actor_id=actor.id,
        actor_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
        competition_id=competition_id,
        after={
            "zoneId": str(payload.zoneId),
            "limits": [
                {"skillId": str(i.skillId), "maxNominations": i.maxNominations}
                for i in payload.limits
            ],
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    quotas = await _build_skill_quotas(
        session,
        competition_id=competition_id,
        institution_id=institution_id,
    )
    return InstitutionNominationLimitsOut(
        competitionId=competition_id,
        institutionId=institution_id,
        zoneId=payload.zoneId,
        limits=quotas,
    )
