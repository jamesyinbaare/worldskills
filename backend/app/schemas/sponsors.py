"""Sponsor catalog schemas."""

from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _normalize_optional_text(v: str | None) -> str | None:
    if v is None:
        return None
    stripped = v.strip()
    return stripped or None


def _normalize_website(v: str | None) -> str | None:
    normalized = _normalize_optional_text(v)
    if normalized is None:
        return None
    candidate = normalized if "://" in normalized else f"https://{normalized}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").strip()
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or " " in host
        or "." not in host
    ):
        raise ValueError("INVALID_URL")
    return candidate


class SponsorSkillAreaOut(BaseModel):
    catalogSkillId: UUID
    name: str
    number: str | None = None


class SponsorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    website: str | None = Field(default=None, max_length=512)
    catalogSkillIds: list[UUID] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("description")
    @classmethod
    def description_normalize(cls, v: str | None) -> str | None:
        return _normalize_optional_text(v)

    @field_validator("website")
    @classmethod
    def website_normalize(cls, v: str | None) -> str | None:
        return _normalize_website(v)

    @field_validator("catalogSkillIds")
    @classmethod
    def catalog_skill_ids_unique(cls, v: list[UUID]) -> list[UUID]:
        # Preserve order, drop duplicates
        seen: set[UUID] = set()
        out: list[UUID] = []
        for skill_id in v:
            if skill_id not in seen:
                seen.add(skill_id)
                out.append(skill_id)
        return out


class SponsorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    website: str | None = Field(default=None, max_length=512)
    active: bool | None = None
    catalogSkillIds: list[UUID] | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("description")
    @classmethod
    def description_normalize(cls, v: str | None) -> str | None:
        return _normalize_optional_text(v)

    @field_validator("website")
    @classmethod
    def website_normalize(cls, v: str | None) -> str | None:
        return _normalize_website(v)

    @field_validator("catalogSkillIds")
    @classmethod
    def catalog_skill_ids_unique(cls, v: list[UUID] | None) -> list[UUID] | None:
        if v is None:
            return v
        seen: set[UUID] = set()
        out: list[UUID] = []
        for skill_id in v:
            if skill_id not in seen:
                seen.add(skill_id)
                out.append(skill_id)
        return out


class SponsorOut(BaseModel):
    sponsorId: UUID
    name: str
    description: str | None = None
    website: str | None = None
    hasLogo: bool = False
    logoFileName: str | None = None
    active: bool
    skillAreas: list[SponsorSkillAreaOut] = Field(default_factory=list)
