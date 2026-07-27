"""Schemas for US-ZON-01 geography (regions, zones, region→zone map)."""

from uuid import UUID

from pydantic import BaseModel, Field


class RegionOut(BaseModel):
    regionId: UUID
    name: str
    active: bool


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ZonePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class ZoneOut(BaseModel):
    zoneId: UUID
    name: str
    active: bool


class RegionZoneMappingItem(BaseModel):
    regionId: UUID
    zoneId: UUID


class RegionZoneMapOut(BaseModel):
    mappings: list[RegionZoneMappingItem]


class RegionZoneMapPut(BaseModel):
    mappings: list[RegionZoneMappingItem] = Field(default_factory=list)
