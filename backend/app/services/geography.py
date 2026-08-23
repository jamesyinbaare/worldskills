"""Regions catalog, cycle zones, and region→zone resolution (US-ZON-01)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Competition, CompetitionRegionZone, Institution, Region, User, Zone
from app.schemas.geography import RegionZoneMapPut, ZoneCreate, ZonePatch
from app.services.audit import write_audit_event


def region_to_dict(region: Region) -> dict[str, Any]:
    return {"regionId": str(region.id), "name": region.name, "active": region.active}


def zone_to_dict(zone: Zone) -> dict[str, Any]:
    return {"zoneId": str(zone.id), "name": zone.name, "active": zone.active}


async def list_regions(session: AsyncSession, *, active_only: bool = False) -> list[Region]:
    stmt = select(Region).order_by(Region.name)
    if active_only:
        stmt = stmt.where(Region.active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_cycle_zones(session: AsyncSession, competition_id: uuid.UUID) -> list[Zone]:
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    result = await session.execute(
        select(Zone).where(Zone.competition_id == competition_id).order_by(Zone.name.asc())
    )
    return list(result.scalars().all())


async def create_competition_zone(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: ZoneCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Zone:
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)

    name = payload.name.strip()
    if not name:
        raise AppError(
            "VALIDATION_ERROR",
            "Zone name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("name", "REQUIRED")],
        )

    dup = await session.execute(
        select(Zone).where(Zone.competition_id == competition_id, func.lower(Zone.name) == name.lower())
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "DUPLICATE",
            "A zone with this name already exists in the competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    zone = Zone(competition_id=competition_id, name=name, active=True)
    session.add(zone)
    await session.flush()
    await write_audit_event(
        session,
        action="ZONE_CREATE",
        entity_type="Zone",
        entity_id=str(zone.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=zone_to_dict(zone),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(zone)
    return zone


async def patch_cycle_zone(
    session: AsyncSession,
    competition_id: uuid.UUID,
    zone_id: uuid.UUID,
    payload: ZonePatch,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Zone:
    zone = await session.get(Zone, zone_id)
    if zone is None or zone.competition_id != competition_id:
        raise AppError("ZONE_NOT_FOUND", "Zone not found in cycle", status_code=status.HTTP_404_NOT_FOUND)

    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)

    before = zone_to_dict(zone)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise AppError(
                "VALIDATION_ERROR",
                "Zone name is required",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("name", "REQUIRED")],
            )
        dup = await session.execute(
            select(Zone).where(
                Zone.competition_id == competition_id,
                func.lower(Zone.name) == name.lower(),
                Zone.id != zone_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise AppError(
                "DUPLICATE",
                "A zone with this name already exists in the competition",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("name", "DUPLICATE")],
            )
        zone.name = name
    if payload.active is not None:
        zone.active = payload.active

    await session.flush()
    await write_audit_event(
        session,
        action="ZONE_UPDATE",
        entity_type="Zone",
        entity_id=str(zone.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=zone_to_dict(zone),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(zone)
    return zone


async def get_region_zone_map(session: AsyncSession, competition_id: uuid.UUID) -> list[CompetitionRegionZone]:
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    result = await session.execute(
        select(CompetitionRegionZone).where(CompetitionRegionZone.competition_id == competition_id)
    )
    return list(result.scalars().all())


async def put_region_zone_map(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: RegionZoneMapPut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> list[CompetitionRegionZone]:
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)

    seen_regions: set[uuid.UUID] = set()
    for item in payload.mappings:
        if item.regionId in seen_regions:
            raise AppError(
                "DUPLICATE",
                "Each region may appear only once in the map",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("mappings", "DUPLICATE")],
            )
        seen_regions.add(item.regionId)

        region = await session.get(Region, item.regionId)
        if region is None or not region.active:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid region",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("regionId", "INVALID")],
            )
        zone = await session.get(Zone, item.zoneId)
        if zone is None or zone.competition_id != competition_id:
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Zone must belong to this competition",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("zoneId", "CONFIG_INCOMPLETE")],
            )

    before_rows = await get_region_zone_map(session, competition_id)
    before = [
        {"regionId": str(r.region_id), "zoneId": str(r.zone_id)} for r in before_rows
    ]

    for old in before_rows:
        await session.delete(old)
    await session.flush()

    created: list[CompetitionRegionZone] = []
    for item in payload.mappings:
        row = CompetitionRegionZone(competition_id=competition_id, region_id=item.regionId, zone_id=item.zoneId)
        session.add(row)
        created.append(row)
    await session.flush()

    after = [{"regionId": str(r.region_id), "zoneId": str(r.zone_id)} for r in created]
    await write_audit_event(
        session,
        action="REGION_ZONE_MAP_UPDATE",
        entity_type="Competition",
        entity_id=str(competition_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before={"mappings": before},
        after={"mappings": after},
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    return created


async def resolve_zone_for_registration(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    region_id: uuid.UUID | None = None,
    institution_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve regionId and derived zoneId for registration/nomination."""
    resolved_region: uuid.UUID | None = region_id
    institution: Institution | None = None

    if institution_id is not None:
        institution = await session.get(Institution, institution_id)
        if institution is None or not institution.active:
            raise AppError(
                "VALIDATION_ERROR",
                "Invalid institution",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("institutionId", "REQUIRED")],
            )

    if resolved_region is None and institution is not None:
        resolved_region = institution.region_id

    if resolved_region is None:
        raise AppError(
            "REGION_REQUIRED",
            "A region is required to derive the competitor zone",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("regionId", "REGION_REQUIRED")],
        )

    region = await session.get(Region, resolved_region)
    if region is None or not region.active:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid region",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("regionId", "INVALID")],
        )

    mapping = (
        await session.execute(
            select(CompetitionRegionZone).where(
                CompetitionRegionZone.competition_id == competition_id,
                CompetitionRegionZone.region_id == resolved_region,
            )
        )
    ).scalar_one_or_none()
    if mapping is None:
        mapping = await _ensure_region_zone_mapping(
            session, competition_id=competition_id, region_id=resolved_region
        )

    zone = await session.get(Zone, mapping.zone_id)
    if zone is None or zone.competition_id != competition_id or not zone.active:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Mapped zone is invalid or inactive",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("regionId", "CONFIG_INCOMPLETE")],
        )

    return resolved_region, zone.id


async def _ensure_region_zone_mapping(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    region_id: uuid.UUID,
) -> CompetitionRegionZone:
    """If geography was never set up (no zones), create a National zone and map this region.

    When zones already exist, unmapped regions must be configured explicitly by an admin.
    """
    zones = list(
        (
            await session.execute(
                select(Zone).where(Zone.competition_id == competition_id, Zone.active.is_(True)).order_by(Zone.name)
            )
        ).scalars().all()
    )

    if zones:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "This school’s region is not mapped to a zone for this competition. "
            "Ask an admin to finish geography setup, or choose another school/region.",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("regionId", "CONFIG_INCOMPLETE")],
        )

    zone = Zone(competition_id=competition_id, name="National", active=True)
    session.add(zone)
    await session.flush()

    mapping = CompetitionRegionZone(
        competition_id=competition_id,
        region_id=region_id,
        zone_id=zone.id,
    )
    session.add(mapping)
    await session.flush()
    return mapping
