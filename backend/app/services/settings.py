"""Singleton system settings service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSettings, User
from app.schemas.settings import SystemSettingsOut, SystemSettingsUpdate
from app.services.audit import write_audit_event


async def get_or_create_settings(session: AsyncSession) -> SystemSettings:
    row = (
        await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = SystemSettings(
        id=1,
        institution_registration_enabled=False,
        allow_multiple_active_competitions=True,
    )
    session.add(row)
    await session.flush()
    return row


async def get_settings_out(session: AsyncSession) -> SystemSettingsOut:
    row = await get_or_create_settings(session)
    return SystemSettingsOut(
        institutionRegistrationEnabled=row.institution_registration_enabled,
        allowMultipleActiveCompetitions=row.allow_multiple_active_competitions,
    )


async def update_settings(
    session: AsyncSession,
    payload: SystemSettingsUpdate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> SystemSettingsOut:
    row = await get_or_create_settings(session)
    before = {
        "institutionRegistrationEnabled": row.institution_registration_enabled,
        "allowMultipleActiveCompetitions": row.allow_multiple_active_competitions,
    }
    if payload.institutionRegistrationEnabled is not None:
        row.institution_registration_enabled = payload.institutionRegistrationEnabled
    if payload.allowMultipleActiveCompetitions is not None:
        row.allow_multiple_active_competitions = payload.allowMultipleActiveCompetitions
    row.updated_at = datetime.utcnow()
    await session.flush()
    after = {
        "institutionRegistrationEnabled": row.institution_registration_enabled,
        "allowMultipleActiveCompetitions": row.allow_multiple_active_competitions,
    }
    await write_audit_event(
        session,
        action="SYSTEM_SETTINGS_UPDATE",
        entity_type="SystemSettings",
        entity_id="1",
        actor_id=actor.id,
        actor_role=actor.role.value,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
    )
    return SystemSettingsOut(
        institutionRegistrationEnabled=row.institution_registration_enabled,
        allowMultipleActiveCompetitions=row.allow_multiple_active_competitions,
    )


async def institution_registration_enabled(session: AsyncSession) -> bool:
    row = await get_or_create_settings(session)
    return bool(row.institution_registration_enabled)


async def allow_multiple_active_competitions(session: AsyncSession) -> bool:
    row = await get_or_create_settings(session)
    return bool(row.allow_multiple_active_competitions)
