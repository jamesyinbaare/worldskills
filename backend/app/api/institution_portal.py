"""Institution portal APIs — roster and nomination quotas."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.schemas.institution_portal import (
    InstitutionCompetitionOut,
    CompetitionSchoolQuotasOut,
    CompetitionSchoolQuotasUpsert,
    InstitutionCompetitionMembershipOut,
    InstitutionNominationLimitsOut,
    InstitutionNominationLimitsUpsert,
    InstitutionRegistrationOut,
    NominationQuotasOut,
)
from app.services import institution_portal as portal_service

router = APIRouter(tags=["institution-portal"])


@router.get(
    "/institutions/me/registrations",
    response_model=list[InstitutionRegistrationOut],
)
async def list_my_institution_registrations(
    session: DBSessionDep,
    user: CurrentUserDep,
) -> list[InstitutionRegistrationOut]:
    return await portal_service.list_institution_registrations(session, actor=user)


@router.get(
    "/institutions/me/competitions",
    response_model=list[InstitutionCompetitionOut],
)
async def list_my_institution_competitions(
    session: DBSessionDep,
    user: CurrentUserDep,
) -> list[InstitutionCompetitionOut]:
    return await portal_service.list_institution_competitions(session, actor=user)


@router.get(
    "/competitions/{competition_id}/nomination-quotas",
    response_model=NominationQuotasOut,
)
async def get_nomination_quotas(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    user: CurrentUserDep,
) -> NominationQuotasOut:
    return await portal_service.get_nomination_quotas(
        session, competition_id, actor=user
    )


@router.get(
    "/admin/competitions/{competition_id}/school-quotas",
    response_model=CompetitionSchoolQuotasOut,
)
async def get_competition_school_quotas(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> CompetitionSchoolQuotasOut:
    return await portal_service.get_competition_school_quotas(
        session, competition_id
    )


@router.put(
    "/admin/competitions/{competition_id}/school-quotas",
    response_model=CompetitionSchoolQuotasOut,
)
async def upsert_competition_school_quotas(
    competition_id: uuid.UUID,
    payload: CompetitionSchoolQuotasUpsert,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> CompetitionSchoolQuotasOut:
    ip, ua = client_meta(request)
    return await portal_service.upsert_competition_school_quotas(
        session,
        competition_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )


@router.get(
    "/admin/competitions/{competition_id}/institution-memberships",
    response_model=list[InstitutionCompetitionMembershipOut],
)
async def list_institution_memberships(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[InstitutionCompetitionMembershipOut]:
    return await portal_service.list_competition_institution_memberships(
        session, competition_id
    )


@router.get(
    "/admin/competitions/{competition_id}/institutions/{institution_id}/nomination-limits",
    response_model=InstitutionNominationLimitsOut,
)
async def get_admin_nomination_limits(
    competition_id: uuid.UUID,
    institution_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> InstitutionNominationLimitsOut:
    return await portal_service.get_admin_institution_nomination_limits(
        session, competition_id, institution_id
    )


@router.put(
    "/admin/competitions/{competition_id}/institutions/{institution_id}/nomination-limits",
    response_model=InstitutionNominationLimitsOut,
)
async def upsert_nomination_limits(
    competition_id: uuid.UUID,
    institution_id: uuid.UUID,
    payload: InstitutionNominationLimitsUpsert,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> InstitutionNominationLimitsOut:
    ip, ua = client_meta(request)
    return await portal_service.upsert_institution_nomination_limits(
        session,
        competition_id,
        institution_id,
        payload,
        actor=admin,
        ip=ip,
        user_agent=ua,
    )
