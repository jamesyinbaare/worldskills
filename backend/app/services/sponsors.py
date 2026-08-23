"""Global sponsor catalog services."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import CatalogSkill, Sponsor, User, sponsor_catalog_skills
from app.schemas.sponsors import SponsorCreate, SponsorPatch
from app.services.audit import write_audit_event

_LOGO_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

_SPONSOR_LOAD = selectinload(Sponsor.catalog_skills)


def _skill_areas_out(sponsor: Sponsor) -> list[dict[str, Any]]:
    skills = list(sponsor.__dict__.get("catalog_skills") or [])
    skills.sort(key=lambda s: (s.name or "").lower())
    return [
        {
            "catalogSkillId": skill.id,
            "name": skill.name,
            "number": skill.number,
        }
        for skill in skills
    ]


def sponsor_to_dict(sponsor: Sponsor) -> dict[str, Any]:
    return {
        "sponsorId": str(sponsor.id),
        "name": sponsor.name,
        "description": sponsor.description,
        "website": sponsor.website,
        "hasLogo": bool(sponsor.logo_object_key),
        "logoFileName": sponsor.logo_file_name,
        "active": sponsor.active,
        "catalogSkillIds": [str(s.id) for s in (sponsor.__dict__.get("catalog_skills") or [])],
    }


def sponsor_out_kwargs(sponsor: Sponsor) -> dict[str, Any]:
    return {
        "sponsorId": sponsor.id,
        "name": sponsor.name,
        "description": sponsor.description,
        "website": sponsor.website,
        "hasLogo": bool(sponsor.logo_object_key),
        "logoFileName": sponsor.logo_file_name,
        "active": sponsor.active,
        "skillAreas": _skill_areas_out(sponsor),
    }


def _assert_logo_mime(content_type: str | None, filename: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    lower = filename.lower()
    if ct in _LOGO_MIME:
        return ct
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    raise AppError(
        "FILE_TYPE",
        "Only JPEG, PNG, or WebP logos are allowed",
        status_code=status.HTTP_400_BAD_REQUEST,
        fields=[FieldError("file", "FILE_TYPE")],
    )


async def _load_sponsor(session: AsyncSession, sponsor_id: uuid.UUID) -> Sponsor | None:
    result = await session.execute(
        select(Sponsor).options(_SPONSOR_LOAD).where(Sponsor.id == sponsor_id)
    )
    return result.scalar_one_or_none()


async def _resolve_active_catalog_skills(
    session: AsyncSession,
    catalog_skill_ids: list[uuid.UUID],
) -> list[CatalogSkill]:
    if not catalog_skill_ids:
        return []
    result = await session.execute(
        select(CatalogSkill).where(
            CatalogSkill.id.in_(catalog_skill_ids),
            CatalogSkill.active.is_(True),
        )
    )
    found = {skill.id: skill for skill in result.scalars().all()}
    missing = [skill_id for skill_id in catalog_skill_ids if skill_id not in found]
    if missing:
        raise AppError(
            "CATALOG_SKILL_INVALID",
            "One or more catalog skill areas are invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("catalogSkillIds", "INVALID")],
        )
    # Preserve request order
    return [found[skill_id] for skill_id in catalog_skill_ids]


async def list_sponsors(session: AsyncSession) -> list[Sponsor]:
    result = await session.execute(
        select(Sponsor).options(_SPONSOR_LOAD).order_by(Sponsor.name)
    )
    return list(result.scalars().all())


async def list_active_sponsors(session: AsyncSession) -> list[Sponsor]:
    result = await session.execute(
        select(Sponsor)
        .options(_SPONSOR_LOAD)
        .where(Sponsor.active.is_(True))
        .order_by(Sponsor.name)
    )
    return list(result.scalars().all())


async def active_sponsors_by_catalog_skill_ids(
    session: AsyncSession,
    catalog_skill_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[Sponsor]]:
    """Map catalog skill id → active sponsors linked to that skill (name-sorted)."""
    unique_ids = list({skill_id for skill_id in catalog_skill_ids if skill_id is not None})
    if not unique_ids:
        return {}

    result = await session.execute(
        select(Sponsor, sponsor_catalog_skills.c.catalog_skill_id)
        .join(
            sponsor_catalog_skills,
            sponsor_catalog_skills.c.sponsor_id == Sponsor.id,
        )
        .options(_SPONSOR_LOAD)
        .where(
            Sponsor.active.is_(True),
            sponsor_catalog_skills.c.catalog_skill_id.in_(unique_ids),
        )
        .order_by(Sponsor.name)
    )

    out: dict[uuid.UUID, list[Sponsor]] = defaultdict(list)
    seen: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for sponsor, catalog_skill_id in result.all():
        if sponsor.id in seen[catalog_skill_id]:
            continue
        seen[catalog_skill_id].add(sponsor.id)
        out[catalog_skill_id].append(sponsor)
    return dict(out)


async def create_sponsor(
    session: AsyncSession,
    payload: SponsorCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Sponsor:
    dup = await session.execute(
        select(Sponsor).where(func.lower(Sponsor.name) == payload.name.lower())
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "SPONSOR_DUPLICATE",
            "A sponsor with this name already exists",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    skills = await _resolve_active_catalog_skills(session, payload.catalogSkillIds)

    sponsor = Sponsor(
        name=payload.name,
        description=payload.description,
        website=payload.website,
        active=True,
    )
    sponsor.catalog_skills = skills
    session.add(sponsor)
    await session.flush()

    await write_audit_event(
        session,
        action="SPONSOR_CREATE",
        entity_type="Sponsor",
        entity_id=str(sponsor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        after=sponsor_to_dict(sponsor),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    loaded = await _load_sponsor(session, sponsor.id)
    assert loaded is not None
    return loaded


async def patch_sponsor(
    session: AsyncSession,
    sponsor_id: uuid.UUID,
    payload: SponsorPatch,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Sponsor:
    sponsor = await _load_sponsor(session, sponsor_id)
    if sponsor is None:
        raise AppError(
            "SPONSOR_NOT_FOUND",
            "Sponsor not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    before = sponsor_to_dict(sponsor)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        dup = await session.execute(
            select(Sponsor).where(
                func.lower(Sponsor.name) == data["name"].lower(),
                Sponsor.id != sponsor_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise AppError(
                "SPONSOR_DUPLICATE",
                "A sponsor with this name already exists",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("name", "DUPLICATE")],
            )
        sponsor.name = data["name"]

    if "description" in data:
        sponsor.description = data["description"]
    if "website" in data:
        sponsor.website = data["website"]
    if "active" in data and data["active"] is not None:
        sponsor.active = data["active"]
    if "catalogSkillIds" in data:
        skills = await _resolve_active_catalog_skills(
            session, data["catalogSkillIds"] or []
        )
        sponsor.catalog_skills = skills

    await session.flush()
    await write_audit_event(
        session,
        action="SPONSOR_UPDATE",
        entity_type="Sponsor",
        entity_id=str(sponsor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        before=before,
        after=sponsor_to_dict(sponsor),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    loaded = await _load_sponsor(session, sponsor.id)
    assert loaded is not None
    return loaded


async def upload_sponsor_logo(
    session: AsyncSession,
    sponsor_id: uuid.UUID,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Sponsor:
    from app.services.storage import get_object_storage

    sponsor = await _load_sponsor(session, sponsor_id)
    if sponsor is None:
        raise AppError(
            "SPONSOR_NOT_FOUND",
            "Sponsor not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    mime = _assert_logo_mime(content_type, filename)
    store = get_object_storage()
    previous_key = sponsor.logo_object_key
    stored = store.put(
        data,
        prefix=f"sponsors/{sponsor.id}/logo",
        filename=filename,
    )
    before = sponsor_to_dict(sponsor)
    sponsor.logo_object_key = stored.key
    sponsor.logo_file_name = filename
    sponsor.logo_content_type = mime
    sponsor.logo_scan_status = "CLEAN"
    await session.flush()
    await write_audit_event(
        session,
        action="SPONSOR_LOGO_UPLOAD",
        entity_type="Sponsor",
        entity_id=str(sponsor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        before=before,
        after=sponsor_to_dict(sponsor),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    if previous_key and previous_key != stored.key:
        try:
            store.delete(previous_key)
        except Exception:
            pass
    loaded = await _load_sponsor(session, sponsor.id)
    assert loaded is not None
    return loaded


async def clear_sponsor_logo(
    session: AsyncSession,
    sponsor_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Sponsor:
    from app.services.storage import get_object_storage

    sponsor = await _load_sponsor(session, sponsor_id)
    if sponsor is None:
        raise AppError(
            "SPONSOR_NOT_FOUND",
            "Sponsor not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    before = sponsor_to_dict(sponsor)
    previous_key = sponsor.logo_object_key
    sponsor.logo_object_key = None
    sponsor.logo_file_name = None
    sponsor.logo_content_type = None
    sponsor.logo_scan_status = None
    await session.flush()
    await write_audit_event(
        session,
        action="SPONSOR_LOGO_CLEAR",
        entity_type="Sponsor",
        entity_id=str(sponsor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=None,
        before=before,
        after=sponsor_to_dict(sponsor),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    if previous_key:
        try:
            get_object_storage().delete(previous_key)
        except Exception:
            pass
    loaded = await _load_sponsor(session, sponsor.id)
    assert loaded is not None
    return loaded


async def download_sponsor_logo(
    session: AsyncSession,
    sponsor_id: uuid.UUID,
    *,
    active_only: bool = False,
) -> tuple[bytes, str, str]:
    from app.services.storage import get_object_storage

    sponsor = await session.get(Sponsor, sponsor_id)
    if sponsor is None or (active_only and not sponsor.active):
        raise AppError(
            "SPONSOR_NOT_FOUND",
            "Sponsor not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not sponsor.logo_object_key or not sponsor.logo_file_name:
        raise AppError("FILE_NOT_FOUND", "No logo attached", status_code=404)

    store = get_object_storage()
    data = store.get(sponsor.logo_object_key)
    return (
        data,
        sponsor.logo_content_type or "application/octet-stream",
        sponsor.logo_file_name,
    )
