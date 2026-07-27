"""Geography HTTP API — regions catalog and cycle zones (US-ZON-01)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies.auth import AdminUserDep, CurrentUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import Region, Zone
from app.schemas.geography import (
    RegionOut,
    RegionZoneMapOut,
    RegionZoneMapPut,
    RegionZoneMappingItem,
    ZoneCreate,
    ZoneOut,
    ZonePatch,
)
from app.services import geography as geography_service

router = APIRouter(tags=["geography"])


def _region_out(region: Region) -> RegionOut:
    return RegionOut(regionId=region.id, name=region.name, active=region.active)


def _zone_out(zone: Zone) -> ZoneOut:
    return ZoneOut(zoneId=zone.id, name=zone.name, active=zone.active)


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(session: DBSessionDep, user: CurrentUserDep) -> list[RegionOut]:
    _ = user
    regions = await geography_service.list_regions(session)
    return [_region_out(r) for r in regions]


@router.get("/competitions/{competition_id}/zones", response_model=list[ZoneOut])
async def list_cycle_zones(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[ZoneOut]:
    _ = admin
    zones = await geography_service.list_cycle_zones(session, competition_id)
    return [_zone_out(z) for z in zones]


@router.post("/competitions/{competition_id}/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
async def create_competition_zone(
    competition_id: uuid.UUID,
    payload: ZoneCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ZoneOut:
    ip, ua = client_meta(request)
    zone = await geography_service.create_competition_zone(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _zone_out(zone)


@router.patch("/competitions/{competition_id}/zones/{zone_id}", response_model=ZoneOut)
async def patch_cycle_zone(
    competition_id: uuid.UUID,
    zone_id: uuid.UUID,
    payload: ZonePatch,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> ZoneOut:
    ip, ua = client_meta(request)
    zone = await geography_service.patch_cycle_zone(
        session, competition_id, zone_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _zone_out(zone)


@router.get("/competitions/{competition_id}/region-zone-map", response_model=RegionZoneMapOut)
async def get_region_zone_map(
    competition_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> RegionZoneMapOut:
    _ = admin
    rows = await geography_service.get_region_zone_map(session, competition_id)
    return RegionZoneMapOut(
        mappings=[
            RegionZoneMappingItem(regionId=r.region_id, zoneId=r.zone_id) for r in rows
        ]
    )


@router.put("/competitions/{competition_id}/region-zone-map", response_model=RegionZoneMapOut)
async def put_region_zone_map(
    competition_id: uuid.UUID,
    payload: RegionZoneMapPut,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> RegionZoneMapOut:
    ip, ua = client_meta(request)
    rows = await geography_service.put_region_zone_map(
        session, competition_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return RegionZoneMapOut(
        mappings=[
            RegionZoneMappingItem(regionId=r.region_id, zoneId=r.zone_id) for r in rows
        ]
    )
